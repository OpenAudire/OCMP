import { expect, request, test, type APIRequestContext, type Page } from '@playwright/test';

import {
  demoDraft,
  expectNoAccessibilityViolations,
  LECTURER_EMAIL,
  LECTURER_STATE,
  openApp,
  removeFramework,
} from './support';

// The review queue. A colleague who may map but not review (the test lecturer, given a custom
// role on one module) suggests three links through the API; the test admin decides on them in
// the browser by keyboard and with the buttons. Each journey makes its own uniquely named phase,
// module, objectives and a small framework, finds its own cards by their wording (the light and
// dark runs may share the queue) and removes everything afterwards, also when it fails: the
// lecturer's role and the custom role, the links (a rejected link is first reopened through the
// API, which makes it a link a person may delete), the module, the phase and the framework
// (ADR 037).
//
// It ends with the coverage report of the version, so with the structure made here and the
// mapping it is the build, map, review and report chain of the Phase 1 definition of done.
//
// Not covered here: a second reviewer actually deciding (that needs a third account; the API
// and unit tests cover it), and bulk accept with real suggestions (there is no AI yet to make
// links with a confidence; the dialog and its count are checked).
const PROGRAMME = 'BSc Health Sciences (Demo)';
const API = '/api/v1';

interface Fixture {
  versionId: string;
  phaseId: string;
  moduleId: string;
  frameworkId: string;
  roleKey: string;
  assignmentId: string;
  objectives: { id: string; text: string; itemId: string; itemCode: string; itemTitle: string }[];
}

async function csrf(api: APIRequestContext): Promise<Record<string, string>> {
  const cookie = (await api.storageState()).cookies.find((c) => c.name === 'ocmp_csrf');
  if (!cookie) throw new Error('No CSRF cookie: is the saved session valid?');
  return { 'X-CSRF-Token': cookie.value };
}

async function post<T>(api: APIRequestContext, path: string, data: object, status = 201): Promise<T> {
  const response = await api.post(`${API}${path}`, { headers: await csrf(api), data });
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
      { code: 'R-1', title: 'Review item one', order: 0 },
      { code: 'R-2', title: 'Review item two', order: 1 },
      { code: 'R-3', title: 'Review item three', order: 2 },
    ],
  });
}

/**
 * Makes the journey's data. `fixture` is filled in as each piece exists and is handed to the
 * clean-up at once, so a failure half way still removes what was made.
 */
async function makeFixture(page: Page, project: string, fixture: Fixture): Promise<void> {
  const api = page.request;
  await openApp(page, '/');
  const programmes = (await (await api.get(`${API}/programmes`)).json()) as {
    name: string;
    versions: { id: string; status: string; academic_year: number }[];
  }[];
  const versionId = demoDraft(programmes.find((p) => p.name === PROGRAMME)!.versions);
  fixture.versionId = versionId;
  const suffix = `${project}-${Date.now() % 1_000_000}`;
  const phase = await post<{ id: string }>(api, `/curriculum-versions/${versionId}/phases`, {
    name: `Review ${suffix}`,
    kind: 'block',
  });
  fixture.phaseId = phase.id;
  const module = await post<{ id: string }>(api, `/curriculum-versions/${versionId}/modules`, {
    code: `RV-${suffix}`,
    name: 'Review module',
    phase_id: phase.id,
  });
  fixture.moduleId = module.id;

  const key = `e2e-review-${suffix}`.toLowerCase();
  const headers = await csrf(api);
  const preview = await api.post(`${API}/framework-packs/preview`, {
    headers: { ...headers, 'Content-Type': 'application/json' },
    data: packJson(key, `E2E review ${suffix}`),
  });
  expect(preview.ok(), await preview.text()).toBe(true);
  const { token } = (await preview.json()) as { token: string };
  const imported = await api.post(`${API}/framework-packs/import`, {
    headers,
    data: { token, activate: true },
  });
  expect(imported.ok(), await imported.text()).toBe(true);
  const { framework_id: frameworkId } = (await imported.json()) as { framework_id: string };
  fixture.frameworkId = frameworkId;
  const tree = (await (
    await api.get(`${API}/frameworks/${frameworkId}/items?limit=10`)
  ).json()) as { items: { id: string; code: string; title: string }[] };

  for (const [index, word] of ['one', 'two', 'three'].entries()) {
    const text = `Review journey objective ${word} ${suffix}`;
    const objective = await post<{ id: string }>(api, `/modules/${module.id}/outcomes`, { text });
    const item = tree.items.find((i) => i.code === `R-${index + 1}`)!;
    fixture.objectives.push({
      id: objective.id,
      text,
      itemId: item.id,
      itemCode: item.code,
      itemTitle: item.title,
    });
  }

  // The lecturer may map in this module but not review: a custom role says exactly that.
  const roleKey = `e2e_mapping_only_${suffix.replace(/[^a-z0-9]/gi, '_')}`.toLowerCase();
  await post(api, '/roles', {
    key: roleKey,
    name: 'E2E mapping only',
    permissions: ['curriculum.view', 'mapping.edit'],
    scope_types: ['module'],
  });
  fixture.roleKey = roleKey;
  const users = (await (
    await api.get(`${API}/users?search=${encodeURIComponent(LECTURER_EMAIL)}`)
  ).json()) as { items: { id: string; email: string }[] };
  const lecturer = users.items.find((user) => user.email === LECTURER_EMAIL)!;
  const assignment = await post<{ id: string }>(api, '/role-assignments', {
    user_id: lecturer.id,
    role_key: roleKey,
    scope_type: 'module',
    scope_id: module.id,
  });
  fixture.assignmentId = assignment.id;
}

async function cleanUp(page: Page, fixture: Fixture) {
  const api = page.request;
  await openApp(page, '/');
  const headers = await csrf(api);
  // A rejected link is hidden and cannot be deleted; adding the same pair again reopens it as a
  // link a person made, which can.
  for (const objective of fixture.objectives) {
    await api.post(`${API}/objectives/${objective.id}/mapping-links`, {
      headers,
      data: {
        framework_item_id: objective.itemId,
        coverage: 1,
        depth_match: 'matches',
        rationale: '',
      },
    });
  }
  const workspace = await api.get(`${API}/curriculum-versions/${fixture.versionId}/mapping`);
  if (workspace.ok()) {
    const data = (await workspace.json()) as {
      objectives: { links: { id: string; framework_id: string }[] }[];
    };
    for (const objective of data.objectives) {
      for (const link of objective.links) {
        if (link.framework_id === fixture.frameworkId) {
          await api.delete(`${API}/mapping-links/${link.id}`, { headers });
        }
      }
    }
  }
  if (fixture.assignmentId) {
    await api.delete(`${API}/role-assignments/${fixture.assignmentId}`, { headers });
  }
  if (fixture.roleKey) await api.delete(`${API}/roles/${fixture.roleKey}`, { headers });
  if (fixture.moduleId) await api.delete(`${API}/modules/${fixture.moduleId}`, { headers });
  if (fixture.phaseId) await api.delete(`${API}/phases/${fixture.phaseId}`, { headers });
  if (fixture.frameworkId) await removeFramework(page, fixture.frameworkId);
}

let current: Fixture | null = null;

test.describe('review queue', () => {
  test.afterEach(async ({ page }) => {
    if (!current) return;
    const fixture = current;
    current = null;
    await cleanUp(page, fixture);
  });

  test('decide on a colleague\'s suggestions by keyboard, second review and re-check', async ({
    page,
    baseURL,
  }, testInfo) => {
    // A long journey with an axe scan at every step; the suite runs it beside many others.
    test.setTimeout(180_000);
    const fixture: Fixture = {
      versionId: '',
      phaseId: '',
      moduleId: '',
      frameworkId: '',
      roleKey: '',
      assignmentId: '',
      objectives: [],
    };
    current = fixture;
    await makeFixture(page, testInfo.project.name, fixture);
    const [one, two, three] = fixture.objectives;

    // The colleague suggests three links; they cannot review, so their own queue is empty.
    const lecturer = await request.newContext({
      baseURL,
      ignoreHTTPSErrors: true,
      storageState: LECTURER_STATE,
    });
    try {
      for (const objective of fixture.objectives) {
        const made = await post<{ id: string; status: string }>(
          lecturer,
          `/objectives/${objective.id}/mapping-links`,
          {
            framework_item_id: objective.itemId,
            coverage: 3,
            depth_match: 'matches',
            rationale: `Fits ${objective.itemCode}.`,
          }
        );
        expect(made.status).toBe('suggested');
      }
      const theirs = await lecturer.get(`${API}/mapping/review-queue/count`);
      expect((await theirs.json()).total).toBe(0);
    } finally {
      await lecturer.dispose();
    }

    await openApp(page, '/mapping/review');
    await expect(page.getByRole('heading', { level: 1, name: 'Review queue' })).toBeVisible();
    const card = (text: string) =>
      page.getByRole('region', { name: 'Suggestions' }).getByRole('button', { name: new RegExp(text) });
    await expect(card(one.text)).toBeVisible();

    // The menu shows how many links wait for this person, in words as well.
    // The number is the suggestions this person can act on (not re-checks); "99+" above 99.
    const count = (await (await page.request.get(`${API}/mapping/review-queue/count`)).json()) as {
      waiting: number;
    };
    expect(count.waiting).toBeGreaterThanOrEqual(3);
    const spoken =
      count.waiting > 99
        ? 'more than 99 suggestions waiting'
        : `${count.waiting} suggestions waiting`;
    await expect(
      page.getByRole('link', { name: new RegExp(`Review queue\\s+${spoken}`) })
    ).toBeVisible();
    await expect(
      page.locator('nav').getByText(count.waiting > 99 ? '99+' : String(count.waiting), { exact: true })
    ).toBeVisible();
    await expectNoAccessibilityViolations(page);

    // Accept all confident suggestions: people's suggestions have no confidence, so nothing is
    // eligible; the dialog says so before anything is changed.
    await page.getByRole('button', { name: /^Accept all \d+% and above/ }).click();
    const dialog = page.getByRole('dialog');
    await expect(dialog.getByText(/No waiting suggestion is at 90% or above\./)).toBeVisible();
    await expect(dialog.getByText(/never accepted in bulk/)).toBeVisible();
    // The choices start at the institution's floor (80% unless the administrator changed it).
    await expect(dialog.getByRole('option')).toHaveText([
      '80% and above',
      '85% and above',
      '90% and above',
      '95% and above',
    ]);
    await expect(dialog).toBeVisible();
    await expectNoAccessibilityViolations(page);
    await page.keyboard.press('Escape');
    await expect(dialog).toBeHidden();

    // Edit and accept by keyboard: select, E for the coverage, arrow to change it, A to accept.
    await card(one.text).click();
    const detail = page.getByRole('region', { name: 'Selected suggestion' });
    await expect(detail.getByText('Why this link was suggested')).toBeVisible();
    await expect(detail.getByText(`Fits ${one.itemCode}.`)).toBeVisible();
    await expect(detail.getByText('Suggested by a person, no confidence score')).toBeVisible();
    await expectNoAccessibilityViolations(page);
    await page.keyboard.press('e');
    await expect(detail.getByLabel('3: 41 to 60%')).toBeFocused();
    await page.keyboard.press('ArrowRight');
    await expect(detail.getByLabel('4: 61 to 80%')).toBeChecked();
    await page.keyboard.press('a');
    await expect(
      page.getByText(`Accepted the link to ${one.itemCode} ${one.itemTitle}.`)
    ).toBeVisible();
    await expect(card(one.text)).toHaveCount(0);
    await expectNoAccessibilityViolations(page);

    // Reject with R.
    await card(two.text).click();
    await page.keyboard.press('r');
    await expect(
      page.getByText(`Rejected the link to ${two.itemCode} ${two.itemTitle}.`)
    ).toBeVisible();

    // Unsure: 2 asks for a second review. It is not for the person who gave the first review, so
    // their own second-review pile does not hold it.
    await card(three.text).click();
    await page.keyboard.press('2');
    await expect(
      page.getByText(`Sent the link to ${three.itemCode} ${three.itemTitle} to a second review.`)
    ).toBeVisible();
    await page.getByLabel('Show', { exact: true }).selectOption('second');
    await expect(page.getByText('Nothing is waiting for your second review')).toBeVisible();
    await expectNoAccessibilityViolations(page);

    // The decisions are what the API holds.
    const workspace = (await (
      await page.request.get(`${API}/curriculum-versions/${fixture.versionId}/mapping`)
    ).json()) as {
      objectives: {
        id: string;
        links: { framework_id: string; status: string; coverage: number }[];
      }[];
    };
    const linkOf = (id: string) =>
      workspace.objectives
        .find((o) => o.id === id)
        ?.links.find((l) => l.framework_id === fixture.frameworkId);
    expect(linkOf(one.id)).toMatchObject({ status: 'accepted', coverage: 4 });
    expect(linkOf(two.id)).toBeUndefined(); // rejected links are not mappings
    expect(linkOf(three.id)).toMatchObject({ status: 'needs_second_review' });

    // Changing the objective's wording flags its accepted link for a re-check.
    const edited = await page.request.patch(`${API}/objectives/${one.id}`, {
      headers: await csrf(page.request),
      data: { text: `${one.text} (reworded)` },
    });
    expect(edited.ok(), await edited.text()).toBe(true);
    await page.reload();
    await expect(page.getByRole('heading', { level: 1, name: 'Review queue' })).toBeVisible();
    await page.getByLabel('Show', { exact: true }).selectOption('recheck');
    await card(`${one.text} \\(reworded\\)`).click();
    await expect(
      detail.getByText(/The objective's wording changed after this link was accepted/)
    ).toBeVisible();
    await expectNoAccessibilityViolations(page);

    // Shortcuts can be turned off; then the key does nothing and the button still works.
    await page.getByLabel('Use keyboard shortcuts').uncheck();
    await expect(page.getByText(/Keyboard shortcuts are off/)).toBeVisible();
    await expectNoAccessibilityViolations(page);
    await card(`${one.text} \\(reworded\\)`).focus();
    await page.keyboard.press('a');
    await expect(page.getByText(/Confirmed that the link to/)).toHaveCount(0);
    await detail.getByRole('button', { name: 'Still fits' }).click();
    await expect(
      page.getByText(`Confirmed that the link to ${one.itemCode} ${one.itemTitle} still fits.`)
    ).toBeVisible();
    await expect(card(`${one.text} \\(reworded\\)`)).toHaveCount(0);
    await page.getByLabel('Use keyboard shortcuts').check();
    await expectNoAccessibilityViolations(page);

    // The end of the chain (build, map, review, report): the decided link is in the coverage report
    // of the version. Only the accepted link counts; the one waiting for a second review is shown
    // apart and the rejected one is not there at all.
    const report = await page.request.get(
      `${API}/curriculum-versions/${fixture.versionId}/coverage`,
      { params: { framework_id: fixture.frameworkId, method: 'single' } }
    );
    expect(report.ok(), await report.text()).toBe(true);
    const body = (await report.json()) as {
      definition: string;
      items: { code: string; links: number; waiting: number; status: string }[];
    };
    const item = (code: string) => body.items.find((i) => i.code === code);
    expect(body.definition).toContain('accepted link');
    expect(item(one.itemCode)).toMatchObject({ links: 1, status: 'covered' });
    expect(item(two.itemCode)).toMatchObject({ links: 0, waiting: 0, status: 'none' });
    expect(item(three.itemCode)).toMatchObject({ links: 0, waiting: 1, status: 'none' });
  });
});
