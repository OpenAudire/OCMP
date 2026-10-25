import { expect, test, type Page } from '@playwright/test';

import { expectNoAccessibilityViolations, openApp } from './support';

// Runs against the demo programme (load-demo); the test admin sees every programme.
const PROGRAMME = 'BSc Health Sciences (Demo)';

async function openBuilder(page: Page, path = '/curriculum') {
  await openApp(page, path);
  const tree = page.getByRole('tree', { name: `Structure of ${PROGRAMME}` });
  await expect(tree).toBeVisible();
  return tree;
}

test.describe('curriculum builder', () => {
  test('opens a version with its structure and programme details', async ({ page }) => {
    const tree = await openBuilder(page);

    await expect(page).toHaveURL(/\/curriculum\/versions\/[0-9a-f-]+$/);
    await expect(page.getByRole('heading', { level: 1, name: 'Curriculum builder' })).toBeVisible();
    await expect(page.getByRole('heading', { level: 2, name: PROGRAMME })).toBeVisible();
    await expect(tree.getByRole('treeitem', { name: /Year 1/ })).toBeVisible();
    await expect(tree.getByRole('treeitem', { name: /HBIO101/ })).toBeVisible();
    // The longitudinal module sits in its own group after the phases.
    await expect(tree.getByRole('treeitem', { name: 'Across phases' })).toBeVisible();
    await expect(tree.getByRole('treeitem', { name: /CPP100/ })).toBeVisible();
    await expect(page.getByRole('region', { name: 'Programme outcomes' })).toBeVisible();
    await expectNoAccessibilityViolations(page);
  });

  test('moves through the tree by keyboard to a session and its objectives', async ({ page }) => {
    const tree = await openBuilder(page);

    await tree.getByRole('treeitem', { selected: true }).focus();
    // Programme > Year 1 > HBIO101, open it, then its first session.
    await page.keyboard.press('ArrowDown');
    await page.keyboard.press('ArrowDown');
    await page.keyboard.press('Enter');
    await expect(page.getByRole('heading', { level: 2, name: /HBIO101/ })).toBeVisible();
    await expect(page.getByRole('region', { name: 'Module outcomes' })).toBeVisible();
    await page.keyboard.press('ArrowRight');
    await page.keyboard.press('ArrowRight');
    await page.keyboard.press('Enter');

    const session = tree.getByRole('treeitem', { name: /Cells and tissues/ });
    await expect(session).toHaveAttribute('aria-selected', 'true');
    await expect(page).toHaveURL(/item=event%3A/);
    await expect(page.getByRole('heading', { level: 2, name: 'Cells and tissues' })).toBeVisible();
    const objectives = page.getByRole('region', { name: 'Learning objectives' });
    await expect(objectives.getByRole('listitem').first()).toBeVisible();
    await expectNoAccessibilityViolations(page);

    // The address keeps the selection.
    await page.reload();
    await expect(page.getByRole('heading', { level: 2, name: 'Cells and tissues' })).toBeVisible();
  });

  test('the version switcher lists the programme versions', async ({ page }) => {
    await openBuilder(page);

    const switcher = page.getByRole('banner').getByRole('button', { name: PROGRAMME });
    await switcher.click();
    const group = page.getByRole('group', { name: PROGRAMME });
    await expect(group.getByRole('menuitem').first()).toBeVisible();
    await expect(page.locator('[role="menuitem"][aria-current="true"]')).toHaveCount(1);
    await expectNoAccessibilityViolations(page);

    await page.keyboard.press('Escape');
    await expect(group).toBeHidden();
    await expect(switcher).toBeFocused();
  });

  test('an unknown version explains itself', async ({ page }) => {
    await openApp(page, '/curriculum/versions/00000000-0000-0000-0000-000000000000');

    await expect(page.getByRole('alert')).toContainText("This curriculum version isn't available");
    await expectNoAccessibilityViolations(page);
    await page.getByRole('link', { name: 'Open the latest version' }).click();
    await expect(page.getByRole('tree', { name: `Structure of ${PROGRAMME}` })).toBeVisible();
  });

  test('on a phone the switcher is part of the page', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await openBuilder(page);

    await expect(page.getByRole('main').getByRole('button', { name: PROGRAMME })).toBeVisible();
    await expect(page.getByRole('banner').getByRole('button', { name: PROGRAMME })).toBeHidden();
    await expectNoAccessibilityViolations(page);
  });
});
