import { expect, request, test, type APIRequestContext } from '@playwright/test';

import {
  demoDraft,
  expectNoAccessibilityViolations,
  LECTURER_EMAIL,
  LECTURER_STATE,
  openApp,
  SIGNED_IN_STATE,
  tick,
} from './support';

// A lecturer who holds only a role on one session. The test admin (saved session) makes a
// uniquely named phase, module, session, module outcome and programme outcome through the
// API, grants the lecturer role on the session, and removes everything afterwards. The
// lecturer's own saved session is used for the browser (never sign in inside a test).
test.use({ storageState: LECTURER_STATE });

const PROGRAMME = 'BSc Health Sciences (Demo)';
const API = '/api/v1';

interface Fixture {
  versionId: string;
  phaseId: string;
  moduleId: string;
  eventId: string;
  programmeOutcomeId: string;
  assignmentId: string;
  programmeOutcomeText: string;
  moduleOutcomeText: string;
}

async function adminApi(baseURL: string | undefined) {
  const api = await request.newContext({
    baseURL,
    ignoreHTTPSErrors: true,
    storageState: SIGNED_IN_STATE,
  });
  const csrf = (await api.storageState()).cookies.find((cookie) => cookie.name === 'ocmp_csrf');
  if (!csrf) throw new Error('No CSRF cookie: is the admin session valid?');
  return { api, headers: { 'X-CSRF-Token': csrf.value } };
}

async function post<T>(
  api: APIRequestContext,
  headers: Record<string, string>,
  path: string,
  data: object
) {
  const response = await api.post(`${API}${path}`, { headers, data });
  expect(response.status(), await response.text()).toBe(201);
  return (await response.json()) as T;
}

async function makeFixture(
  api: APIRequestContext,
  headers: Record<string, string>,
  project: string
): Promise<Fixture> {
  const programmes = (await (await api.get(`${API}/programmes`)).json()) as {
    name: string;
    versions: { id: string; status: string; academic_year: number }[];
  }[];
  const versionId = demoDraft(programmes.find((p) => p.name === PROGRAMME)!.versions);
  const suffix = `${project}-${Date.now() % 1_000_000}`;
  const phase = await post<{ id: string }>(
    api,
    headers,
    `/curriculum-versions/${versionId}/phases`,
    { name: `Lecturer ${suffix}`, kind: 'block' }
  );
  const module = await post<{ id: string }>(
    api,
    headers,
    `/curriculum-versions/${versionId}/modules`,
    { code: `LE-${suffix}`, name: 'Lecturer module', phase_id: phase.id }
  );
  const event = await post<{ id: string }>(
    api,
    headers,
    `/modules/${module.id}/learning-events`,
    { title: 'Lecturer session' }
  );
  const programmeOutcomeText = `Programme outcome ${suffix}`;
  const moduleOutcomeText = `Module outcome ${suffix}`;
  const programmeOutcome = await post<{ id: string }>(
    api,
    headers,
    `/curriculum-versions/${versionId}/outcomes`,
    { text: programmeOutcomeText }
  );
  await post<{ id: string }>(api, headers, `/modules/${module.id}/outcomes`, {
    text: moduleOutcomeText,
  });
  const users = (await (
    await api.get(`${API}/users?search=${encodeURIComponent(LECTURER_EMAIL)}`)
  ).json()) as { items: { id: string; email: string }[] };
  const lecturer = users.items.find((user) => user.email === LECTURER_EMAIL)!;
  const assignment = await post<{ id: string }>(api, headers, '/role-assignments', {
    user_id: lecturer.id,
    role_key: 'lecturer',
    scope_type: 'learning_event',
    scope_id: event.id,
  });
  return {
    versionId,
    phaseId: phase.id,
    moduleId: module.id,
    eventId: event.id,
    programmeOutcomeId: programmeOutcome.id,
    assignmentId: assignment.id,
    programmeOutcomeText,
    moduleOutcomeText,
  };
}

test('a lecturer with only a session role links a session objective upward', async ({
  page,
  baseURL,
}, testInfo) => {
  test.slow();
  const { api, headers } = await adminApi(baseURL);
  const fixture = await makeFixture(api, headers, testInfo.project.name);
  try {
    await openApp(page, `/curriculum/versions/${fixture.versionId}?item=event:${fixture.eventId}`);
    const notice = page.getByRole('status').filter({ hasText: /objective/ });

    await page.getByRole('button', { name: 'Add objective' }).click();
    const dialog = page.getByRole('dialog', { name: 'Add objective' });
    await dialog.getByRole('textbox', { name: /Wording/ }).fill('Take a pulse and record it.');

    // Read-only sight of the module's and the programme's outcomes, to choose links.
    const programmeOutcome = dialog.getByRole('checkbox', {
      name: new RegExp(fixture.programmeOutcomeText),
    });
    const moduleOutcome = dialog.getByRole('checkbox', {
      name: new RegExp(fixture.moduleOutcomeText),
    });
    await expect(programmeOutcome).toBeVisible();
    await expect(moduleOutcome).toBeVisible();
    await tick(programmeOutcome);
    await tick(moduleOutcome);

    // Only draft and ready for review can be set; approving is for coordinators.
    const status = dialog.getByRole('combobox', { name: 'Status' });
    await expect(status.getByRole('option')).toHaveText(['Draft', 'Ready for review']);
    await status.selectOption({ label: 'Ready for review' });
    await expectNoAccessibilityViolations(page);
    await dialog.getByRole('button', { name: 'Add objective' }).click();
    await expect(notice).toHaveText('The objective was added.', { timeout: 15_000 });

    const row = page.getByRole('listitem').filter({ hasText: 'Take a pulse and record it.' });
    await expect(row.getByText('Linked to 2 broader outcomes')).toBeVisible();
    await expect(row.getByText('Ready for review')).toBeVisible();
    await expectNoAccessibilityViolations(page);

    // The links can be changed again.
    await row.getByRole('button', { name: /^Edit objective/ }).click();
    const edit = page.getByRole('dialog', { name: 'Edit objective' });
    const moduleLink = edit.getByRole('checkbox', { name: new RegExp(fixture.moduleOutcomeText) });
    await expect(moduleLink).toBeChecked();
    await moduleLink.uncheck();
    await edit.getByRole('button', { name: 'Save changes' }).click();
    await expect(notice).toHaveText('Changes to the objective saved.', { timeout: 15_000 });
    await expect(
      page
        .getByRole('listitem')
        .filter({ hasText: 'Take a pulse and record it.' })
        .getByText('Linked to 1 broader outcome')
    ).toBeVisible();
  } finally {
    await api.delete(`${API}/role-assignments/${fixture.assignmentId}`, { headers });
    // Deleting the module takes its sessions and their objectives with it.
    await api.delete(`${API}/modules/${fixture.moduleId}`, { headers });
    await api.delete(`${API}/phases/${fixture.phaseId}`, { headers });
    await api.delete(`${API}/objectives/${fixture.programmeOutcomeId}`, { headers });
    await api.dispose();
  }
});
