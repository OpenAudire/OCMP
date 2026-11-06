import { expect, test, type Page } from '@playwright/test';

import { expectNoAccessibilityViolations, openApp } from './support';

// The curriculum explorer (Slice 1.29) on the published demo version as the test admin. It only
// reads, so nothing has to be removed afterwards (ADR 037). It is built for a phone first, so the
// journey runs at phone width and also checks the page does not scroll sideways.
test.describe('Explorer', () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test('shows a week, then the modules, then one module with its sessions and assessments', async ({
    page,
  }) => {
    await openApp(page, '/explorer');
    await expect(page.getByRole('heading', { level: 1, name: 'Explorer' })).toBeVisible();
    await expect(page.getByRole('heading', { level: 2, name: /^Week \d+$/ })).toBeVisible();
    await expectNoAccessibilityViolations(page);

    await page.getByText('Modules', { exact: true }).click();
    await expect(page).toHaveURL(/view=browse/);
    const first = page.getByRole('list').getByRole('link').first();
    await expect(first).toBeVisible();
    await first.click();

    await expect(page.getByRole('heading', { level: 1 })).toContainText(/\w+/);
    await expect(page.getByRole('heading', { level: 2, name: 'What this module covers' })).toBeVisible();
    await expect(page.getByRole('heading', { level: 2, name: 'Sessions, week by week' })).toBeVisible();
    await expect(page.getByRole('heading', { level: 2, name: 'Assessments' })).toBeVisible();
    // The demo's modules carry assessments with questions, so the section is not an empty state.
    await expect(page.getByText(/[0-9]+% of the module mark/).first()).toBeVisible();
    await expectNoAccessibilityViolations(page);

    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth
    );
    expect(overflow).toBe(false);
  });

  test('offers the search and leaves out framework mappings', async ({ page }) => {
    await openApp(page, '/explorer');
    await expect(page.getByRole('link', { name: 'Search the curriculum' })).toBeVisible();
    await page.getByText('Modules', { exact: true }).click();
    await page.getByRole('list').getByRole('link').first().click();
    await expect(page.getByRole('heading', { level: 2, name: 'Assessments' })).toBeVisible();
    await expect(page.locator('#main-content').getByText(/framework/i)).toHaveCount(0);
  });
});

// "Where this year builds each competency" (Slice 1.31, ADR 061) is off until the institution switches it
// on. The journey turns it on through the settings API and always turns it off again. It runs in one
// project only, because the setting is shared by every project running at the same time.
test.describe('Explorer: competencies', () => {
  test.use({ viewport: { width: 390, height: 844 } });

  async function setSwitch(page: Page, on: boolean): Promise<void> {
    const csrf = (await page.context().cookies()).find((cookie) => cookie.name === 'ocmp_csrf');
    if (!csrf) return;
    const response = await page.request.patch('/api/v1/institution/settings', {
      headers: { 'X-CSRF-Token': csrf.value },
      data: { explorer: { show_competency_view: on } },
    });
    expect(response.ok()).toBe(true);
  }

  // eslint-disable-next-line no-empty-pattern
  test.beforeEach(({}, testInfo) => {
    test.skip(testInfo.project.name !== 'light', 'Changes an institution setting: one project only.');
  });

  test.afterEach(async ({ page }) => {
    await openApp(page, '/explorer');
    await setSwitch(page, false);
  });

  test('is not offered while the setting is off, and lists groups with no scores once it is on', async ({
    page,
  }) => {
    await openApp(page, '/explorer');
    await setSwitch(page, false);
    await page.reload();
    await expect(page.getByText('Competencies', { exact: true })).toHaveCount(0);

    await setSwitch(page, true);
    await page.reload();
    await page.getByText('Competencies', { exact: true }).click();
    await expect(page).toHaveURL(/view=built/);
    const group = page.getByRole('heading', { level: 2 }).first();
    await expect(group).toBeVisible();
    await expect(page.locator('#main-content').getByRole('link').first()).toBeVisible();
    await expect(page.locator('#main-content').getByText(/%|score|coverage|depth/i)).toHaveCount(0);
    await expectNoAccessibilityViolations(page);
  });
});
