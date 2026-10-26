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
  const results = await new AxeBuilder({ page }).withTags(WCAG_TAGS).analyze();
  const summary = results.violations.map(
    (v) => `${v.id} (${v.impact}): ${v.help}\n  ${v.nodes.map((n) => n.target.join(' ')).join('\n  ')}`
  );
  expect(summary, summary.join('\n')).toEqual([]);
}
