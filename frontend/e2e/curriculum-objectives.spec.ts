import { expect, test, type APIRequestContext, type Page } from '@playwright/test';

import { demoDraft, expectNoAccessibilityViolations, openApp } from './support';

// Runs against the demo programme (load-demo) as the test admin. Each journey makes its
// own uniquely named phase, module, session and programme outcome through the API, works
// on those only (the other journeys run in parallel) and deletes them afterwards.
const PROGRAMME = 'BSc Health Sciences (Demo)';
const API = '/api/v1';

interface Fixture {
  versionId: string;
  phaseId: string;
  moduleId: string;
  eventId: string;
  outcomeId: string;
  suffix: string;
  outcomeText: string;
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

async function makeFixture(page: Page, project: string): Promise<Fixture> {
  await openApp(page, '/');
  const headers = await csrfHeaders(page);
  const programmes = (await (await page.request.get(`${API}/programmes`)).json()) as {
    name: string;
    versions: { id: string; status: string; academic_year: number }[];
  }[];
  const versionId = demoDraft(programmes.find((p) => p.name === PROGRAMME)!.versions);
  const suffix = `${project}-${Date.now() % 1_000_000}`;
  const phase = await post<{ id: string }>(
    page.request,
    headers,
    `/curriculum-versions/${versionId}/phases`,
    { name: `Objectives ${suffix}`, kind: 'block' }
  );
  const module = await post<{ id: string }>(
    page.request,
    headers,
    `/curriculum-versions/${versionId}/modules`,
    { code: `OB-${suffix}`, name: 'Objectives module', phase_id: phase.id }
  );
  const event = await post<{ id: string }>(
    page.request,
    headers,
    `/modules/${module.id}/learning-events`,
    { title: 'Objectives session' }
  );
  const outcomeText = `Programme outcome ${suffix}`;
  const outcome = await post<{ id: string }>(
    page.request,
    headers,
    `/curriculum-versions/${versionId}/outcomes`,
    { text: outcomeText }
  );
  return {
    versionId,
    phaseId: phase.id,
    moduleId: module.id,
    eventId: event.id,
    outcomeId: outcome.id,
    suffix,
    outcomeText,
  };
}

async function cleanUp(page: Page, fixture: Fixture) {
  const headers = await csrfHeaders(page);
  // Deleting the module takes its sessions and their objectives with it.
  await page.request.delete(`${API}/modules/${fixture.moduleId}`, { headers });
  await page.request.delete(`${API}/phases/${fixture.phaseId}`, { headers });
  await page.request.delete(`${API}/objectives/${fixture.outcomeId}`, { headers });
}

test.describe('objective editor', () => {
  let fixture: Fixture | null = null;

  test.afterEach(async ({ page }) => {
    if (fixture) await cleanUp(page, fixture);
    fixture = null;
  });

  test('adds, changes and deletes a session objective with its links', async ({
    page,
  }, testInfo) => {
    test.slow();
    fixture = await makeFixture(page, testInfo.project.name);
    await openApp(page, `/curriculum/versions/${fixture.versionId}?item=event:${fixture.eventId}`);
    const notice = page.getByRole('status').filter({ hasText: /objective/ });

    // Cancelling leaves nothing behind and returns focus to the button.
    const add = page.getByRole('button', { name: 'Add objective' });
    await add.click();
    const dialog = page.getByRole('dialog', { name: 'Add objective' });
    await expect(dialog.getByRole('textbox', { name: /Wording/ })).toBeFocused();
    await expectNoAccessibilityViolations(page);
    await page.keyboard.press('Escape');
    await expect(dialog).toBeHidden();
    await expect(add).toBeFocused();

    // The wording is required; domain, taxonomy level and upward link are chosen.
    await add.click();
    await dialog.getByRole('button', { name: 'Add objective' }).click();
    await expect(dialog.getByText('Fill in this field.')).toBeVisible();
    await expectNoAccessibilityViolations(page);
    await dialog.getByRole('textbox', { name: /Wording/ }).fill('Take a pulse and record it.');
    await dialog.getByRole('combobox', { name: 'Domain' }).selectOption({ label: 'Skill' });
    const level = dialog.getByRole('combobox', { name: 'Taxonomy level' });
    await expect(level.getByRole('option')).not.toHaveCount(1);
    await level.selectOption({ index: 1 });
    await dialog.getByRole('checkbox', { name: new RegExp(fixture.outcomeText) }).check();
    await expectNoAccessibilityViolations(page);
    await dialog.getByRole('button', { name: 'Add objective' }).click();
    await expect(notice).toHaveText('The objective was added.');
    const row = page.getByRole('listitem').filter({ hasText: 'Take a pulse and record it.' });
    await expect(row.getByText('Skill')).toBeVisible();
    await expect(row.getByText('Linked to 1 broader outcome')).toBeVisible();
    await expectNoAccessibilityViolations(page);

    // Change the wording and status; the link stays ticked.
    await row.getByRole('button', { name: /^Edit objective/ }).click();
    const edit = page.getByRole('dialog', { name: 'Edit objective' });
    await expect(edit.getByRole('textbox', { name: /Wording/ })).toHaveValue(
      'Take a pulse and record it.'
    );
    await expect(
      edit.getByRole('checkbox', { name: new RegExp(fixture.outcomeText) })
    ).toBeChecked();
    await edit.getByRole('textbox', { name: /Wording/ }).fill('Take a pulse and blood pressure.');
    await edit.getByRole('combobox', { name: 'Status' }).selectOption({ label: 'Approved' });
    await expectNoAccessibilityViolations(page);
    await edit.getByRole('button', { name: 'Save changes' }).click();
    await expect(notice).toHaveText('Changes to the objective saved.');
    const changed = page
      .getByRole('listitem')
      .filter({ hasText: 'Take a pulse and blood pressure.' });
    await expect(changed.getByText('Approved')).toBeVisible();
    await expect(changed.getByText('Linked to 1 broader outcome')).toBeVisible();

    // Delete it; the confirmation takes focus because the button is gone.
    await changed.getByRole('button', { name: /^Delete objective/ }).click();
    const remove = page.getByRole('dialog', { name: 'Delete this objective?' });
    await expectNoAccessibilityViolations(page);
    await remove.getByRole('button', { name: 'Delete objective' }).click();
    await expect(notice).toHaveText('The objective was deleted.');
    await expect(page.getByText('Take a pulse and blood pressure.')).toHaveCount(0);
    await expectNoAccessibilityViolations(page);
  });

  test('adds a module outcome and edits the programme outcome', async ({ page }, testInfo) => {
    test.slow();
    fixture = await makeFixture(page, testInfo.project.name);
    await openApp(page, `/curriculum/versions/${fixture.versionId}?item=module:${fixture.moduleId}`);
    const notice = page.getByRole('status').filter({ hasText: /outcome/ });

    await page.getByRole('button', { name: 'Add outcome' }).click();
    const dialog = page.getByRole('dialog', { name: 'Add outcome' });
    await dialog.getByRole('textbox', { name: /Wording/ }).fill('Explain the module aims.');
    await dialog.getByRole('checkbox', { name: new RegExp(fixture.outcomeText) }).check();
    await expectNoAccessibilityViolations(page);
    await dialog.getByRole('button', { name: 'Add outcome' }).click();
    await expect(notice).toHaveText('The outcome was added.');
    await expect(
      page
        .getByRole('listitem')
        .filter({ hasText: 'Explain the module aims.' })
        .getByText('Linked to 1 broader outcome')
    ).toBeVisible();

    // The programme's own outcomes have no upward links to choose.
    await openApp(page, `/curriculum/versions/${fixture.versionId}`);
    const row = page.getByRole('listitem').filter({ hasText: fixture.outcomeText });
    await row.getByRole('button', { name: /^Edit outcome/ }).click();
    const edit = page.getByRole('dialog', { name: 'Edit outcome' });
    await expect(edit.getByRole('checkbox')).toHaveCount(0);
    await expectNoAccessibilityViolations(page);
    await edit.getByRole('combobox', { name: 'Domain' }).selectOption({ label: 'Attitude' });
    await edit.getByRole('button', { name: 'Save changes' }).click();
    await expect(notice).toHaveText('Changes to the outcome saved.');
    await expect(
      page.getByRole('listitem').filter({ hasText: fixture.outcomeText }).getByText('Attitude')
    ).toBeVisible();
  });
});
