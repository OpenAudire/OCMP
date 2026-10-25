import { expect, test } from '@playwright/test';

import { expectNoAccessibilityViolations, openApp, SIGNED_OUT } from './support';

test.describe('signed-out pages', () => {
  test.use({ storageState: SIGNED_OUT });

  for (const [path, heading] of [
    ['/login', 'Sign in'],
    ['/forgot-password', 'Reset your password'],
  ] as const) {
    test(`${path} has no WCAG violations`, async ({ page }) => {
      await page.goto(path);
      await expect(page.getByRole('heading', { level: 1, name: heading })).toBeVisible();
      await expectNoAccessibilityViolations(page);
    });
  }

  test('a failed sign-in message has no WCAG violations', async ({ page }) => {
    await page.goto('/login');
    // A new address each run: repeated failures for one address are slowed down.
    await page.getByRole('textbox', { name: 'Email' }).fill(`nobody.${Date.now()}@example.org`);
    await page.getByRole('textbox', { name: 'Password' }).fill('not-the-password');
    await page.getByRole('button', { name: 'Sign in' }).click();
    await expect(page.getByRole('alert')).toBeVisible({ timeout: 15_000 });
    await expectNoAccessibilityViolations(page);
  });
});

test.describe('signed-in pages', () => {
  for (const [path, heading] of [
    ['/dashboard', 'Dashboard'],
    ['/mapping/review', 'Review queue'],
    ['/account', 'Your account'],
    ['/no-such-page', 'Page not found'],
  ] as const) {
    test(`${path} has no WCAG violations`, async ({ page }) => {
      await openApp(page, path);
      await expect(page.getByRole('heading', { level: 1, name: heading })).toBeVisible();
      await expectNoAccessibilityViolations(page);
    });
  }

  test('the open account menu has no WCAG violations', async ({ page }) => {
    await openApp(page, '/dashboard');
    await page.getByRole('button', { name: /account menu for/i }).click();
    await expect(page.getByRole('menuitem', { name: 'Sign out' })).toBeVisible();
    await expectNoAccessibilityViolations(page);
  });
});
