import { expect, test } from '@playwright/test';

import { installStructuredArtifactBridgeStub, structuredArtifactCommands } from './artifact-helpers';
import { gotoOperatorPanel, openPrimaryView } from './helpers';

test('canvas editor keeps local content safe, edits, and exports SVG offline', async ({ page }) => {
  const consoleHealth = await gotoOperatorPanel(page, { operatorId: 'canvas-operator' });
  await openPrimaryView(page, 'AI Assistant', 'Welcome to ImperaOS Assistant');
  await page.getByLabel('Message').fill('Open a governed canvas artifact.');
  await page.getByLabel('Message').press('Enter');
  await expect(page.getByRole('button', { name: 'Open Launch plan' })).toBeVisible();
  await installStructuredArtifactBridgeStub(page, 'canvas');
  await page.getByRole('button', { name: 'Open Launch plan' }).dispatchEvent('click');

  const workbench = page.getByRole('complementary', { name: 'Workbench' });
  const editor = workbench.getByRole('region', { name: 'Canvas editor: Board' });
  await expect(editor).toBeVisible();
  await expect(editor.getByRole('navigation', { name: 'Canvas outline' })).toContainText('asset-local-1');
  await expect(editor.getByRole('img', { name: 'Local asset asset-local-1' })).toBeVisible();
  await expect(editor.getByText('<script>local text only</script>', { exact: true })).toBeVisible();

  await editor.getByRole('button', { name: 'Add rectangle' }).click();
  await expect.poll(async () => (await structuredArtifactCommands(page)).filter((item) => item === 'bridge_artifact_mutate'), { timeout: 12_000 })
    .toEqual(['bridge_artifact_mutate']);
  await expect(workbench.getByLabel('Artifact status').getByText('Revision 2')).toBeVisible();

  const offlineRequests: string[] = [];
  page.on('request', (request) => offlineRequests.push(request.url()));
  await page.context().setOffline(true);
  try {
    await editor.getByRole('button', { name: 'Export SVG' }).click();
    await workbench.getByRole('dialog', { name: 'Export Board' }).getByRole('button', { name: 'Choose destination and export' }).click();
    await expect.poll(async () => (await structuredArtifactCommands(page)).filter((item) => item.includes('export')))
      .toEqual(['bridge_artifact_export_begin', 'bridge_artifact_export_commit']);
    const commands = await structuredArtifactCommands(page);
    expect(commands).toContain('bridge_artifact_asset_get');
    expect(offlineRequests).toEqual([]);
    consoleHealth.assertNoCriticalErrors();
  } finally {
    await page.context().setOffline(false);
  }
});
