import { expect, test } from '@playwright/test';

import { installArtifactBridgeStub } from './artifact-helpers';
import { gotoOperatorPanel, openPrimaryView } from './helpers';

test('revision conflict preserves, compares, and forks the local draft without silent merge', async ({ page }) => {
  test.setTimeout(90_000);
  const consoleHealth = await gotoOperatorPanel(page, { operatorId: 'e2e-operator' });
  await openPrimaryView(page, 'AI Assistant', 'Welcome to ImperaOS Assistant');
  await page.getByLabel('Message').fill('Create a governed document artifact.');
  await page.getByLabel('Message').press('Enter');
  await expect(page.getByRole('button', { name: 'Open Launch plan' })).toBeVisible();
  await installArtifactBridgeStub(page);
  await page.getByRole('button', { name: 'Open Launch plan' }).click();

  const workbench = page.getByRole('complementary', { name: 'Workbench' });
  const editor = workbench.getByRole('region', { name: 'Document editor: Launch plan' });
  await expect(editor).toBeVisible({ timeout: 30_000 });
  await page.evaluate(() => {
    const state = (window as unknown as { __artifactE2eState: { seedRemoteConflict: () => void } }).__artifactE2eState;
    state.seedRemoteConflict();
  });
  await editor.getByRole('textbox').fill('Preserved local draft');

  const conflict = workbench.getByRole('region', { name: 'Revision conflict' });
  await expect(conflict).toBeVisible({ timeout: 10_000 });
  await expect(conflict).toContainText('local draft is preserved');
  const mutation = await page.evaluate(() => {
    const state = (window as unknown as {
      __artifactE2eState: { snapshot: () => { mutationRequests: Array<Record<string, unknown>> } };
    }).__artifactE2eState;
    return state.snapshot().mutationRequests.at(-1);
  });
  expect(mutation).toMatchObject({ artifactId: 'artifact-preview-document', expectedRevisionNumber: 1 });
  expect(JSON.stringify(mutation?.content)).toContain('Preserved local draft');
  await conflict.getByRole('button', { name: 'Reload latest remote' }).click();
  const reloadDialog = workbench.getByRole('alertdialog', { name: 'Discard local draft?' });
  await expect(reloadDialog).toBeVisible();
  await expect(conflict.getByRole('button', { name: 'Compare' })).toBeDisabled();
  await page.keyboard.press('Escape');
  await expect(reloadDialog).toHaveCount(0);
  await expect(conflict.getByRole('button', { name: 'Reload latest remote' })).toBeFocused();
  await conflict.getByRole('button', { name: 'Compare' }).click();

  const comparison = workbench.getByRole('region', { name: 'Revision comparison' });
  await expect(comparison).toContainText('Local draft');
  await expect(comparison.getByText('Changed')).toBeVisible();
  await expect(comparison.getByText('block:block-1')).toBeVisible();
  await comparison.getByRole('button', { name: 'Close comparison' }).click();
  await expect(conflict.getByRole('button', { name: 'Compare' })).toBeFocused();

  await conflict.getByRole('button', { name: 'Fork local draft' }).click();
  const forkTab = workbench.getByRole('tab', { name: 'Launch plan (local draft)' });
  await expect(forkTab).toHaveAttribute('aria-selected', 'true');
  await expect(forkTab).toBeFocused();
  await expect(workbench.getByRole('status', { name: 'Artifact operation status' })).toContainText('Local draft forked into a new artifact.');
  const forkEditor = workbench.getByRole('region', { name: 'Document editor: Launch plan (local draft)' });
  await expect(forkEditor.getByRole('textbox')).toContainText('Preserved local draft');
  await expect(workbench.getByRole('region', { name: 'Revision conflict' })).toHaveCount(0);

  await workbench.getByRole('tab', { name: 'Launch plan', exact: true }).click();
  await expect(workbench.getByRole('region', { name: 'Revision conflict' })).toHaveCount(0);
  await expect(workbench.getByRole('region', { name: 'Document editor: Launch plan' }).getByRole('textbox')).toContainText('Initial governed draft');
  await forkTab.click();
  await workbench.getByRole('button', { name: 'Close Launch plan (local draft)' }).click();
  await expect(forkTab).toHaveCount(0);
  await workbench.getByRole('button', { name: /Launch plan \(local draft\)/ }).click();
  await expect(workbench.getByRole('region', { name: 'Document editor: Launch plan (local draft)' }).getByRole('textbox')).toContainText('Preserved local draft');

  await workbench.getByRole('tab', { name: 'Launch plan', exact: true }).click();
  await page.evaluate(() => {
    const state = (window as unknown as { __artifactE2eState: { seedRemoteConflict: () => void } }).__artifactE2eState;
    state.seedRemoteConflict();
  });
  const originalEditor = workbench.getByRole('region', { name: 'Document editor: Launch plan' }).getByRole('textbox');
  await originalEditor.fill('Draft discarded only after confirmation');
  const reloadConflict = workbench.getByRole('region', { name: 'Revision conflict' });
  await expect(reloadConflict).toBeVisible({ timeout: 10_000 });
  await expect(originalEditor).toBeFocused();
  await page.evaluate(() => {
    const state = (window as unknown as { __artifactE2eState: { failNextGet: () => void } }).__artifactE2eState;
    state.failNextGet();
  });
  await reloadConflict.getByRole('button', { name: 'Reload latest remote' }).click();
  await workbench.getByRole('button', { name: 'Discard draft and reload' }).click();
  await expect(
    workbench.getByRole('alert').filter({ hasText: 'The latest remote revision could not be loaded.' }),
  ).toBeVisible();
  await expect(reloadConflict).toBeVisible();
  await expect(originalEditor).toContainText('Draft discarded only after confirmation');
  await expect(reloadConflict.getByRole('button', { name: 'Reload latest remote' })).toBeFocused();
  await reloadConflict.getByRole('button', { name: 'Reload latest remote' }).click();
  await workbench.getByRole('button', { name: 'Discard draft and reload' }).click();
  await expect(reloadConflict).toHaveCount(0);
  await expect(originalEditor).toContainText('Initial governed draft');
  consoleHealth.assertNoCriticalErrors();
});
