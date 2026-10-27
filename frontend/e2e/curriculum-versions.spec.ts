import { expect, test, type Page } from '@playwright/test';

import { expectNoAccessibilityViolations, openApp } from './support';

// Runs against the demo programme (load-demo): a published version for the current year
// and a draft for the next year, copied forward from it with a few changes. The
// publishing journey copies the draft to a far-away academic year of its own, works on
// that copy and deletes it afterwards; the comparison journey only reads.
const PROGRAMME = 'BSc Health Sciences (Demo)';
const API = '/api/v1';

interface Version {
  id: string;
  academic_year: number;
  status: string;
}

async function versions(page: Page): Promise<Version[]> {
  const programmes = (await (await page.request.get(`${API}/programmes`)).json()) as {
    name: string;
    versions: Version[];
  }[];
  return programmes.find((p) => p.name === PROGRAMME)!.versions;
}

/** A free year far from the demo's, different for the light and dark projects. */
function journeyYear(project: string): number {
  return (project === 'dark' ? 2150 : 2100) + (Date.now() % 40);
}

test.describe('curriculum versions', () => {
  let created: number | null = null;

  test.afterEach(async ({ page }) => {
    if (created === null) return;
    await openApp(page, '/');
    const cookies = await page.context().cookies();
    const csrf = cookies.find((cookie) => cookie.name === 'ocmp_csrf')!.value;
    const found = (await versions(page)).find((v) => v.academic_year === created);
    // Drafts can be deleted; a version the journey left published goes back to draft first.
    if (found?.status === 'published') {
      await page.request.post(`${API}/curriculum-versions/${found.id}/status`, {
        headers: { 'X-CSRF-Token': csrf },
        data: { status: 'draft' },
      });
    }
    if (found) {
      await page.request.delete(`${API}/curriculum-versions/${found.id}`, {
        headers: { 'X-CSRF-Token': csrf },
      });
    }
    created = null;
  });

  test('copies a year forward, publishes it, returns it to draft and deletes it', async ({
    page,
  }, testInfo) => {
    test.slow();
    await openApp(page, '/curriculum');
    const draft = (await versions(page)).find((v) => v.status === 'draft')!;
    await openApp(page, `/curriculum/versions/${draft.id}`);
    await expect(page.getByRole('group', { name: 'Version actions' })).toBeVisible();

    // The copy dialog: counts, role assignments, and a year that must be free.
    const year = journeyYear(testInfo.project.name);
    await page.getByRole('button', { name: 'Copy forward' }).click();
    const dialog = page.getByRole('dialog', { name: /Copy the \d{4} draft forward/ });
    const yearField = dialog.getByRole('textbox', { name: /Academic year/ });
    await expect(yearField).toBeFocused();
    await expect(dialog.getByRole('definition').first()).toBeVisible();
    await expectNoAccessibilityViolations(page);
    await yearField.fill(String(draft.academic_year));
    await dialog.getByRole('button', { name: 'Copy forward' }).click();
    await expect(dialog.getByText('This year already has a version.')).toBeVisible();
    await expectNoAccessibilityViolations(page);
    await yearField.fill(String(year));
    await dialog.getByRole('button', { name: 'Copy forward' }).click();
    created = year;

    // The new draft opens with a notice, and can be edited.
    await expect(page).toHaveURL(/\/curriculum\/versions\/[0-9a-f-]+$/);
    const notice = page.getByRole('status').filter({ hasText: `${year} draft created` });
    await expect(notice).toBeVisible();
    await expect(page.getByRole('group', { name: 'Version actions' })).toContainText('Delete draft');
    await expect(page.getByRole('group', { name: 'Changes' })).toBeVisible();
    await expectNoAccessibilityViolations(page);

    // Publish after confirming; the version becomes read-only.
    await page.getByRole('button', { name: 'Publish version' }).click();
    const publish = page.getByRole('dialog', { name: `Publish the ${year} draft?` });
    await expect(publish).toBeVisible();
    await expectNoAccessibilityViolations(page);
    await publish.getByRole('button', { name: 'Publish version' }).click();
    await expect(page.getByRole('status').filter({ hasText: `${year} published.` })).toBeVisible();
    await expect(page.getByText(/read-only and visible to students/)).toBeVisible();
    await expect(page.getByRole('group', { name: 'Changes' })).toBeHidden();
    await expect(page.getByRole('button', { name: 'Delete draft' })).toBeHidden();
    await expectNoAccessibilityViolations(page);

    // Back to draft, then delete it.
    await page.getByRole('button', { name: 'Return to draft' }).click();
    const unpublish = page.getByRole('dialog', { name: `Return the ${year} published to draft?` });
    // A written reason is required; it goes into the change history.
    await unpublish.getByRole('button', { name: 'Return to draft' }).click();
    await expect(unpublish.getByText('Give a reason.')).toBeVisible();
    await expectNoAccessibilityViolations(page);
    await unpublish.getByRole('textbox', { name: /Reason/ }).fill('Checking the unpublish journey.');
    await unpublish.getByRole('button', { name: 'Return to draft' }).click();
    await expect(page.getByRole('status').filter({ hasText: `${year} returned to draft.` })).toBeVisible();
    await page.getByRole('button', { name: 'Delete draft' }).click();
    const remove = page.getByRole('dialog', { name: `Delete the ${year} draft?` });
    await expect(remove).toBeVisible();
    await expectNoAccessibilityViolations(page);
    await remove.getByRole('button', { name: 'Delete draft' }).click();
    created = null;
    await expect(page.getByRole('status').filter({ hasText: 'was deleted' })).toBeVisible();
    expect((await versions(page)).some((v) => v.academic_year === year)).toBe(false);
  });

  test('compares the draft with the published version it was copied from', async ({ page }) => {
    await openApp(page, '/curriculum');
    const draft = (await versions(page)).find((v) => v.status === 'draft')!;
    await openApp(page, `/curriculum/versions/${draft.id}`);

    await page.getByRole('link', { name: 'Compare versions' }).click();

    await expect(page.getByRole('heading', { level: 1, name: 'Compare versions' })).toBeVisible();
    await expect(page.getByRole('heading', { level: 2, name: /Changes from .* published to/ }))
      .toBeVisible();
    const sessions = page.getByRole('region', { name: 'Sessions' });
    await expect(sessions.getByText('The nervous system')).toBeVisible();
    await expect(sessions.getByText('Portfolio reflection')).toBeVisible();
    await expect(sessions.getByText('Reading and summarising a research paper', { exact: true })).toBeVisible();
    await expect(page.getByRole('combobox', { name: 'Compare with' })).toHaveValue(/.+/);
    await expectNoAccessibilityViolations(page);

    await page.getByRole('link', { name: 'Back to the builder' }).click();
    await expect(page.getByRole('tree', { name: `Structure of ${PROGRAMME}` })).toBeVisible();
  });
});
