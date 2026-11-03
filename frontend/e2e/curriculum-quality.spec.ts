import { expect, test, type APIRequestContext, type Page } from '@playwright/test';

import { demoDraft, expectNoAccessibilityViolations, openApp } from './support';

// Runs against the demo programme (load-demo) as the test admin. Each journey makes its
// own uniquely named phase, module and session through the API, works on those only (the
// other journeys run in parallel) and deletes them afterwards.
const PROGRAMME = 'BSc Health Sciences (Demo)';
const API = '/api/v1';

interface Fixture {
  versionId: string;
  phaseId: string;
  moduleId: string;
  eventId: string;
  suffix: string;
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
    { name: `Quality ${suffix}`, kind: 'block' }
  );
  const module = await post<{ id: string }>(
    page.request,
    headers,
    `/curriculum-versions/${versionId}/modules`,
    { code: `QC-${suffix}`, name: 'Quality module', phase_id: phase.id }
  );
  const event = await post<{ id: string }>(
    page.request,
    headers,
    `/modules/${module.id}/learning-events`,
    { title: 'Quality session' }
  );
  return { versionId, phaseId: phase.id, moduleId: module.id, eventId: event.id, suffix };
}

async function cleanUp(page: Page, fixture: Fixture) {
  const headers = await csrfHeaders(page);
  // Deleting the module takes its sessions and their objectives with it.
  await page.request.delete(`${API}/modules/${fixture.moduleId}`, { headers });
  await page.request.delete(`${API}/phases/${fixture.phaseId}`, { headers });
}

test.describe('objective quality checker', () => {
  let fixture: Fixture | null = null;

  test.afterEach(async ({ page }) => {
    if (fixture) await cleanUp(page, fixture);
    fixture = null;
  });

  test('checks the wording as you type, suggests a level and never blocks saving', async ({
    page,
  }, testInfo) => {
    test.slow();
    fixture = await makeFixture(page, testInfo.project.name);
    await openApp(page, `/curriculum/versions/${fixture.versionId}?item=event:${fixture.eventId}`);

    await page.getByRole('button', { name: 'Add objective' }).click();
    const dialog = page.getByRole('dialog', { name: 'Add objective' });
    const quality = dialog.getByRole('region', { name: 'Quality check' });
    await expect(quality.getByText('Type the wording to see suggestions.')).toBeVisible();
    // The test admin also holds the AI permission, so the AI help box is there (its buttons are
    // off until there is wording; nothing is ever asked of the AI in this journey).
    const aiHelp = dialog.getByRole('group', { name: 'AI help with this wording' });
    await expect(aiHelp).toBeVisible();
    await expect(aiHelp.getByRole('button', { name: 'Suggest a measurable rewrite' })).toBeDisabled();
    await expectNoAccessibilityViolations(page);

    // Vague and double-barrelled wording: warnings, written out and with icons.
    const wording = dialog.getByRole('textbox', { name: /Wording/ });
    await wording.fill(`Understand the heart and explain its valves ${fixture.suffix}.`);
    await expect(quality.getByRole('status')).toContainText('Warnings:', { timeout: 15_000 });
    await expect(quality.getByText('Vague verb: understand.')).toBeVisible();
    await expect(quality.getByText('Warning', { exact: true }).first()).toBeVisible();
    await expectNoAccessibilityViolations(page);

    // A clean verb points to a level; it is set only when clicked.
    await wording.fill(`Explain the heart valves ${fixture.suffix}.`);
    const use = quality.getByRole('button', { name: /^Use Understand/ });
    await expect(use).toBeVisible({ timeout: 15_000 });
    const level = dialog.getByRole('combobox', { name: 'Taxonomy level' });
    await expect(level).toHaveValue('');
    await expectNoAccessibilityViolations(page);
    await use.click();
    await expect(level.locator('option:checked')).toHaveText('Understand');
    await expect(use).toBeHidden();

    // Findings are advice: wording with warnings still saves.
    await wording.fill(`Understand the valves ${fixture.suffix}.`);
    await expect(quality.getByText('Vague verb: understand.')).toBeVisible({ timeout: 15_000 });
    await dialog.getByRole('button', { name: 'Add objective' }).click();
    await expect(
      page.getByRole('status').filter({ hasText: 'The objective was added.' })
    ).toBeVisible();
  });

  test('lists findings for every objective with filters and a link to edit', async ({
    page,
  }, testInfo) => {
    test.slow();
    fixture = await makeFixture(page, testInfo.project.name);
    const headers = await csrfHeaders(page);
    const vagueText = `Appreciate the value of teamwork ${fixture.suffix}`;
    await post(page.request, headers, `/learning-events/${fixture.eventId}/objectives`, {
      text: vagueText,
    });
    await post(page.request, headers, `/learning-events/${fixture.eventId}/objectives`, {
      text: `Explain the heart valves ${fixture.suffix}.`,
      domain: 'knowledge',
    });

    await openApp(page, `/curriculum/versions/${fixture.versionId}`);
    await page.getByRole('link', { name: 'Check wording' }).click();
    await expect(page.getByRole('heading', { level: 1, name: 'Objective quality' })).toBeVisible();
    const row = page.getByRole('listitem').filter({ hasText: vagueText });
    await expect(row).toBeVisible();
    await expect(row.getByText('Vague verb: appreciate.')).toBeVisible();
    await expectNoAccessibilityViolations(page);

    // Filter by rule: only objectives with that finding remain.
    await page.getByRole('combobox', { name: 'Rule' }).selectOption({ label: 'Vague verb' });
    await expect(row).toBeVisible();
    await expect(
      page.getByRole('listitem').filter({ hasText: `Explain the heart valves ${fixture.suffix}.` })
    ).toBeHidden();
    await expectNoAccessibilityViolations(page);

    // A rule nothing breaks gives an explained empty state.
    await page.getByRole('combobox', { name: 'Rule' }).selectOption({ label: 'Too long' });
    await expect(page.getByRole('heading', { name: 'Nothing matches' })).toBeVisible();
    await expectNoAccessibilityViolations(page);

    // From a finding to the item that holds the objective.
    await page.getByRole('combobox', { name: 'Rule' }).selectOption({ label: 'Vague verb' });
    await row.getByRole('link', { name: /Open in the curriculum/ }).click();
    await expect(page).toHaveURL(new RegExp(`item=event%3A${fixture.eventId}`));
    await expect(page.getByText(vagueText)).toBeVisible();
  });
});
