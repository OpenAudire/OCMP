import { expect, test, type Page } from '@playwright/test';

import { expectNoAccessibilityViolations, openApp, removeFramework } from './support';

// Runs as the test admin. The first journey browses the demo framework (read only); the
// others import a pack of their own (unique key) through the API and remove it afterwards
// (DELETE /frameworks, ADR 037), also when they fail.

const IMPORTED: string[] = [];

/** A flat pack of `count` items, so the tree has to load it in windows. */
function packJson(key: string, count: number): string {
  return JSON.stringify({
    format_version: 2,
    metadata: {
      key,
      name: `E2E browse ${key}`,
      version: '1',
      publisher: 'End-to-end tests',
      licence: 'Fictional, for tests',
    },
    items: [
      { code: 'G-1', title: 'First group', order: 0 },
      { code: 'G-1.1', title: 'Gather a history', parent_code: 'G-1', order: 1 },
      ...Array.from({ length: count }, (_, n) => ({
        code: `K-${String(n + 1).padStart(3, '0')}`,
        title: `Keyword ${n + 1}`,
        order: n + 2,
      })),
    ],
  });
}

async function importPack(page: Page, key: string, count: number): Promise<string> {
  const csrf = (await page.context().cookies()).find((c) => c.name === 'ocmp_csrf')!.value;
  const headers = { 'X-CSRF-Token': csrf };
  const preview = await page.request.post('/api/v1/framework-packs/preview', {
    headers: { ...headers, 'Content-Type': 'application/json' },
    data: packJson(key, count),
  });
  expect(preview.ok()).toBe(true);
  const { token } = (await preview.json()) as { token: string };
  const imported = await page.request.post('/api/v1/framework-packs/import', {
    headers,
    data: { token, activate: false },
  });
  expect(imported.ok()).toBe(true);
  const { framework_id: id } = (await imported.json()) as { framework_id: string };
  IMPORTED.push(id);
  return id;
}

test.describe('framework library and browser', () => {
  test.afterEach(async ({ page }) => {
    if (IMPORTED.length === 0) return;
    await openApp(page, '/');
    for (const id of IMPORTED.splice(0)) await removeFramework(page, id);
  });

  test('browse the demo framework, search it and see where an item is mapped', async ({ page }) => {
    // A long journey with an axe scan at every step; the suite runs it beside many others.
    test.setTimeout(90_000);
    await openApp(page, '/frameworks');
    await expect(page.getByRole('heading', { level: 1, name: 'Frameworks' })).toBeVisible();
    const cards = page.getByRole('list', { name: 'Frameworks' });
    await expect(cards.getByText('Demo Graduate Competencies')).toBeVisible();
    await cards.getByRole('button', { name: /Demo Graduate Competencies/ }).click();
    const details = page.getByRole('region', { name: 'Framework details' });
    await expect(details.getByText('CC0 - Public Domain', { exact: false })).toBeVisible();
    await expectNoAccessibilityViolations(page);

    await details
      .getByRole('link', { name: /Browse Demo Graduate Competencies version/ })
      .first()
      .click();
    const tree = page.getByRole('tree', { name: 'Demo Graduate Competencies items' });
    await expect(tree.getByRole('treeitem')).toHaveCount(2);
    await expectNoAccessibilityViolations(page);

    // Keyboard: open the first group, move into it and select its first child.
    await tree.getByRole('treeitem').first().focus();
    await page.keyboard.press('ArrowRight');
    await expect(tree.getByRole('treeitem', { name: /Analysis/ })).toBeVisible();
    await page.keyboard.press('ArrowRight');
    await page.keyboard.press('ArrowDown');
    await page.keyboard.press('ArrowUp');
    await expect(tree.getByRole('treeitem', { name: /Analysis/ })).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(page.getByRole('heading', { level: 2, name: /Analysis/ })).toBeVisible();
    await expect(page).toHaveURL(/item=/);

    // The demo maps objectives to this item; the admin sees them, read only.
    const mapped = page.getByRole('list', { name: 'Objectives mapped to this item' });
    await expect(mapped).toBeVisible();
    await expect(page.getByText(/\d+ links? you can see/)).toBeVisible();
    await expect(mapped.getByRole('link').first()).toHaveAttribute('href', /\/curriculum\/versions\//);
    await expectNoAccessibilityViolations(page);

    // Search by words, pick the match, then show it in the tree.
    await page.getByRole('searchbox', { name: /Search this framework/ }).fill('ethic');
    const results = page.getByRole('list', { name: 'Search results' });
    await expect(results.getByRole('button', { name: /Ethical conduct/ })).toBeVisible();
    await expect(page.getByText('1 match')).toBeVisible();
    await expectNoAccessibilityViolations(page);
    await results.getByRole('button', { name: /Ethical conduct/ }).click();
    await expect(page.getByRole('heading', { level: 2, name: /Ethical conduct/ })).toBeVisible();
    await page.getByRole('button', { name: 'Show in tree' }).click();
    const found = tree.getByRole('treeitem', { name: /Ethical conduct/ });
    await expect(found).toBeFocused();
    await expect(found).toHaveAttribute('aria-selected', 'true');
    await expectNoAccessibilityViolations(page);

    // Nothing matches: a plain message, not an empty page.
    await page.getByRole('searchbox', { name: /Search this framework/ }).fill('zzzzzz');
    await expect(page.getByText(/Nothing matches "zzzzzz"/)).toBeVisible();
    await expectNoAccessibilityViolations(page);
  });

  test('a long list opens in windows', async ({ page }, testInfo) => {
    const key = `e2e-browse-${testInfo.project.name}-${Date.now() % 10_000_000}`;
    const id = await importPack(page, key, 130);
    await openApp(page, `/frameworks/${id}`);

    const tree = page.getByRole('tree', { name: `E2E browse ${key} items` });
    // 100 siblings first, then the rest on request.
    await expect(tree.getByRole('treeitem', { name: /Keyword 98/ })).toBeVisible();
    await expect(tree.getByRole('treeitem', { name: /Keyword 130/ })).toHaveCount(0);
    const more = tree.getByRole('treeitem', { name: /Show more items/ });
    await expect(more).toBeVisible();
    await expectNoAccessibilityViolations(page);
    await more.click();
    await expect(tree.getByRole('treeitem', { name: /Keyword 130/ })).toBeVisible();
    await expect(more).toHaveCount(0);

    // An item far down opens straight from its address, with a way back to the start.
    await openApp(page, `/frameworks/${id}`);
    await page.getByRole('searchbox', { name: /Search this framework/ }).fill('K-125');
    await page.getByRole('list', { name: 'Search results' }).getByRole('button', { name: /Keyword 125/ }).click();
    await page.getByRole('button', { name: 'Show in tree' }).click();
    const far = tree.getByRole('treeitem', { name: /Keyword 125/ });
    await expect(far).toBeFocused();
    await expect(tree.getByRole('treeitem', { name: /Show earlier items/ })).toBeVisible();
    await expectNoAccessibilityViolations(page);
  });

  test('delete an unused version after confirming', async ({ page }, testInfo) => {
    const key = `e2e-delete-${testInfo.project.name}-${Date.now() % 10_000_000}`;
    const id = await importPack(page, key, 3);
    await openApp(page, `/frameworks?framework=${key}`);

    const name = `E2E browse ${key}`;
    await expect(page.getByRole('heading', { level: 2, name })).toBeVisible();
    await page.getByRole('button', { name: `Delete ${name} version 1` }).click();
    const dialog = page.getByRole('dialog');
    await expect(dialog.getByText(/hides the version from the library/)).toBeVisible();
    await expectNoAccessibilityViolations(page);

    await dialog.getByRole('button', { name: 'Delete version' }).click();
    await expect(page.getByRole('status').filter({ hasText: `Deleted ${name} version 1.` })).toBeVisible();
    await expect(page.getByRole('list', { name: 'Frameworks' }).getByText(name)).toHaveCount(0);
    await expectNoAccessibilityViolations(page);

    // It is gone for good: the API no longer finds it, so the cleanup has nothing left to do.
    expect((await page.request.get(`/api/v1/frameworks/${id}/items`)).status()).toBe(404);
  });
});
