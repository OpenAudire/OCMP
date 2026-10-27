import { expect, test, type APIRequestContext, type Page } from '@playwright/test';

import { demoDraft, expectNoAccessibilityViolations, openApp } from './support';

// Runs against the demo programme (load-demo) as the test admin. Each journey makes its
// own uniquely named block and module through the API, works on those only (the other
// journeys run in parallel) and removes them afterwards.
const PROGRAMME = 'BSc Health Sciences (Demo)';
const API = '/api/v1';

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

interface Fixture {
  versionId: string;
  phaseId: string;
  moduleId: string;
  moduleLabel: string;
  outcome: string;
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
    { name: `Assessments ${suffix}`, kind: 'block' }
  );
  // Two credits are 20 notional hours, so the 2 hours planned below are "under".
  const module = await post<{ id: string }>(
    page.request,
    headers,
    `/curriculum-versions/${versionId}/modules`,
    { code: `AS-${suffix}`, name: 'Assessment module', phase_id: phase.id, credits: 2, nqf_level: 5 }
  );
  await post(page.request, headers, `/modules/${module.id}/learning-events`, {
    title: `Assessment session ${suffix}`,
    contact_minutes: 60,
    self_study_minutes: 60,
  });
  const outcome = `Explain the assessed outcome ${suffix}.`;
  await post(page.request, headers, `/modules/${module.id}/outcomes`, { text: outcome });
  return {
    versionId,
    phaseId: phase.id,
    moduleId: module.id,
    moduleLabel: `AS-${suffix} Assessment module`,
    outcome,
  };
}

async function cleanUp(page: Page, fixture: Fixture) {
  const headers = await csrfHeaders(page);
  await page.request.delete(`${API}/modules/${fixture.moduleId}`, { headers });
  await page.request.delete(`${API}/phases/${fixture.phaseId}`, { headers });
}

test.describe('assessments and credits', () => {
  let fixture: Fixture | null = null;

  test.afterEach(async ({ page }) => {
    if (fixture) await cleanUp(page, fixture);
    fixture = null;
  });

  test('adds an assessment with an item linked to an outcome and sees the hours change', async ({
    page,
  }, testInfo) => {
    test.slow();
    fixture = await makeFixture(page, testInfo.project.name);
    await openApp(page, `/curriculum/versions/${fixture.versionId}?item=module:${fixture.moduleId}`);

    // The planned hours are advice, in words: 2 h against 20 h expected.
    await expect(page.getByText(/Planned 2 h against 20 h expected: 90% under/)).toBeVisible();
    const section = page.getByRole('region', { name: 'Assessments' });
    await expect(section.getByText('No assessments yet.')).toBeVisible();
    await expectNoAccessibilityViolations(page);

    // Nothing typed: the dialog says what is missing and saves nothing.
    await section.getByRole('button', { name: 'Add assessment' }).click();
    const dialog = page.getByRole('dialog', { name: 'Add assessment' });
    await dialog.getByRole('button', { name: 'Add assessment' }).click();
    await expect(dialog.getByText('Fill in this field.')).toBeVisible();
    await expectNoAccessibilityViolations(page);

    await dialog.getByRole('textbox', { name: /Name/ }).fill('Class test');
    await dialog.getByRole('textbox', { name: /Weight/ }).fill('100');
    await dialog.getByRole('textbox', { name: /^Timing/ }).fill('Week 6');
    await dialog.getByRole('textbox', { name: /Time in the assessment/ }).fill('60');
    await dialog.getByRole('button', { name: 'Add assessment' }).click();
    await expect(
      page.getByRole('status').filter({ hasText: 'Assessment Class test added' })
    ).toBeVisible();
    await expect(section.getByText('The weights add up to 100%.')).toBeVisible();
    // The hour of assessment time counts: 3 h against 20 h expected.
    await expect(page.getByText(/Planned 3 h against 20 h expected: 85% under/)).toBeVisible();
    await expectNoAccessibilityViolations(page);

    await section.getByRole('button', { name: 'Add item to Class test' }).click();
    const itemDialog = page.getByRole('dialog', { name: 'Add an item to Class test' });
    await itemDialog.getByRole('textbox', { name: /^Item/ }).fill('Question 1');
    await itemDialog.getByRole('textbox', { name: /Marks/ }).fill('20');
    await itemDialog.getByRole('checkbox', { name: new RegExp(fixture.outcome.slice(0, 30)) }).check();
    await expectNoAccessibilityViolations(page);
    await itemDialog.getByRole('button', { name: 'Add item' }).click();
    await expect(
      page.getByRole('status').filter({ hasText: 'Item Question 1 added' })
    ).toBeVisible();
    await expect(section.getByText('Question 1')).toBeVisible();
    await expect(section.getByText('20 marks')).toBeVisible();
    await expect(section.getByText('Assesses 1 objective:')).toBeVisible();
    await expect(section.getByText(fixture.outcome)).toBeVisible();
    await expectNoAccessibilityViolations(page);

    // The version-wide check lists the module with its planned and expected hours.
    await openApp(page, `/curriculum/versions/${fixture.versionId}/credits`);
    await expect(page.getByRole('heading', { level: 1, name: 'Credits and hours' })).toBeVisible();
    const modules = page.getByRole('region', { name: /Planned hours per/ });
    const row = modules.getByRole('row').filter({ hasText: fixture.moduleLabel });
    await expect(row).toBeVisible();
    await expect(row.getByText(/Planned 3 h against 20 h expected/)).toBeVisible();
    await expect(page.getByRole('region', { name: 'Credits per NQF level' })).toBeVisible();
    await expect(page.getByRole('region', { name: /Credits per year/ })).toBeVisible();
    await expectNoAccessibilityViolations(page);

    // Changing the item and deleting the assessment go through confirmations.
    await openApp(page, `/curriculum/versions/${fixture.versionId}?item=module:${fixture.moduleId}`);
    await section.getByRole('button', { name: 'Edit assessment Class test' }).click();
    const edit = page.getByRole('dialog', { name: 'Edit Class test' });
    await edit.getByRole('textbox', { name: /Weight/ }).fill('60');
    await edit.getByRole('button', { name: 'Save changes' }).click();
    await expect(section.getByText('The weights add up to 60%, not 100%.')).toBeVisible();

    await section.getByRole('button', { name: 'Delete assessment Class test' }).click();
    const confirm = page.getByRole('dialog', { name: 'Delete Class test?' });
    await expect(confirm).toBeVisible();
    await expectNoAccessibilityViolations(page);
    await confirm.getByRole('button', { name: 'Delete assessment' }).click();
    await expect(page.getByRole('status').filter({ hasText: 'Class test deleted' })).toBeVisible();
    await expect(section.getByText('No assessments yet.')).toBeVisible();
    await expect(page.getByText(/Planned 2 h against 20 h expected/)).toBeVisible();
  });

  test('the version bar links to the credits page, which has no accessibility problems', async ({
    page,
  }, testInfo) => {
    test.slow();
    fixture = await makeFixture(page, testInfo.project.name);
    await openApp(page, `/curriculum/versions/${fixture.versionId}`);

    await page.getByRole('link', { name: 'Check credits' }).click();

    await expect(page.getByRole('heading', { level: 1, name: 'Credits and hours' })).toBeVisible();
    await expect(page.getByText(/One credit is 10 notional hours/)).toBeVisible();
    await expectNoAccessibilityViolations(page);
  });
});
