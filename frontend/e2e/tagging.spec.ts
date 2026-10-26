import { expect, test, type APIRequestContext, type Page } from '@playwright/test';

import {
  demoDraft,
  expectNoAccessibilityViolations,
  openApp,
  removeTagListByKey,
} from './support';

// Runs against the demo programme (load-demo) as the test admin. Each journey makes its
// own uniquely named tag list, module and sessions through the API, works on those only
// (the other journeys run in parallel) and removes them afterwards.
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

interface TagFixture {
  versionId: string;
  phaseId: string;
  moduleId: string;
  moduleLabel: string;
  eventId: string;
  eventTitle: string;
  listId: string;
  listName: string;
  valueId: string;
  tagLabel: string;
}

async function makeFixture(page: Page, project: string): Promise<TagFixture> {
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
    { name: `Tagging ${suffix}`, kind: 'block' }
  );
  const module = await post<{ id: string }>(
    page.request,
    headers,
    `/curriculum-versions/${versionId}/modules`,
    { code: `TG-${suffix}`, name: 'Tagging module', phase_id: phase.id }
  );
  const eventTitle = `Tagging session ${suffix}`;
  const event = await post<{ id: string }>(
    page.request,
    headers,
    `/modules/${module.id}/learning-events`,
    { title: eventTitle }
  );
  const list = await post<{ id: string }>(page.request, headers, '/tag-lists', {
    key: `tg-${suffix}`.toLowerCase(),
    name: `Methods ${suffix}`,
    kind: 'custom',
  });
  const tagLabel = `Tag ${suffix}`;
  const value = await post<{ id: string }>(page.request, headers, `/tag-lists/${list.id}/values`, {
    label: tagLabel,
  });
  return {
    versionId,
    phaseId: phase.id,
    moduleId: module.id,
    moduleLabel: `TG-${suffix} Tagging module`,
    eventId: event.id,
    eventTitle,
    listId: list.id,
    listName: `Methods ${suffix}`,
    valueId: value.id,
    tagLabel,
  };
}

async function cleanUp(page: Page, fixture: TagFixture) {
  const headers = await csrfHeaders(page);
  // Deleting the module leaves its taggings behind, so make the tag unused first by
  // removing the direct tag of the module and the session through the page's own data.
  const module = (await (await page.request.get(`${API}/modules/${fixture.moduleId}`)).json()) as {
    tags?: { direct_tagging_id: string | null }[];
  };
  for (const tag of module.tags ?? []) {
    if (tag.direct_tagging_id) {
      await page.request.delete(`${API}/taggings/${tag.direct_tagging_id}`, { headers });
    }
  }
  const event = (await (await page.request.get(`${API}/learning-events/${fixture.eventId}`)).json()) as {
    tags?: { direct_tagging_id: string | null }[];
  };
  for (const tag of event.tags ?? []) {
    if (tag.direct_tagging_id) {
      await page.request.delete(`${API}/taggings/${tag.direct_tagging_id}`, { headers });
    }
  }
  await page.request.delete(`${API}/modules/${fixture.moduleId}`, { headers });
  await page.request.delete(`${API}/phases/${fixture.phaseId}`, { headers });
  await page.request.delete(`${API}/tag-values/${fixture.valueId}`, { headers });
  await page.request.delete(`${API}/tag-lists/${fixture.listId}`, { headers });
}

test.describe('tagging', () => {
  let fixture: TagFixture | null = null;

  test.afterEach(async ({ page }) => {
    if (fixture) await cleanUp(page, fixture);
    fixture = null;
  });

  test('tags a module, previews and passes the tag to its sessions, then removes it', async ({
    page,
  }, testInfo) => {
    test.slow();
    fixture = await makeFixture(page, testInfo.project.name);
    await openApp(page, `/curriculum/versions/${fixture.versionId}?item=module:${fixture.moduleId}`);

    const add = page.getByRole('button', { name: `Add tag to ${fixture.moduleLabel}` });
    await add.click();
    const dialog = page.getByRole('dialog', { name: `Add a tag to ${fixture.moduleLabel}` });
    await expectNoAccessibilityViolations(page);

    // Nothing chosen: the dialog says so and saves nothing.
    await dialog.getByRole('button', { name: 'Add tag' }).click();
    await expect(dialog.getByText('Fill in this field.')).toBeVisible();
    await expectNoAccessibilityViolations(page);

    // Choosing the tag lists the session it would reach before anything is saved.
    await dialog.getByRole('combobox', { name: /Tag/ }).selectOption({ label: fixture.tagLabel });
    await expect(dialog.getByText(fixture.eventTitle)).toBeVisible();
    await expect(dialog.getByText('Will get the tag')).toBeVisible();
    const inherit = dialog.getByRole('checkbox', { name: /Also give this tag to the 1 item/ });
    await expect(inherit).toBeChecked();
    await expectNoAccessibilityViolations(page);
    await dialog.getByRole('button', { name: 'Add tag' }).click();

    const notice = page.getByRole('status').filter({ hasText: /passed on to 1 other item/ });
    await expect(notice).toBeVisible();
    const group = page.getByRole('group', { name: `Tags of ${fixture.moduleLabel}` });
    await expect(group.getByText(fixture.tagLabel)).toBeVisible();
    await expectNoAccessibilityViolations(page);

    // The session shows the tag with its source and no Remove button.
    await openApp(page, `/curriculum/versions/${fixture.versionId}?item=event:${fixture.eventId}`);
    const sessionTags = page.getByRole('group', { name: `Tags of ${fixture.eventTitle}` });
    await expect(sessionTags.getByText(fixture.tagLabel)).toBeVisible();
    await expect(sessionTags.getByText(/Inherited from .* TG-.* Tagging module/)).toBeVisible();
    await expect(sessionTags.getByRole('button', { name: /^Remove tag/ })).toHaveCount(0);
    await expectNoAccessibilityViolations(page);

    // Removing it at the module takes it off the session too.
    await openApp(page, `/curriculum/versions/${fixture.versionId}?item=module:${fixture.moduleId}`);
    await page
      .getByRole('button', { name: `Remove tag ${fixture.tagLabel} from ${fixture.moduleLabel}` })
      .click();
    await expect(
      page.getByRole('status').filter({ hasText: `Tag ${fixture.tagLabel} removed` })
    ).toBeVisible();
    await openApp(page, `/curriculum/versions/${fixture.versionId}?item=event:${fixture.eventId}`);
    await expect(
      page.getByRole('group', { name: `Tags of ${fixture.eventTitle}` }).getByText('No tags yet.')
    ).toBeVisible();
  });

  test('passes a tag on to a session added after the module was tagged', async ({
    page,
  }, testInfo) => {
    test.slow();
    fixture = await makeFixture(page, testInfo.project.name);
    const headers = await csrfHeaders(page);
    await openApp(page, `/curriculum/versions/${fixture.versionId}?item=module:${fixture.moduleId}`);

    // Tag the module without giving the tag to its session.
    await page.getByRole('button', { name: `Add tag to ${fixture.moduleLabel}` }).click();
    const dialog = page.getByRole('dialog', { name: `Add a tag to ${fixture.moduleLabel}` });
    await dialog.getByRole('combobox', { name: /Tag/ }).selectOption({ label: fixture.tagLabel });
    await dialog.getByRole('checkbox', { name: /Also give this tag to the 1 item/ }).uncheck();
    await dialog.getByRole('button', { name: 'Add tag' }).click();
    await expect(
      page.getByRole('status').filter({ hasText: `Tag ${fixture.tagLabel} added to` })
    ).toBeVisible();

    // The existing session was left out on purpose; it is the item the notice counts.
    const group = page.getByRole('group', { name: `Tags of ${fixture.moduleLabel}` });
    await expect(group.getByText(/has not reached 1 newer item below/)).toBeVisible();
    await expectNoAccessibilityViolations(page);

    await group
      .getByRole('button', {
        name: `Pass it on: tag ${fixture.tagLabel} of ${fixture.moduleLabel} to newer items`,
      })
      .click();
    const pass = page.getByRole('dialog', {
      name: `Pass ${fixture.tagLabel} on from ${fixture.moduleLabel}`,
    });
    await expect(pass.getByText(fixture.eventTitle)).toBeVisible();
    await expect(pass.getByText('Will get the tag')).toBeVisible();
    await expectNoAccessibilityViolations(page);
    await pass.getByRole('button', { name: 'Pass on to 1 item' }).click();

    await expect(
      page.getByRole('status').filter({ hasText: `passed on from ${fixture.moduleLabel} to 1 item` })
    ).toBeVisible();
    await expect(group.getByText(/has not reached/)).toHaveCount(0);

    // The session now carries the tag, with the module as its source.
    await openApp(page, `/curriculum/versions/${fixture.versionId}?item=event:${fixture.eventId}`);
    const sessionTags = page.getByRole('group', { name: `Tags of ${fixture.eventTitle}` });
    await expect(sessionTags.getByText(fixture.tagLabel)).toBeVisible();
    await expect(sessionTags.getByText(/Inherited from .* TG-.* Tagging module/)).toBeVisible();

    // A session added later has not been reached either.
    await post(page.request, headers, `/modules/${fixture.moduleId}/learning-events`, {
      title: `Later session ${fixture.eventTitle}`,
    });
    await openApp(page, `/curriculum/versions/${fixture.versionId}?item=module:${fixture.moduleId}`);
    await expect(
      page
        .getByRole('group', { name: `Tags of ${fixture.moduleLabel}` })
        .getByText(/has not reached 1 newer item below/)
    ).toBeVisible();
  });

  test('tags a session on its own', async ({ page }, testInfo) => {
    test.slow();
    fixture = await makeFixture(page, testInfo.project.name);
    await openApp(page, `/curriculum/versions/${fixture.versionId}?item=event:${fixture.eventId}`);

    await page.getByRole('button', { name: `Add tag to ${fixture.eventTitle}` }).click();
    const dialog = page.getByRole('dialog', { name: `Add a tag to ${fixture.eventTitle}` });
    await dialog.getByRole('combobox', { name: /Tag/ }).selectOption({ label: fixture.tagLabel });
    // A session passes its tag to nothing, so there is no preview.
    await expect(dialog.getByRole('checkbox')).toHaveCount(0);
    await expectNoAccessibilityViolations(page);
    await dialog.getByRole('button', { name: 'Add tag' }).click();

    await expect(
      page.getByRole('status').filter({ hasText: `Tag ${fixture.tagLabel} added to` })
    ).toBeVisible();
    await expect(
      page.getByRole('group', { name: `Tags of ${fixture.eventTitle}` }).getByText(fixture.tagLabel)
    ).toBeVisible();
  });
});

test.describe('tag lists screen', () => {
  let screenKey: string | null = null;

  // The journey deletes its list through the screen; if it fails halfway, remove it here.
  test.afterEach(async ({ page }) => {
    if (screenKey === null) return;
    await openApp(page, '/');
    await removeTagListByKey(page, screenKey);
    screenKey = null;
  });

  test('adds, makes inactive and deletes a list and its tag', async ({ page }, testInfo) => {
    test.slow();
    const suffix = `${testInfo.project.name}-${Date.now() % 1_000_000}`;
    screenKey = `screen-${suffix}`.toLowerCase();
    const name = `Screen list ${suffix}`;
    await openApp(page, '/admin');
    await page.getByRole('link', { name: 'Tag lists' }).click();
    await expect(page.getByRole('heading', { level: 1, name: 'Tag lists' })).toBeVisible();
    await expectNoAccessibilityViolations(page);

    await page.getByRole('button', { name: 'New tag list' }).first().click();
    const dialog = page.getByRole('dialog', { name: 'New tag list' });
    await dialog.getByRole('button', { name: 'New tag list' }).click();
    await expect(dialog.getByText('Fill in this field.').first()).toBeVisible();
    await expectNoAccessibilityViolations(page);
    await dialog.getByRole('textbox', { name: /Name/ }).fill(name);
    await dialog.getByRole('textbox', { name: /Key/ }).fill(screenKey);
    await dialog.getByRole('button', { name: 'New tag list' }).click();
    await expect(page.getByRole('status').filter({ hasText: `Tag list ${name} added` })).toBeVisible({
      timeout: 15_000,
    });
    const card = page.getByRole('region', { name });
    await expect(card).toBeVisible();
    await expectNoAccessibilityViolations(page);

    await card.getByRole('button', { name: `Add tag to ${name}` }).click();
    const tagDialog = page.getByRole('dialog', { name: `Add a tag to ${name}` });
    await tagDialog.getByRole('textbox', { name: /Label/ }).fill('Screen tag');
    await expectNoAccessibilityViolations(page);
    await tagDialog.getByRole('button', { name: 'Add tag' }).click();
    await expect(card.getByText('Screen tag')).toBeVisible();
    await expect(card.getByText('Not used yet')).toBeVisible();

    await card.getByRole('button', { name: 'Make inactive: tag Screen tag' }).click();
    await expect(card.getByText('Inactive').first()).toBeVisible();
    await expectNoAccessibilityViolations(page);

    await card.getByRole('button', { name: 'Delete tag Screen tag' }).click();
    const confirm = page.getByRole('dialog', { name: 'Delete Screen tag?' });
    await expectNoAccessibilityViolations(page);
    await confirm.getByRole('button', { name: 'Delete Screen tag' }).click();
    await expect(page.getByRole('status').filter({ hasText: 'Tag Screen tag deleted' })).toBeVisible();

    await card.getByRole('button', { name: `Delete list ${name}` }).click();
    await page
      .getByRole('dialog', { name: `Delete ${name}?` })
      .getByRole('button', { name: `Delete ${name}` })
      .click();
    await expect(page.getByRole('region', { name })).toHaveCount(0);
    await expectNoAccessibilityViolations(page);
  });
});
