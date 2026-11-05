import { expect, test } from '@playwright/test';

import { expectNoAccessibilityViolations, openApp } from './support';

// The administration screens (Slice 1.30) as the test admin. People, roles and settings are only
// read here (changing the institution's settings or roles would leak into other journeys). The
// API-token journey makes a token and revokes it again in the same test (ADR 037); a revoked token
// stays in the list, shown as revoked.
test.describe('Administration', () => {
  test('the admin page links to people, roles and settings', async ({ page }) => {
    await openApp(page, '/admin');
    await expect(page.getByRole('link', { name: 'People' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Roles' })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Institution settings' })).toBeVisible();
    await expectNoAccessibilityViolations(page);
  });

  test('people: the list, a search and one person with roles by place', async ({ page }) => {
    await openApp(page, '/admin/users');
    await expect(page.getByRole('heading', { level: 1, name: 'People' })).toBeVisible();
    await expect(page.getByRole('table')).toBeVisible();
    await expectNoAccessibilityViolations(page);

    await page.getByRole('textbox', { name: 'Search people' }).fill('example.org');
    await page.locator('#main-content').getByRole('button', { name: 'Search', exact: true }).click();
    await expect(page.getByRole('table')).toBeVisible();

    await page.getByRole('table').getByRole('link').first().click();
    await expect(page.getByRole('heading', { level: 2, name: 'Roles' })).toBeVisible();
    await expect(page.getByRole('heading', { level: 2, name: 'API tokens' })).toBeVisible();
    await expectNoAccessibilityViolations(page);
  });

  test('roles: built-in roles are listed and can be read, not changed', async ({ page }) => {
    await openApp(page, '/admin/roles');
    await expect(page.getByRole('heading', { level: 1, name: 'Roles' })).toBeVisible();
    await expect(page.getByText('Built in').first()).toBeVisible();
    await page.getByRole('button', { name: /^View the role/ }).first().click();
    const dialog = page.getByRole('dialog');
    await expect(dialog.getByText(/built-in role/)).toBeVisible();
    await expectNoAccessibilityViolations(page);
  });

  test('settings: every block is there with its own Save', async ({ page }) => {
    await openApp(page, '/admin/settings');
    await expect(page.getByRole('heading', { level: 1, name: 'Institution settings' })).toBeVisible();
    for (const name of [
      'Words for curriculum things',
      'Profile and taxonomy',
      'Mapping and review',
      'Credits and notional hours',
      'Objective quality checks',
      'Coverage reports',
    ]) {
      await expect(page.getByRole('heading', { level: 2, name })).toBeVisible();
    }
    await expect(page.getByRole('button', { name: 'Save' })).toHaveCount(6);
    await expectNoAccessibilityViolations(page);
  });

  test('API tokens: a token is shown once and can be revoked', async ({ page }) => {
    await openApp(page, '/account');
    await page.getByRole('button', { name: 'Make a token' }).click();
    const dialog = page.getByRole('dialog');
    await dialog.getByLabel('Name', { exact: false }).first().fill(`e2e ${Date.now()}`);
    await expectNoAccessibilityViolations(page);
    await dialog.getByRole('button', { name: 'Make token' }).click();

    const secret = page.getByTestId('new-token');
    await expect(secret).toContainText(/^ocmp_/);
    await expect(page.getByText(/shown only this once/)).toBeVisible();
    await page.getByRole('button', { name: 'I have copied it' }).click();
    await expect(page.getByTestId('new-token')).toHaveCount(0);

    // Clean up: revoke the token this journey made.
    await page.getByRole('button', { name: /^Revoke the token e2e/ }).first().click();
    await page.getByRole('dialog').getByRole('button', { name: 'Revoke' }).click();
    await expect(page.getByRole('dialog')).toHaveCount(0);
  });
});
