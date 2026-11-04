import { expect, test } from '@playwright/test';

import { expectNoAccessibilityViolations, openApp } from './support';

// The Excel import of a draft curriculum version (Slice 1.25). The journey downloads the real
// template, uploads it still blank and reads the answer: a blank template has no rows, so nothing
// can be imported and nothing is created (ADR 037). The importing itself is covered by the
// backend tests, which build real workbooks.
test.describe('Curriculum import from Excel', () => {
  test('the template can be downloaded and a file with nothing to import is explained', async ({
    page,
  }) => {
    await openApp(page, '/import');

    await expect(page.getByRole('heading', { level: 1, name: 'Import and export' })).toBeVisible();
    await expect(
      page.getByRole('heading', { level: 2, name: 'Curriculum from Excel' })
    ).toBeVisible();
    // The page also holds the mapping and tag cards, with buttons of the same names.
    const card = page.getByRole('region', { name: 'Curriculum from Excel' });
    const link = card.getByRole('link', { name: 'Download the Excel template', exact: true });
    const href = (await link.getAttribute('href')) as string;
    const template = await page.request.get(href);
    expect(template.status()).toBe(200);
    expect(template.headers()['content-type']).toContain('spreadsheetml');
    await expectNoAccessibilityViolations(page);

    await card.locator('input[type="file"]').setInputFiles({
      name: 'blank-template.xlsx',
      mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      buffer: await template.body(),
    });
    await card.getByRole('button', { name: 'Check the file' }).click();

    await expect(page.getByText('The file cannot be imported yet')).toBeVisible();
    await expect(page.getByText('The workbook has no rows to import.')).toBeVisible();
    await expect(
      page.getByRole('button', { name: 'Import into the curriculum' })
    ).toHaveCount(0);
    await expectNoAccessibilityViolations(page);
  });

  test('the tag and mapping templates download, and the import history is on the page', async ({
    page,
  }) => {
    await openApp(page, '/import');

    for (const name of [/Download the Excel template for tags/, /Download the Excel template for mappings/]) {
      const href = (await page.getByRole('link', { name }).getAttribute('href')) as string;
      const template = await page.request.get(href);
      expect(template.status()).toBe(200);
      expect(template.headers()['content-type']).toContain('spreadsheetml');
    }
    const framework = await page.request.get(
      (await page.getByRole('link', { name: /Excel template for a framework/ }).getAttribute('href')) as string
    );
    expect(framework.status()).toBe(200);
    await expect(page.getByRole('heading', { level: 2, name: 'Import history' })).toBeVisible();
    await expectNoAccessibilityViolations(page);
  });

  test('a curriculum version can be exported as Excel, a matrix and JSON', async ({ page }) => {
    await openApp(page, '/import');

    await expect(
      page.getByRole('heading', { level: 2, name: 'Export a curriculum version' })
    ).toBeVisible();
    const workbook = await page.request.get(
      (await page
        .getByRole('link', { name: /Download the whole version as Excel/ })
        .getAttribute('href')) as string
    );
    expect(workbook.status()).toBe(200);
    expect(workbook.headers()['content-type']).toContain('spreadsheetml');
    const matrix = await page.request.get(
      (await page
        .getByRole('link', { name: /objectives by framework items/ })
        .getAttribute('href')) as string
    );
    expect(matrix.status()).toBe(200);
    const json = await page.request.get(
      (await page
        .getByRole('link', { name: /Download the version as JSON/ })
        .getAttribute('href')) as string
    );
    expect(json.status()).toBe(200);
    expect((await json.json()).schema).toBe('ocmp.curriculum-version');
    await expectNoAccessibilityViolations(page);
  });
});

