import AxeBuilder from '@axe-core/playwright';
import { expect, type Page } from '@playwright/test';

/** Session cookies saved by auth.setup.ts (git-ignored). */
export const SIGNED_IN_STATE = 'e2e/.auth/signed-in.json';

/** Session of a user who holds only a session role (lecturer.setup.ts; git-ignored). */
export const LECTURER_STATE = 'e2e/.auth/lecturer.json';

export const LECTURER_EMAIL = 'e2e.lecturer@example.org';

/** The lecturer's password follows the admin's, so no extra secret is needed. */
export function lecturerPassword(): string {
  return `${credentials().password}-lecturer`;
}

/**
 * The demo programme's oldest draft version. Journeys that edit the curriculum work in it
 * because the newest version can be the copy another journey is publishing meanwhile.
 */
export function demoDraft(versions: { id: string; status: string; academic_year: number }[]): string {
  const drafts = versions
    .filter((version) => version.status === 'draft')
    .sort((a, b) => a.academic_year - b.academic_year);
  if (drafts.length === 0) throw new Error('No draft version: load the demo data (load-demo).');
  return drafts[0].id;
}

/**
 * Removes a framework version a journey imported (frameworks have no screen to delete from),
 * so the local demo stays clean. Tolerates one that is already gone.
 */
export async function removeFramework(page: Page, frameworkId: string): Promise<void> {
  const csrf = (await page.context().cookies()).find((cookie) => cookie.name === 'ocmp_csrf');
  if (!csrf) return;
  await page.request.delete(`/api/v1/frameworks/${frameworkId}`, {
    headers: { 'X-CSRF-Token': csrf.value },
  });
}

/** Removes the tag list with this key (and its unused tags), if a journey left it behind. */
export async function removeTagListByKey(page: Page, key: string): Promise<void> {
  const csrf = (await page.context().cookies()).find((cookie) => cookie.name === 'ocmp_csrf');
  if (!csrf) return;
  const lists = await page.request.get('/api/v1/tag-lists');
  if (!lists.ok()) return;
  const found = ((await lists.json()) as { id: string; key: string }[]).find((l) => l.key === key);
  if (found) {
    await page.request.delete(`/api/v1/tag-lists/${found.id}`, {
      headers: { 'X-CSRF-Token': csrf.value },
    });
  }
}

/** For tests of the signed-out pages. */
export const SIGNED_OUT = { cookies: [], origins: [] };

/** WCAG 2.2 A and AA rules (brief section 11). */
const WCAG_TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'];

/** A platform admin on the stack under test (see e2e/README.md). */
export function credentials(): { email: string; password: string } {
  const email = process.env.E2E_EMAIL;
  const password = process.env.E2E_PASSWORD;
  if (!email || !password) {
    throw new Error('Set E2E_EMAIL and E2E_PASSWORD to a platform admin on the stack under test.');
  }
  return { email, password };
}

/** Opens a page of the signed-in app and waits for the app frame (the account menu). */
export async function openApp(page: Page, path: string): Promise<void> {
  await page.goto(path);
  await expect(page.getByRole('button', { name: /account menu for/i })).toBeVisible();
}

/** Runs axe on the current page and fails with a readable list of violations. */
export async function expectNoAccessibilityViolations(page: Page): Promise<void> {
  // Fonts must be loaded before colour contrast is measured.
  await page.evaluate(() => document.fonts.ready);
  // Colour contrast is only meaningful in the settled state. Two things made it flaky:
  // 1. A dialog or menu that is still fading in has partly transparent text. CSS transitions
  //    and animations are switched off for the check (the final colours are what matter), and
  //    the check waits until every dialog, menu and list box is fully opaque.
  // 2. A dialog that has not been rendered yet when this runs (the click returned, React and
  //    Mantine mount it a little later on a slow runner) is not in the page, so "all dialogs
  //    are opaque" is vacuously true and axe then measured it mid-fade (found in the CI trace
  //    of run 40505442931: no dialog in the frame when axe started, half faded in during it).
  //    So the page must also have been quiet, with no DOM change, for 300 ms.
  await page.evaluate(() => {
    if (document.getElementById('e2e-no-motion')) return;
    const style = document.createElement('style');
    style.id = 'e2e-no-motion';
    style.textContent =
      '*, *::before, *::after { transition: none !important; animation: none !important; }';
    document.head.appendChild(style);
  });
  await page
    .waitForFunction(
      () => {
        const w = window as unknown as { __lastChange?: number };
        if (w.__lastChange === undefined) {
          w.__lastChange = performance.now();
          new MutationObserver(() => {
            w.__lastChange = performance.now();
          }).observe(document.documentElement, {
            subtree: true,
            childList: true,
            attributes: true,
            characterData: true,
          });
          return false;
        }
        const quiet = performance.now() - w.__lastChange >= 300;
        const opaque = Array.from(
          document.querySelectorAll('[role="dialog"], [role="menu"], [role="listbox"]')
        ).every((element) => {
          for (let node: Element | null = element; node; node = node.parentElement) {
            if (getComputedStyle(node).opacity !== '1') return false;
          }
          return true;
        });
        const settled = document
          .getAnimations()
          .every(
            (animation) =>
              animation.playState !== 'running' ||
              animation.effect?.getComputedTiming().iterations === Infinity
          );
        return quiet && opaque && settled;
      },
      undefined,
      { timeout: 5000, polling: 50 }
    )
    .catch(() => undefined);
  const results = await new AxeBuilder({ page }).withTags(WCAG_TAGS).analyze();
  const summary = results.violations.map(
    (v) => `${v.id} (${v.impact}): ${v.help}\n  ${v.nodes.map((n) => n.target.join(' ')).join('\n  ')}`
  );
  expect(summary, summary.join('\n')).toEqual([]);
}
