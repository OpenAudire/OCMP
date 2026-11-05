import { expect, test } from '@playwright/test';

import { openApp } from './support';

test('the start page is the first section, in the shared layout', async ({ page }) => {
  await openApp(page, '/');

  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page).toHaveTitle('Curriculum in Context');
  const nav = page.getByRole('navigation', { name: 'Main navigation' });
  await expect(nav.getByRole('link')).toHaveText([
    'Dashboard',
    'Curriculum',
    'Mapping',
    'Review queue',
    'Frameworks',
    'Reports',
    'Import and export',
    'Explorer',
    'Search',
    'Admin',
  ]);
  await expect(nav.locator('[aria-current="page"]')).toHaveText(['Dashboard']);

  await nav.getByRole('link', { name: 'Review queue' }).click();
  await expect(page.getByRole('heading', { level: 1, name: 'Review queue' })).toBeVisible();
  await expect(nav.locator('[aria-current="page"]')).toHaveText(['Review queue']);
});

test('the theme toggle switches the theme and is remembered', async ({ page }, testInfo) => {
  await openApp(page, '/dashboard');
  const html = page.locator('html');
  const start = testInfo.project.name === 'dark' ? 'dark' : 'light';
  const other = start === 'dark' ? 'light' : 'dark';
  await expect(html).toHaveAttribute('data-mantine-color-scheme', start);

  await page.getByRole('button', { name: `Switch to ${other} theme` }).click();
  await expect(html).toHaveAttribute('data-mantine-color-scheme', other);

  await page.reload();
  await expect(html).toHaveAttribute('data-mantine-color-scheme', other);
  await expect(page.getByRole('button', { name: `Switch to ${start} theme` })).toBeVisible();
});

test('fonts are self-hosted: IBM Plex Sans loads and nothing comes from other sites', async ({
  page,
  baseURL,
}) => {
  const origin = new URL(baseURL ?? 'https://localhost').origin;
  const external: string[] = [];
  page.on('request', (request) => {
    const url = request.url();
    if (!url.startsWith(origin) && !url.startsWith('data:')) external.push(url);
  });

  await openApp(page, '/dashboard');
  await page.evaluate(() => document.fonts.ready);

  expect(await page.evaluate(() => document.fonts.check('600 16px "IBM Plex Sans"'))).toBe(true);
  expect(external).toEqual([]);
});

test('the skip link moves focus to the page content', async ({ page }) => {
  await openApp(page, '/dashboard');
  await page.locator('body').focus();
  await page.keyboard.press('Tab');
  const skip = page.getByRole('link', { name: 'Skip to main content' });
  await expect(skip).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.locator('#main-content')).toBeFocused();
});

test.describe('phone width', () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test('the navigation opens from the menu button and closes after choosing', async ({ page }) => {
    await openApp(page, '/dashboard');
    const nav = page.getByRole('navigation', { name: 'Main navigation' });
    await expect(nav).toBeHidden();

    const menuButton = page.getByRole('button', { name: 'Show or hide navigation' });
    await menuButton.click();
    await expect(nav).toBeVisible();
    await expect(menuButton).toHaveAttribute('aria-expanded', 'true');

    // The menu button stays reachable above the open navigation and closes it.
    await menuButton.click();
    await expect(nav).toBeHidden();

    await menuButton.click();
    await nav.getByRole('link', { name: 'Frameworks' }).click();

    await expect(page.getByRole('heading', { level: 1, name: 'Frameworks' })).toBeVisible();
    await expect(nav).toBeHidden();
  });
});
