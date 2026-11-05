import { expect, test } from '@playwright/test';

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
