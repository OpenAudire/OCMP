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
    const link = page.getByRole('link', { name: 'Download the Excel template', exact: true });
    const href = (await link.getAttribute('href')) as string;
    const template = await page.request.get(href);
    expect(template.status()).toBe(200);
    expect(template.headers()['content-type']).toContain('spreadsheetml');
    await expectNoAccessibilityViolations(page);

    await page.locator('input[type="file"]').first().setInputFiles({
      name: 'blank-template.xlsx',
      mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      buffer: await template.body(),
    });
    await page.getByRole('button', { name: 'Check the file' }).click();

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
});

