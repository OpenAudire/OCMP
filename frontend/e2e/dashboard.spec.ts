import { expect, test } from '@playwright/test';

import { expectNoAccessibilityViolations, openApp } from './support';

// The committee dashboard (Slice 1.28) on the demo programme as the test admin. It only reads, so
// nothing has to be removed afterwards (ADR 037). The figures depend on the demo data and on
// whether daily snapshots exist, so the journey checks that the parts are there and readable.
test.describe('Committee dashboard', () => {
  test('shows the indicators, the traceability, the comparison, the progress and the credits', async ({
    page,
  }) => {
    await openApp(page, '/dashboard');

    await expect(
      page.getByRole('heading', { level: 1, name: 'Programme committee overview' })
    ).toBeVisible();
    const indicators = page.getByRole('region', { name: 'Key indicators' });
    await expect(indicators.getByRole('article')).toHaveCount(4);
    await expect(indicators).toContainText('Objectives mapped');
    await expect(indicators).toContainText('Weighted coverage');
    await expect(
      page.getByRole('heading', { level: 2, name: /^Traceability/ })
    ).toBeVisible();
    await expect(
      page.getByRole('heading', { level: 2, name: 'Weighted coverage by competency group' })
    ).toBeVisible();
    await expect(
      page.getByRole('heading', { level: 2, name: 'Mapping progress by module' })
    ).toBeVisible();
    await expect(
      page.getByRole('heading', { level: 2, name: 'Credits and notional hours' })
    ).toBeVisible();
    await expectNoAccessibilityViolations(page);
  });

  test('the credits table can be limited to modules outside the tolerance', async ({ page }) => {
    await openApp(page, '/dashboard');
    const section = page.getByRole('region', { name: 'Credits and notional hours' });
    await expect(section.getByRole('table')).toBeVisible();
    await section.getByLabel('Only modules outside the tolerance').check();
    await expect(section.getByLabel('Only modules outside the tolerance')).toBeChecked();
    await expectNoAccessibilityViolations(page);
  });

  test('works at phone width without sideways scrolling of the page', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await openApp(page, '/dashboard');
    await expect(
      page.getByRole('heading', { level: 1, name: 'Programme committee overview' })
    ).toBeVisible();
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth
    );
    expect(overflow).toBe(false);
  });
});
