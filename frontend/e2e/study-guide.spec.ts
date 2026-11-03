import { expect, test, type Page } from '@playwright/test';

import { demoDraft, expectNoAccessibilityViolations, openApp } from './support';

// Runs against the demo programme (load-demo) as the test admin, who holds the AI permission.
// AI is off on the test stack, so nothing is ever read or recorded: the journey checks the panel,
// the upload dialog with its confirmation and the refusal in words, in both themes, with axe.
// Each journey makes its own uniquely named phase and module through the API and removes them
// afterwards, also when it fails (ADR 037).
const PROGRAMME = 'BSc Health Sciences (Demo)';
const API = '/api/v1';

interface Fixture {
  versionId: string;
  phaseId: string;
  moduleId: string;
}

async function csrfHeaders(page: Page): Promise<Record<string, string>> {
  const cookie = (await page.context().cookies()).find((c) => c.name === 'ocmp_csrf');
  if (!cookie) throw new Error('No CSRF cookie: is the saved session valid?');
  return { 'X-CSRF-Token': cookie.value };
}

async function post<T>(page: Page, path: string, data: object): Promise<T> {
  const response = await page.request.post(`${API}${path}`, {
    headers: await csrfHeaders(page),
    data,
  });
  expect(response.status(), await response.text()).toBe(201);
  return (await response.json()) as T;
}

async function makeFixture(page: Page, project: string): Promise<Fixture> {
  await openApp(page, '/');
  const programmes = (await (await page.request.get(`${API}/programmes`)).json()) as {
    name: string;
    versions: { id: string; status: string; academic_year: number }[];
  }[];
  const versionId = demoDraft(programmes.find((p) => p.name === PROGRAMME)!.versions);
  const suffix = `${project}-${Date.now() % 1_000_000}`;
  const phase = await post<{ id: string }>(page, `/curriculum-versions/${versionId}/phases`, {
    name: `Guide ${suffix}`,
    kind: 'block',
  });
  const module = await post<{ id: string }>(page, `/curriculum-versions/${versionId}/modules`, {
    code: `SG-${suffix}`,
    name: 'Study guide module',
    phase_id: phase.id,
  });
  return { versionId, phaseId: phase.id, moduleId: module.id };
}

async function cleanUp(page: Page, fixture: Fixture) {
  const headers = await csrfHeaders(page);
  await page.request.delete(`${API}/modules/${fixture.moduleId}`, { headers });
  await page.request.delete(`${API}/phases/${fixture.phaseId}`, { headers });
}

test.describe('study guides', () => {
  let fixture: Fixture | null = null;

  test.afterEach(async ({ page }) => {
    if (fixture) await cleanUp(page, fixture);
    fixture = null;
  });

  test('shows the panel, asks for the confirmation and says in words that AI is off', async ({
    page,
  }, testInfo) => {
    test.slow();
    fixture = await makeFixture(page, testInfo.project.name);
    await openApp(
      page,
      `/curriculum/versions/${fixture.versionId}?item=module:${fixture.moduleId}`,
    );

    const panel = page.getByRole('region', { name: 'Study guide' });
    await expect(panel).toBeVisible();
    await expect(panel.getByText(/Nothing becomes an outcome until you accept it/)).toBeVisible();
    await expectNoAccessibilityViolations(page);

    await panel.getByRole('button', { name: 'Read a study guide' }).click();
    const dialog = page.getByRole('dialog', { name: 'Read a study guide' });
    await expect(
      dialog.getByRole('checkbox', { name: /contains no real patient information/ }),
    ).not.toBeChecked();
    await expectNoAccessibilityViolations(page);

    // Without the tick nothing is sent, and the box says what is missing.
    await dialog
      .locator('input[type="file"]')
      .setInputFiles({
        name: 'guide.docx',
        mimeType: 'application/octet-stream',
        buffer: Buffer.from('x'),
      });
    await dialog.getByRole('button', { name: 'Read it' }).click();
    await expect(dialog.getByText('Confirm this before the study guide is read.')).toBeVisible();
    await expectNoAccessibilityViolations(page);

    // With it, AI being off is refused before the file is read or anything is recorded.
    await dialog.getByRole('checkbox', { name: /contains no real patient information/ }).check();
    await dialog.getByRole('button', { name: 'Read it' }).click();
    await expect(dialog.getByRole('alert')).toContainText('AI is switched off', {
      timeout: 15_000,
    });
    await expectNoAccessibilityViolations(page);
  });
});
