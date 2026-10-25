import { expect, test, type APIRequestContext, type Page } from '@playwright/test';

import { expectNoAccessibilityViolations, openApp } from './support';

// Runs against the demo programme (load-demo) as the test admin. Each journey makes its
// own uniquely named phase with modules through the API, works on those only (the other
// journeys run in parallel) and deletes everything it made afterwards.
const PROGRAMME = 'BSc Health Sciences (Demo)';
const API = '/api/v1';

interface Fixture {
  versionId: string;
  phaseId: string;
  suffix: string;
  /** Module ids by code. */
  modules: Record<string, string>;
}

async function csrfHeaders(page: Page): Promise<Record<string, string>> {
  const cookies = await page.context().cookies();
  const csrf = cookies.find((cookie) => cookie.name === 'ocmp_csrf');
  if (!csrf) throw new Error('No CSRF cookie: is the saved session valid?');
  return { 'X-CSRF-Token': csrf.value };
}

async function post<T>(
  request: APIRequestContext,
  headers: Record<string, string>,
  path: string,
  data: object
) {
  const response = await request.post(`${API}${path}`, { headers, data });
  expect(response.status(), await response.text()).toBe(201);
  return (await response.json()) as T;
}

/** A phase with two modules (A first, B second) and a session in A. */
async function makeFixture(page: Page, project: string): Promise<Fixture> {
  await openApp(page, '/');
  const headers = await csrfHeaders(page);
  const programmes = (await (await page.request.get(`${API}/programmes`)).json()) as {
    name: string;
    versions: { id: string }[];
  }[];
  const versionId = programmes.find((p) => p.name === PROGRAMME)!.versions[0].id;
  const suffix = `${project}-${Date.now() % 1_000_000}`;
  const phase = await post<{ id: string }>(
    page.request,
    headers,
    `/curriculum-versions/${versionId}/phases`,
    { name: `Reorder ${suffix}`, kind: 'block' }
  );
  const modules: Record<string, string> = {};
  for (const letter of ['A', 'B']) {
    const code = `R${letter}-${suffix}`;
    const module = await post<{ id: string }>(
      page.request,
      headers,
      `/curriculum-versions/${versionId}/modules`,
      { code, name: `Module ${letter}`, phase_id: phase.id }
    );
    modules[code] = module.id;
  }
  await post(page.request, headers, `/modules/${modules[`RA-${suffix}`]}/learning-events`, {
    title: 'Opening session',
  });
  return { versionId, phaseId: phase.id, suffix, modules };
}

/** Deletes every module of the journey's phases (copies too), then the phases. */
async function cleanUp(page: Page, fixture: Fixture) {
  const headers = await csrfHeaders(page);
  const structure = (await (
    await page.request.get(`${API}/curriculum-versions/${fixture.versionId}/structure`)
  ).json()) as { phases: { id: string; name: string; modules: { id: string }[] }[] };
  const mine = structure.phases.filter((phase) => phase.name.includes(fixture.suffix));
  for (const phase of mine) {
    for (const module of phase.modules) {
      await page.request.delete(`${API}/modules/${module.id}`, { headers });
    }
    await page.request.delete(`${API}/phases/${phase.id}`, { headers });
  }
}

test.describe('curriculum builder reordering and copying', () => {
  let fixture: Fixture | null = null;

  test.afterEach(async ({ page }) => {
    if (fixture) await cleanUp(page, fixture);
    fixture = null;
  });

  test('moves a module with the keyboard and by dragging', async ({ page }, testInfo) => {
    test.slow(); // long journeys; the others run in parallel
    fixture = await makeFixture(page, testInfo.project.name);
    const { suffix, modules } = fixture;
    const a = `RA-${suffix}`;
    const b = `RB-${suffix}`;
    await openApp(page, `/curriculum/versions/${fixture.versionId}?item=module:${modules[b]}`);
    const tree = page.getByRole('tree', { name: `Structure of ${PROGRAMME}` });
    const itemA = tree.getByRole('treeitem', { name: new RegExp(a) });
    const itemB = tree.getByRole('treeitem', { name: new RegExp(b) });
    await expect(itemB).toHaveAttribute('aria-posinset', '2');
    await expect(page.getByText(/drag an item in the tree/)).toBeVisible();

    // Keyboard: Move up with Enter. B becomes first, so Move up is no longer available
    // and focus goes to the confirmation.
    const up = page.getByRole('button', { name: 'Move up' });
    const down = page.getByRole('button', { name: 'Move down' });
    await expect(down).toBeDisabled();
    await up.focus();
    await page.keyboard.press('Enter');
    const notice = page.getByRole('status').filter({ hasText: 'moved to place' });
    await expect(notice).toHaveText(`${b} Module B moved to place 1 of 2.`);
    await expect(itemB).toHaveAttribute('aria-posinset', '1');
    await expect(itemA).toHaveAttribute('aria-posinset', '2');
    await expect(up).toBeDisabled();
    await expect(page.locator(':focus')).toContainText('moved to place 1 of 2');
    await expectNoAccessibilityViolations(page);

    // Space on Move down puts it back.
    await down.focus();
    await page.keyboard.press('Space');
    await expect(notice).toHaveText(`${b} Module B moved to place 2 of 2.`);
    await expect(itemB).toHaveAttribute('aria-posinset', '2');

    // Pointer: drag A below B.
    await expect(itemA).toHaveAttribute('draggable', 'true');
    await itemA.dragTo(itemB);
    await expect(notice).toHaveText(`${a} Module A moved to place 2 of 2.`);
    await expect(itemA).toHaveAttribute('aria-posinset', '2');
    // The selection did not change.
    await expect(itemB).toHaveAttribute('aria-selected', 'true');
  });

  test('copies a module, a session and a phase with what they hold', async ({ page }, testInfo) => {
    test.slow();
    fixture = await makeFixture(page, testInfo.project.name);
    const { suffix, modules } = fixture;
    const a = `RA-${suffix}`;
    const b = `RB-${suffix}`;
    await openApp(page, `/curriculum/versions/${fixture.versionId}?item=module:${modules[a]}`);
    const tree = page.getByRole('tree', { name: `Structure of ${PROGRAMME}` });
    const notice = page.getByRole('status').filter({ hasText: 'added as a copy' });

    // Module: the code is required and must be new.
    await page.getByRole('button', { name: 'Copy module' }).click();
    const moduleDialog = page.getByRole('dialog', { name: `Copy ${a} Module A` });
    const code = moduleDialog.getByRole('textbox', { name: /Code/ });
    await expect(code).toBeFocused();
    await expect(moduleDialog.getByRole('textbox', { name: /Name/ })).toHaveValue(
      'Module A (copy)'
    );
    await moduleDialog.getByRole('button', { name: 'Copy module' }).click();
    await expect(moduleDialog.getByText('Fill in this field.')).toBeVisible();
    await code.fill(b);
    await moduleDialog.getByRole('button', { name: 'Copy module' }).click();
    await expect(moduleDialog.getByRole('alert')).toContainText('already uses this code');
    await expectNoAccessibilityViolations(page);
    await code.fill(`RC-${suffix}`);
    await moduleDialog.getByRole('button', { name: 'Copy module' }).click();
    await expect(notice).toHaveText(`RC-${suffix} Module A (copy) added as a copy.`);
    const copied = tree.getByRole('treeitem', { name: new RegExp(`RC-${suffix}`) });
    await expect(copied).toHaveAttribute('aria-selected', 'true');
    // Placed right after the original, with its session.
    await expect(copied).toHaveAttribute('aria-posinset', '2');
    await expect(copied).toContainText('1 session');

    // Session: copied right after itself in the same module.
    await tree.getByRole('treeitem', { name: /Opening session/ }).first().click();
    await page.getByRole('button', { name: 'Copy session' }).click();
    const sessionDialog = page.getByRole('dialog', { name: 'Copy Opening session' });
    await expect(sessionDialog.getByRole('textbox', { name: /Title/ })).toHaveValue(
      'Opening session (copy)'
    );
    await expectNoAccessibilityViolations(page);
    await sessionDialog.getByRole('button', { name: 'Copy session' }).click();
    await expect(notice).toHaveText('Opening session (copy) added as a copy.');
    await expect(tree.getByRole('treeitem', { name: /Opening session \(copy\)/ })).toHaveAttribute(
      'aria-selected',
      'true'
    );

    // Phase: one new code per module.
    await tree.getByRole('treeitem', { name: new RegExp(`Reorder ${suffix}`) }).click();
    await page.getByRole('button', { name: 'Copy phase' }).click();
    const phaseDialog = page.getByRole('dialog', { name: `Copy Reorder ${suffix}` });
    const codes = phaseDialog.getByRole('textbox', { name: /New code for/ });
    await expect(codes).toHaveCount(3);
    for (const [index, letter] of ['D', 'E', 'F'].entries()) {
      await codes.nth(index).fill(`R${letter}-${suffix}`);
    }
    await expectNoAccessibilityViolations(page);
    await phaseDialog.getByRole('button', { name: 'Copy phase' }).click();
    await expect(notice).toHaveText(`Reorder ${suffix} (copy) added as a copy.`);
    const phaseCopy = tree.getByRole('treeitem', {
      name: new RegExp(`Reorder ${suffix} \\(copy\\)`),
    });
    await expect(phaseCopy).toHaveAttribute('aria-selected', 'true');
    await expect(phaseCopy).toContainText('3 modules');
    await expect(tree.getByRole('treeitem', { name: new RegExp(`RD-${suffix}`) })).toBeVisible();
    await expectNoAccessibilityViolations(page);
  });
});
