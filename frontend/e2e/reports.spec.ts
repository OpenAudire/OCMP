import { expect, test } from '@playwright/test';

import { expectNoAccessibilityViolations, openApp } from './support';

// The coverage and gap reports (Slice 1.21) on the demo programme as the test admin. They only
// read: nothing is created, so nothing has to be removed afterwards (ADR 037). The demo framework
// has no mapping that was accepted in bulk, so the journey checks that the report states what
// it is and that its parts are there, not particular figures.
test.describe('Reports', () => {
  test('the coverage report states its method, shows the summary, the heatmap and the items', async ({
    page,
  }) => {
    await openApp(page, '/reports');
    await expect(page.getByRole('heading', { level: 1, name: 'Reports' })).toBeVisible();
    await page.getByRole('link', { name: 'Open the report' }).first().click();

    await expect(page.getByRole('heading', { level: 1, name: 'Coverage report' })).toBeVisible();
    const panel = page.getByLabel('The method and what it covers');
    await expect(panel).toBeVisible();
    await expect(panel).toContainText('Single match');
    await expect(panel).toContainText('covered when at least one accepted link');
    await expect(panel).toContainText('Made on');
    await expect(
      page.getByRole('heading', { level: 2, name: 'Summary of the framework' })
    ).toBeVisible();
    await expect(page.getByRole('heading', { level: 2, name: /^Heatmap/ })).toBeVisible();
    await expect(page.getByRole('heading', { level: 2, name: 'Items' })).toBeVisible();
    await expectNoAccessibilityViolations(page);

    // The report can be downloaded as Excel and as PDF, and the files are real.
    const excel = page.getByRole('link', { name: /Download as Excel/ });
    const pdf = page.getByRole('link', { name: /Download as PDF/ });
    await expect(excel).toBeVisible();
    const workbook = await page.request.get((await excel.getAttribute('href')) as string);
    expect(workbook.status()).toBe(200);
    expect(workbook.headers()['content-type']).toContain('spreadsheetml');
    const file = await page.request.get((await pdf.getAttribute('href')) as string);
    expect(file.status()).toBe(200);
    expect((await file.body()).subarray(0, 4).toString()).toBe('%PDF');

    // Another method changes the definition on the page and in the address.
    await page.getByLabel('Method', { exact: true }).selectOption('weighted');
    await expect(page).toHaveURL(/method=weighted/);
    await expect(panel).toContainText('Weighted content coverage');
    await expect(panel).toContainText('add up to at most 100%');
    await expectNoAccessibilityViolations(page);
  });

  test('the gap report lists items and objectives that are not covered', async ({ page }) => {
    await openApp(page, '/reports/gaps');

    await expect(page.getByRole('heading', { level: 1, name: 'Gap report' })).toBeVisible();
    await expect(page.getByLabel('The method and what it covers')).toBeVisible();
    await expect(
      page.getByRole('heading', { level: 2, name: /^Items not covered/ })
    ).toBeVisible();
    await expect(
      page.getByRole('heading', { level: 2, name: /^Objectives with no mapping/ })
    ).toBeVisible();
    await expectNoAccessibilityViolations(page);
  });

  test('the redundancy and traceability reports state their method and can be downloaded', async ({
    page,
  }) => {
    await openApp(page, '/reports/traceability');

    await expect(page.getByRole('heading', { level: 1, name: 'Traceability report' })).toBeVisible();
    await expect(page.getByLabel('The method and what it covers')).toContainText('Method');
    await expect(
      page.getByRole('heading', { level: 2, name: 'From programme outcome to framework item' })
    ).toBeVisible();
    const excel = page.getByRole('link', { name: /Download as Excel/ });
    const workbook = await page.request.get((await excel.getAttribute('href')) as string);
    expect(workbook.status()).toBe(200);
    await expectNoAccessibilityViolations(page);

    await openApp(page, '/reports/redundancy');
    await expect(page.getByRole('heading', { level: 1, name: 'Taught in many sessions' })).toBeVisible();
    await expect(
      page.getByRole('heading', { level: 2, name: 'Items taught in many sessions' })
    ).toBeVisible();
    await expectNoAccessibilityViolations(page);
  });

  test('the teaching reports open and can be downloaded', async ({ page }) => {
    await openApp(page, '/reports/formats');

    await expect(
      page.getByRole('heading', { level: 1, name: 'Teaching formats and contact hours' })
    ).toBeVisible();
    await expect(
      page.getByRole('heading', { level: 2, name: 'By teaching format' })
    ).toBeVisible();
    const excel = page.getByRole('link', { name: /Download as Excel/ });
    const workbook = await page.request.get((await excel.getAttribute('href')) as string);
    expect(workbook.status()).toBe(200);
    await expectNoAccessibilityViolations(page);

    await openApp(page, '/reports/assessments');
    await expect(
      page.getByRole('heading', { level: 1, name: 'Assessment methods report' })
    ).toBeVisible();
    await expectNoAccessibilityViolations(page);
  });
});
