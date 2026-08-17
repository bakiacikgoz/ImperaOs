import { expect, test } from '@playwright/test';

import { artifactExportCommands, installArtifactBridgeStub } from './artifact-helpers';
import { gotoOperatorPanel, openPrimaryView } from './helpers';

test('document artifact edits, autosaves, reopens, restores history, and exports natively', async ({ page }) => {
  test.setTimeout(90_000);
  const unexpectedRequests: string[] = [];
  page.on('request', (request) => {
    const url = request.url();
    if (!url.startsWith('http://127.0.0.1:5173') && !url.startsWith('blob:') && !url.startsWith('data:')) {
      unexpectedRequests.push(url);
    }
  });
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
  await expect(editor.getByRole('textbox')).toContainText('Initial governed draft');
  await page.context().setOffline(true);

  await editor.getByRole('textbox').fill('Saved after autosave');
  await expect(workbench.getByLabel('Artifact status').getByText('saved')).toBeVisible({ timeout: 5_000 });
  await expect(workbench.getByLabel('Artifact status').getByText('Revision 2')).toBeVisible();
  await workbench.getByRole('button', { name: 'Refresh history' }).click();
  await expect(workbench.getByLabel('Revision history').getByText('Revision 2')).toBeVisible();

  await workbench.getByRole('button', { name: 'Close Launch plan' }).click();
  await expect(workbench.getByRole('tab', { name: 'Launch plan' })).toHaveCount(0);
  await workbench.getByRole('button', { name: 'Refresh', exact: true }).click();
  await workbench.getByLabel('Artifact navigator').getByRole('button', { name: /Launch plan/ }).click();
  await expect(editor.getByRole('textbox')).toContainText('Saved after autosave');
  await expect(workbench.getByLabel('Artifact status').getByText('Revision 2')).toBeVisible();

  await workbench.getByRole('button', { name: 'Restore revision 1' }).click();
  await expect(workbench.getByLabel('Artifact status').getByText('Revision 3')).toBeVisible();
  await expect(editor.getByRole('textbox')).toContainText('Initial governed draft');

  await workbench.getByRole('button', { name: 'Export', exact: true }).click();
  let exportDialog = workbench.getByRole('dialog', { name: 'Export Launch plan' });
  await exportDialog.getByLabel('Export format').selectOption('markdown');
  await exportDialog.getByRole('button', { name: 'Choose destination and export' }).click();
  await workbench.getByRole('button', { name: 'Export', exact: true }).click();
  exportDialog = workbench.getByRole('dialog', { name: 'Export Launch plan' });
  await exportDialog.getByLabel('Export format').selectOption('html');
  await exportDialog.getByRole('button', { name: 'Choose destination and export' }).click();
  await expect.poll(() => artifactExportCommands(page)).toEqual([
    'bridge_artifact_export_begin',
    'bridge_artifact_export_commit',
    'bridge_artifact_export_begin',
    'bridge_artifact_export_commit',
  ]);
  expect(unexpectedRequests).toEqual([]);
  consoleHealth.assertNoCriticalErrors();
});
