import { expect, test } from '@playwright/test';

import {
  expectNoAccessibilityViolations,
  openApp,
  removeFramework,
  removeTagListByKey,
} from './support';

// Runs as the test admin (frameworks.manage). Each journey imports a pack with its own
// unique key, so parallel runs and reruns do not collide, and removes the framework and the
// tag list the pack created afterwards (DELETE /frameworks, ADR 037) so the demo stays clean.

function packJson(key: string, version = '1') {
  return JSON.stringify({
    format_version: 2,
    metadata: {
      key,
      name: `E2E pack ${key}`,
      version,
      publisher: 'End-to-end tests',
      licence: 'Fictional, for tests',
    },
    items: [
      { code: 'E-1', title: 'First area', order: 1 },
      { code: 'E-1.1', title: 'First competency', parent_code: 'E-1', order: 1 },
      { code: 'E-2', title: 'Second area', order: 2 },
    ],
    tag_lists: [
      { key: `${key}-themes`, name: `Themes ${key}`, kind: 'theme', values: [{ label: 'One' }] },
    ],
  });
}

test.describe('framework pack import', () => {
  const imported: { frameworkId?: string; listKey: string }[] = [];

  test.afterEach(async ({ page }) => {
    if (imported.length === 0) return;
    await openApp(page, '/');
    for (const item of imported.splice(0)) {
      if (item.frameworkId) await removeFramework(page, item.frameworkId);
      await removeTagListByKey(page, item.listKey);
    }
  });

  test('check a file, read the preview, import it', async ({ page }, testInfo) => {
    const key = `e2e-${testInfo.project.name}-${Date.now() % 10_000_000}`;
    const record: { frameworkId?: string; listKey: string } = { listKey: `${key}-themes` };
    imported.push(record);
    await openApp(page, '/import');
    await expect(page.getByRole('heading', { level: 1, name: 'Import and export' })).toBeVisible();
    await expect(page.getByRole('heading', { level: 2, name: 'Framework pack' })).toBeVisible();
    await expect(page.getByRole('link', { name: /download hpcsa core competencies/i })).toBeVisible();
    await expectNoAccessibilityViolations(page);

    await page.locator('input[type="file"]').setInputFiles({
      name: 'pack.json',
      mimeType: 'application/json',
      buffer: Buffer.from(packJson(key)),
    });
    await page.getByRole('button', { name: 'Check file' }).click();

    await expect(page.getByRole('heading', { name: 'Check the pack before importing' })).toBeVisible();
    await expect(page.getByText('3 items in 2 levels')).toBeVisible();
    await expect(page.getByText('1 tag list with 1 tags')).toBeVisible();
    const items = page.getByRole('region', { name: 'Items in the pack, in tree order' });
    await expect(items.getByText('First competency')).toBeVisible();
    await expectNoAccessibilityViolations(page);

    const importResponse = page.waitForResponse(
      (response) =>
        response.url().endsWith('/framework-packs/import') && response.request().method() === 'POST'
    );
    await page.getByRole('button', { name: 'Import framework' }).click();
    record.frameworkId = ((await (await importResponse).json()) as { framework_id: string }).framework_id;

    await expect(page.getByRole('status').filter({ hasText: `Imported E2E pack ${key}` })).toBeVisible({
      timeout: 30_000,
    });
    await expect(page.getByText('3 items added')).toBeVisible();
    await expectNoAccessibilityViolations(page);

    // The same version cannot be imported twice: the second check explains why.
    await page.getByRole('button', { name: 'Import another pack' }).click();
    await page.locator('input[type="file"]').setInputFiles({
      name: 'pack.json',
      mimeType: 'application/json',
      buffer: Buffer.from(packJson(key)),
    });
    await page.getByRole('button', { name: 'Check file' }).click();
    await expect(page.getByText('already imported')).toBeVisible();
  });

  test('a file with problems lists them and imports nothing', async ({ page }) => {
    await openApp(page, '/import');
    const broken = JSON.stringify({
      metadata: { key: 'Bad Key', name: 'Broken', version: '1', publisher: 'Tests' },
      items: [
        { code: 'A', title: 'A' },
        { code: 'B', title: '' },
      ],
    });

    await page.locator('input[type="file"]').setInputFiles({
      name: 'broken.json',
      mimeType: 'application/json',
      buffer: Buffer.from(broken),
    });
    await page.getByRole('button', { name: 'Check file' }).click();

    await expect(page.getByText('This file cannot be imported yet')).toBeVisible();
    await expect(page.getByText('metadata.key')).toBeVisible();
    await expect(page.getByText('items[1].title')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Import framework' })).toHaveCount(0);
    await expectNoAccessibilityViolations(page);

    await page.getByRole('button', { name: 'Choose another file' }).click();
    await expect(page.getByRole('button', { name: 'Check file' })).toBeVisible();
  });

  test('a blank template downloads and is refused until it is filled in', async ({ page }) => {
    await openApp(page, '/import');
    const link = page.getByRole('link', { name: /download nqf level descriptors/i });
    const href = await link.getAttribute('href');
    const response = await page.request.get(href!);
    expect(response.ok()).toBe(true);
    const template = await response.body();

    await page.locator('input[type="file"]').setInputFiles({
      name: 'nqf-level-descriptors.json',
      mimeType: 'application/json',
      buffer: template,
    });
    await page.getByRole('button', { name: 'Check file' }).click();

    await expect(page.getByText(/this is a blank template/i)).toBeVisible();
    await expect(page.getByRole('button', { name: 'Import framework' })).toHaveCount(0);
    await expectNoAccessibilityViolations(page);
  });
});
