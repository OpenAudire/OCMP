import { expect, test } from '@playwright/test';

import { demoDraft, expectNoAccessibilityViolations, openApp } from './support';

// Search (Slice 1.20) on the demo programme as the test admin. It only reads: nothing is created,
// so nothing has to be removed afterwards (ADR 037). The words come from the demo data
// ("Describe the phases of the cardiac cycle."); meaning-based matching depends on whether the
// stack runs the embeddings service, so the journey does not rely on it.
const API = '/api/v1';

test.describe('Search', () => {
  test('the header box opens the results, filters narrow them, and where-taught lists sessions', async ({
    page,
  }) => {
    await openApp(page, '/curriculum');

    await page.getByRole('textbox', { name: 'Quick search' }).fill('cardiac cycle');
    await page.getByRole('button', { name: 'Run quick search' }).click();

    await expect(page.getByRole('heading', { level: 1, name: 'Search' })).toBeVisible();
    await expect(page.getByRole('heading', { level: 2, name: /^Objectives/ })).toBeVisible();
    await expect(page.getByRole('link', { name: /cardiac cycle/i }).first()).toBeVisible();
    await expectNoAccessibilityViolations(page);

    // Filters open and are named; choosing one is kept in the address.
    await page.getByRole('button', { name: 'Filters' }).click();
    await expect(page.getByLabel('Domain')).toBeVisible();
    await page.getByLabel('Domain').selectOption('knowledge');
    await expect(page).toHaveURL(/domain=knowledge/);
    await expect(page.getByText(/The filters leave out: .*sessions/)).toBeVisible();
    await expectNoAccessibilityViolations(page);

    // Where do we teach this: sessions in the order they are taught, with why.
    await page.getByLabel('Domain').selectOption('');
    // The radio of Mantine's segmented control is hidden; its label is what a person clicks.
    await page.getByText('Where do we teach this?', { exact: true }).click();
    await expect(page.getByRole('heading', { level: 2, name: /Sessions that teach it/ })).toBeVisible();
    await expect(page.getByText('In the order they are taught: phase, module, week.')).toBeVisible();
    await expectNoAccessibilityViolations(page);
  });

  test('a search with nothing in it says so', async ({ page }) => {
    await openApp(page, '/search');

    await expect(page.getByText(/Type a word or a question/)).toBeVisible();
    const programmes = await (await page.request.get(`${API}/programmes`)).json();
    const version = demoDraft(programmes[0].versions);
    await openApp(page, `/search?q=zzzzqx&version=${version}`);

    await expect(page.getByText(/Nothing found for/)).toBeVisible();
    await expectNoAccessibilityViolations(page);
  });
});
