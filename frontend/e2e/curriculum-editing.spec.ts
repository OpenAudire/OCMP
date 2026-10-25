import { expect, test, type Page } from '@playwright/test';

import { expectNoAccessibilityViolations, openApp } from './support';

// Runs against the demo programme (load-demo) as the test admin, who may edit it. Each
// journey adds its own uniquely named items and deletes them again, so the demo data and
// the other journeys (which run in parallel) are not affected.
const PROGRAMME = 'BSc Health Sciences (Demo)';

async function openBuilder(page: Page) {
  await openApp(page, '/curriculum');
  const tree = page.getByRole('tree', { name: `Structure of ${PROGRAMME}` });
  await expect(tree).toBeVisible();
  return tree;
}

test.describe('curriculum builder editing', () => {
  test('adds, changes and deletes a phase, module and session', async ({ page }, testInfo) => {
    const suffix = `${testInfo.project.name}-${Date.now() % 1_000_000}`;
    const phaseName = `E2E phase ${suffix}`;
    const code = `E2E-${suffix}`;
    const tree = await openBuilder(page);
    const notice = page.getByRole('status').filter({ hasText: /added|saved|deleted/ });

    // Cancel leaves nothing behind and returns focus to the button.
    const addPhase = page.getByRole('button', { name: 'Add phase' });
    await addPhase.click();
    const phaseDialog = page.getByRole('dialog', { name: 'Add phase' });
    await expect(phaseDialog.getByRole('textbox', { name: /Name/ })).toBeFocused();
    await expectNoAccessibilityViolations(page);
    await page.keyboard.press('Escape');
    await expect(phaseDialog).toBeHidden();
    await expect(addPhase).toBeFocused();

    // Phase: a required name is checked before anything is sent.
    await addPhase.click();
    await phaseDialog.getByRole('button', { name: 'Add phase' }).click();
    await expect(phaseDialog.getByText('Fill in this field.')).toBeVisible();
    await expectNoAccessibilityViolations(page);
    await phaseDialog.getByRole('textbox', { name: /Name/ }).fill(phaseName);
    await phaseDialog.getByRole('combobox', { name: 'Kind' }).selectOption({ label: 'Block' });
    await phaseDialog.getByRole('button', { name: 'Add phase' }).click();
    await expect(notice).toHaveText(`${phaseName} added.`);
    await expect(tree.getByRole('treeitem', { name: new RegExp(phaseName) })).toHaveAttribute(
      'aria-selected',
      'true'
    );
    await expectNoAccessibilityViolations(page);

    // Module in the new phase.
    await page.getByRole('button', { name: 'Add module' }).click();
    const moduleDialog = page.getByRole('dialog', { name: 'Add module' });
    await expect(moduleDialog.getByRole('combobox', { name: 'Phase' })).toHaveValue(/.+/);
    await moduleDialog.getByRole('textbox', { name: /Code/ }).fill(code);
    await moduleDialog.getByRole('textbox', { name: /Name/ }).fill('Journey module');
    await moduleDialog.getByRole('textbox', { name: 'Credits' }).fill('12');
    await expectNoAccessibilityViolations(page);
    await moduleDialog.getByRole('button', { name: 'Add module' }).click();
    await expect(notice).toHaveText(`${code} Journey module added.`);
    const moduleItem = tree.getByRole('treeitem', { name: new RegExp(code) });
    await expect(moduleItem).toHaveAttribute('aria-selected', 'true');
    await expect(page.getByRole('heading', { level: 2, name: new RegExp(code) })).toBeVisible();

    // Session with a teaching format, then changed.
    await page.getByRole('button', { name: 'Add session' }).click();
    const sessionDialog = page.getByRole('dialog', { name: `Add session to ${code}` });
    await sessionDialog.getByRole('textbox', { name: /Title/ }).fill('Journey session');
    const format = sessionDialog.getByRole('combobox', { name: 'Format' });
    await expect(format.getByRole('option')).not.toHaveCount(1);
    await format.selectOption({ index: 1 });
    await sessionDialog.getByRole('textbox', { name: 'Contact time (minutes)' }).fill('90');
    await sessionDialog.getByRole('button', { name: 'Add session' }).click();
    await expect(notice).toHaveText('Journey session added.');
    await expect(tree.getByRole('treeitem', { name: /Journey session/ })).toHaveAttribute(
      'aria-selected',
      'true'
    );

    await page.getByRole('button', { name: 'Edit session' }).click();
    const editDialog = page.getByRole('dialog', { name: 'Edit Journey session' });
    await expect(editDialog.getByRole('textbox', { name: /Title/ })).toHaveValue('Journey session');
    await editDialog.getByRole('textbox', { name: /Title/ }).fill('Journey workshop');
    await editDialog.getByRole('textbox', { name: 'Week' }).fill('3');
    await editDialog.getByRole('button', { name: 'Save changes' }).click();
    await expect(notice).toHaveText('Changes to Journey workshop saved.');
    await expect(tree.getByRole('treeitem', { name: /Journey workshop/ })).toContainText('Week 3');
    await expect(page.getByRole('button', { name: 'Edit session' })).toBeFocused();

    // Deleting says what goes with it; the selection moves to the parent.
    await page.getByRole('button', { name: 'Delete session' }).click();
    const deleteSession = page.getByRole('dialog', { name: 'Delete Journey workshop?' });
    await expect(deleteSession).toContainText('This also deletes its 0 objectives.');
    await expectNoAccessibilityViolations(page);
    await deleteSession.getByRole('button', { name: 'Delete session' }).click();
    await expect(notice).toHaveText('Journey workshop deleted.');
    await expect(moduleItem).toHaveAttribute('aria-selected', 'true');

    await page.getByRole('button', { name: 'Delete module' }).click();
    const deleteModule = page.getByRole('dialog', { name: `Delete ${code} Journey module?` });
    await deleteModule.getByRole('button', { name: 'Delete module' }).click();
    await expect(notice).toHaveText(`${code} Journey module deleted.`);
    await expect(moduleItem).toBeHidden();

    const phaseItem = tree.getByRole('treeitem', { name: new RegExp(phaseName) });
    await expect(phaseItem).toHaveAttribute('aria-selected', 'true');
    await page.getByRole('button', { name: 'Delete phase' }).click();
    await page
      .getByRole('dialog', { name: `Delete ${phaseName}?` })
      .getByRole('button', { name: 'Delete phase' })
      .click();
    await expect(notice).toHaveText(`${phaseName} deleted.`);
    await expect(phaseItem).toBeHidden();
  });

  test('a phase that holds modules explains why it cannot be deleted', async ({ page }) => {
    const tree = await openBuilder(page);

    await tree.getByRole('treeitem', { name: /Year 1/ }).click();
    await page.getByRole('button', { name: 'Delete phase' }).click();
    const dialog = page.getByRole('dialog', { name: 'Delete Year 1?' });
    await expect(dialog).toContainText('Move them to another phase or delete them first.');
    await expect(dialog.getByRole('button', { name: 'Delete phase' })).toHaveCount(0);
    await expectNoAccessibilityViolations(page);
    await page.keyboard.press('Escape');
    await expect(dialog).toBeHidden();
  });
});
