import { expect, test } from '@playwright/test';

import { expectNoAccessibilityViolations, openApp } from './support';

// Admin > Check the AI's mapping (Slice 1.19). The page is opened and checked with axe in both
// themes. Nothing is created and no AI provider is called: a run needs a configured provider and
// costs money, and gold sets are covered by the API and unit tests (a mocked provider). This
// suite leaves nothing behind (ADR 037).
test.describe('AI evaluation page', () => {
  test('is reachable from the admin page and explains how to read the figures', async ({
    page,
  }) => {
    await openApp(page, '/admin');
    await page.getByRole('link', { name: "Check the AI's mapping" }).click();

    await expect(page.getByRole('heading', { level: 1, name: "Check the AI's mapping" })).toBeVisible();
    await expect(page.getByText('Read these figures with care')).toBeVisible();
    await expect(page.getByRole('heading', { level: 2, name: 'Gold sets' })).toBeVisible();
    await expect(page.getByRole('heading', { level: 2, name: 'Run an evaluation' })).toBeVisible();
    await expect(page.getByRole('heading', { level: 2, name: 'Results' })).toBeVisible();
    await expect(page.getByRole('link', { name: /Download the Excel template/ })).toBeVisible();
    // Checking a file needs a name and a file first.
    await expect(page.getByRole('button', { name: 'Check the file' })).toBeDisabled();
    await expectNoAccessibilityViolations(page);
  });
});
