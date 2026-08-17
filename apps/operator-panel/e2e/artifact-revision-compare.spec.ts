import { expect, test } from '@playwright/test';

import { installArtifactBridgeStub } from './artifact-helpers';
import { gotoOperatorPanel, openPrimaryView } from './helpers';

test('historical revision comparison is bounded, read-only, and preserves the editor', async ({ page }) => {
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
  await editor.getByRole('textbox').fill('Persisted revision two');
  await expect(workbench.getByLabel('Artifact status').getByText('Revision 2')).toBeVisible({ timeout: 10_000 });
  await workbench.getByRole('button', { name: 'Refresh history' }).click();
  await page.evaluate(() => {
    const state = (window as unknown as { __artifactE2eState: { holdMutations: () => void } }).__artifactE2eState;
    state.holdMutations();
  });
  await editor.getByRole('textbox').fill('Unsaved local revision three');

  await workbench.getByRole('button', { name: 'Compare revision 1' }).click();
  const comparison = workbench.getByRole('region', { name: 'Revision comparison' });
  await expect(comparison).toBeVisible();
  await expect(comparison.getByRole('status')).toContainText('1 changes');
  await expect(comparison.getByText('Changed')).toBeVisible();
  await expect(comparison.getByText('Unsaved draft is preserved and excluded from comparison.')).toBeVisible();
  await expect(editor).toBeHidden();

  await comparison.getByRole('button', { name: 'Close comparison' }).click();
  await expect(editor).toBeVisible();
  await expect(editor.getByRole('textbox')).toContainText('Unsaved local revision three');
  await page.evaluate(() => {
    const state = (window as unknown as { __artifactE2eState: { releaseMutations: () => void } }).__artifactE2eState;
    state.releaseMutations();
  });
  await expect(workbench.getByLabel('Artifact status').getByText('Revision 3')).toBeVisible({ timeout: 10_000 });
  consoleHealth.assertNoCriticalErrors();
});

test('revision comparison announces bounded output truncation', async ({ page }) => {
  test.setTimeout(90_000);
  const consoleHealth = await gotoOperatorPanel(page, { operatorId: 'e2e-operator' });
  await openPrimaryView(page, 'AI Assistant', 'Welcome to ImperaOS Assistant');
  await page.getByLabel('Message').fill('Create a governed document artifact.');
  await page.getByLabel('Message').press('Enter');
  await expect(page.getByRole('button', { name: 'Open Launch plan' })).toBeVisible();
  await installArtifactBridgeStub(page);
  await page.evaluate(() => {
    const state = (window as unknown as { __artifactE2eState: { seedBulkRevision: (count: number) => void } }).__artifactE2eState;
    state.seedBulkRevision(502);
  });
  await page.getByRole('button', { name: 'Open Launch plan' }).click();

  const workbench = page.getByRole('complementary', { name: 'Workbench' });
  await expect(workbench.getByRole('region', { name: 'Document editor: Launch plan' })).toBeVisible({ timeout: 30_000 });
  await workbench.getByRole('button', { name: 'Compare revision 1' }).click();

  const comparison = workbench.getByRole('region', { name: 'Revision comparison' });
  await expect(comparison.getByRole('status')).toContainText('502 changes');
  await expect(comparison.getByRole('alert')).toContainText('2 change details omitted');
  consoleHealth.assertNoCriticalErrors();
});
