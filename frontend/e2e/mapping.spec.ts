import { expect, test, type Page } from '@playwright/test';

import {
  demoDraft,
  expectNoAccessibilityViolations,
  openApp,
  removeFramework,
} from './support';

// Runs against the demo programme (load-demo) as the test admin. Each journey makes its own
// uniquely named phase, module and objective plus a small framework through the API, works on
// those only (the other journeys run in parallel) and removes them afterwards, also when it
// fails: links first (a framework with links cannot be deleted), then the module, the phase
// and the framework (ADR 037).
const PROGRAMME = 'BSc Health Sciences (Demo)';
const API = '/api/v1';

interface Fixture {
  versionId: string;
  phaseId: string;
  moduleId: string;
  objectiveId: string;
  frameworkId: string;
  suffix: string;
  objectiveText: string;
  moduleLabel: string;
}

let current: Fixture | null = null;

async function csrf(page: Page): Promise<Record<string, string>> {
  const cookie = (await page.context().cookies()).find((c) => c.name === 'ocmp_csrf');
  if (!cookie) throw new Error('No CSRF cookie: is the saved session valid?');
  return { 'X-CSRF-Token': cookie.value };
}

async function post<T>(page: Page, path: string, data: object, status = 201): Promise<T> {
  const response = await page.request.post(`${API}${path}`, { headers: await csrf(page), data });
  expect(response.status(), await response.text()).toBe(status);
  return (await response.json()) as T;
}

function packJson(key: string, name: string): string {
  return JSON.stringify({
    format_version: 2,
    metadata: {
      key,
      name,
      version: '1',
      publisher: 'End-to-end tests',
      licence: 'Fictional, for tests',
    },
    items: [
      { code: 'M-1', title: 'First mapping group', order: 0 },
      { code: 'M-1.1', title: 'Gather a history', parent_code: 'M-1', order: 1 },
      { code: 'M-2', title: 'Second mapping keyword', order: 2 },
    ],
  });
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
    name: `Mapping ${suffix}`,
    kind: 'block',
  });
  const code = `MP-${suffix}`;
  const module = await post<{ id: string }>(page, `/curriculum-versions/${versionId}/modules`, {
    code,
    name: 'Mapping module',
    phase_id: phase.id,
  });
  const objectiveText = `Describe the mapping journey ${suffix}`;
  const objective = await post<{ id: string }>(page, `/modules/${module.id}/outcomes`, {
    text: objectiveText,
  });
  const headers = await csrf(page);
  const key = `e2e-mapping-${suffix}`.toLowerCase();
  const preview = await page.request.post(`${API}/framework-packs/preview`, {
    headers: { ...headers, 'Content-Type': 'application/json' },
    data: packJson(key, `E2E mapping ${suffix}`),
  });
  expect(preview.ok(), await preview.text()).toBe(true);
  const { token } = (await preview.json()) as { token: string };
  const imported = await page.request.post(`${API}/framework-packs/import`, {
    headers,
    data: { token, activate: false },
  });
  expect(imported.ok(), await imported.text()).toBe(true);
  const { framework_id: frameworkId } = (await imported.json()) as { framework_id: string };
  return {
    versionId,
    phaseId: phase.id,
    moduleId: module.id,
    objectiveId: objective.id,
    frameworkId,
    suffix,
    objectiveText,
    moduleLabel: `${code} Mapping module`,
  };
}

async function cleanUp(page: Page, fixture: Fixture) {
  await openApp(page, '/');
  const headers = await csrf(page);
  const workspace = await page.request.get(`${API}/curriculum-versions/${fixture.versionId}/mapping`);
  if (workspace.ok()) {
    const data = (await workspace.json()) as {
      objectives: { id: string; links: { id: string; framework_id: string }[] }[];
    };
    for (const objective of data.objectives) {
      for (const link of objective.links) {
        if (link.framework_id === fixture.frameworkId) {
          await page.request.delete(`${API}/mapping-links/${link.id}`, { headers });
        }
      }
    }
  }
  await page.request.delete(`${API}/modules/${fixture.moduleId}`, { headers });
  await page.request.delete(`${API}/phases/${fixture.phaseId}`, { headers });
  await removeFramework(page, fixture.frameworkId);
}

test.describe('mapping workspace', () => {
  test.afterEach(async ({ page }) => {
    if (!current) return;
    const fixture = current;
    current = null;
    await cleanUp(page, fixture);
  });

  test('link an objective to a framework item, change the link and remove it', async ({
    page,
  }, testInfo) => {
    // A long journey with an axe scan at every step; the suite runs it beside many others.
    test.setTimeout(120_000);
    const fixture = await makeFixture(page, testInfo.project.name);
    current = fixture;

    await openApp(page, `/mapping/${fixture.versionId}`);
    await expect(page.getByRole('heading', { level: 1, name: 'Mapping' })).toBeVisible();
    await page.getByLabel('Module', { exact: true }).selectOption({ label: fixture.moduleLabel });
    await expect(page.getByText(/Showing 1 of \d+ objectives/)).toBeVisible();
    await expectNoAccessibilityViolations(page);

    // Select the objective; it has no links yet.
    await page.getByRole('button', { name: new RegExp(fixture.objectiveText) }).click();
    await expect(page.getByText('This objective is not linked to any framework item yet.')).toBeVisible();

    // The "?" explains coverage and depth, word for word.
    await page.getByRole('button', { name: 'Help with coverage and depth' }).first().click();
    const help = page.getByRole('region', { name: 'Coverage and depth' });
    await expect(help.getByText(/from 0 \(none\) to 5 \(more than 80%\)/)).toBeVisible();
    await expect(help.getByText('81 to 100%')).toBeVisible();
    await expect(help.getByText('Not applicable')).toBeVisible();
    await expectNoAccessibilityViolations(page);

    // Find an item by search in the framework pane, and link it.
    const chooser = page.getByLabel('Choose a framework');
    await chooser.selectOption({ label: `E2E mapping ${fixture.suffix} (1)` });
    await page.getByRole('searchbox', { name: /Search this framework/ }).fill('keyword');
    await page
      .getByRole('list', { name: 'Search results' })
      .getByRole('button', { name: /Second mapping keyword/ })
      .click();
    await page.getByRole('button', { name: 'Link to the selected objective' }).click();

    const dialog = page.getByRole('dialog');
    await expect(dialog.getByRole('heading', { name: 'Link the objective to the item' })).toBeVisible();
    await expectNoAccessibilityViolations(page);

    // Both choices are needed; the message says which.
    await dialog.getByRole('button', { name: 'Add link' }).click();
    await expect(dialog.getByText('Choose a coverage from 0 to 5.')).toBeVisible();
    await expectNoAccessibilityViolations(page);
    await dialog.getByLabel('3: 41 to 60%').check();
    await dialog.getByRole('button', { name: 'Add link' }).click();
    await expect(dialog.getByText('Choose a depth.')).toBeVisible();
    // Depth by keyboard alone.
    await dialog.getByLabel('Not applicable').focus();
    await page.keyboard.press('Space');
    await expect(dialog.getByText(/states no depth and implies none/)).toBeVisible();
    await dialog.getByLabel(/Reason/).fill('Keyword item, no depth.');
    await expectNoAccessibilityViolations(page);
    await dialog.getByRole('button', { name: 'Add link' }).click();

    await expect(page.getByText(/Linked to M-2 Second mapping keyword/)).toBeVisible();
    const links = page.getByRole('list', { name: 'Links of this objective' });
    await expect(links.getByText('Coverage 3 of 5: 41 to 60%')).toBeVisible();
    await expect(links.getByText('Depth: not applicable')).toBeVisible();
    await expect(links.getByText('Accepted')).toBeVisible();
    await expectNoAccessibilityViolations(page);

    // The item shows the objective in its "where mapped" list.
    const mapped = page.getByRole('list', { name: 'Objectives mapped to this item' });
    await expect(mapped.getByText(fixture.objectiveText)).toBeVisible();

    // Change the link.
    await links.getByRole('button', { name: /^Edit the link to M-2/ }).click();
    await expect(dialog.getByLabel('3: 41 to 60%')).toBeChecked();
    await dialog.getByLabel('5: 81 to 100%').check();
    await dialog.getByLabel('Above').check();
    await dialog.getByRole('button', { name: 'Save link' }).click();
    await expect(page.getByText(/Saved the link to M-2/)).toBeVisible();
    await expect(links.getByText('Coverage 5 of 5: 81 to 100%')).toBeVisible();
    await expect(links.getByText('Depth: above the item')).toBeVisible();

    // Remove it, after a question.
    await links.getByRole('button', { name: /^Remove the link to M-2/ }).click();
    await expect(dialog.getByText(/will no longer be linked to M-2/)).toBeVisible();
    await expectNoAccessibilityViolations(page);
    await dialog.getByRole('button', { name: 'Remove link' }).click();
    await expect(page.getByText('Removed the link to M-2 Second mapping keyword.')).toBeVisible();
    await expect(page.getByText('This objective is not linked to any framework item yet.')).toBeVisible();
    await expectNoAccessibilityViolations(page);
  });
});
