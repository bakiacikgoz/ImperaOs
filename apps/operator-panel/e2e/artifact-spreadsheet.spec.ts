import { expect, test } from '@playwright/test';

import { installStructuredArtifactBridgeStub, structuredArtifactCommands } from './artifact-helpers';
import { gotoOperatorPanel, openPrimaryView } from './helpers';

test('spreadsheet virtualizes 10k rows, edits cells, and exports injection-safe CSV/XLSX', async ({ page }) => {
  const consoleHealth = await gotoOperatorPanel(page, { operatorId: 'spreadsheet-operator' });
  await openPrimaryView(page, 'AI Assistant', 'Welcome to ImperaOS Assistant');
  await page.getByLabel('Message').fill('Open a governed spreadsheet artifact.');
  await page.getByLabel('Message').press('Enter');
  await expect(page.getByRole('button', { name: 'Open Launch plan' })).toBeVisible();
  await installStructuredArtifactBridgeStub(page, 'spreadsheet');
  await page.getByRole('button', { name: 'Open Launch plan' }).dispatchEvent('click');

  const workbench = page.getByRole('complementary', { name: 'Workbench' });
  const editor = workbench.getByRole('region', { name: 'Spreadsheet editor: Budget' });
  const grid = editor.getByRole('grid', { name: 'Budget cells' });
  await expect(editor).toBeVisible();
  await expect(editor).toContainText('10000 filled cells');
  await expect(grid.getByRole('gridcell')).toHaveCount(40 * 12);
  await grid.evaluate((element) => { element.scrollTop = 9_999 * 32; element.dispatchEvent(new Event('scroll')); });
  await expect(grid.getByLabel('A10000')).toHaveValue('10000');
  await expect(grid.getByRole('gridcell')).toHaveCount(40 * 12);
  await grid.evaluate((element) => { element.scrollTop = 0; element.dispatchEvent(new Event('scroll')); });
  await grid.getByLabel('B1', { exact: true }).fill('42');
  await expect.poll(async () => (await structuredArtifactCommands(page)).filter((item) => item === 'bridge_artifact_mutate'), { timeout: 12_000 })
    .toEqual(['bridge_artifact_mutate']);
  await expect(workbench.getByLabel('Artifact status').getByText('Revision 2')).toBeVisible();

  await editor.getByRole('button', { name: 'Export CSV' }).click();
  await workbench.getByRole('dialog', { name: 'Export Budget' }).getByRole('button', { name: 'Choose destination and export' }).click();
  await expect.poll(async () => (await structuredArtifactCommands(page)).filter((item) => item.includes('export')))
    .toEqual(['bridge_artifact_export_begin', 'bridge_artifact_export_commit']);
  const exportedCsv = await page.evaluate(() => {
    const state = (window as unknown as {
      __structuredArtifactE2eState: { snapshot(): { exportedBytes: number[] } };
    }).__structuredArtifactE2eState;
    return new TextDecoder().decode(new Uint8Array(state.snapshot().exportedBytes));
  });
  expect(exportedCsv).toContain("'=1+1");

  await editor.getByRole('button', { name: 'Export XLSX' }).click();
  await workbench.getByRole('dialog', { name: 'Export Budget' }).getByRole('button', { name: 'Choose destination and export' }).click();
  await expect.poll(async () => (await structuredArtifactCommands(page)).filter((item) => item.includes('export')))
    .toEqual([
      'bridge_artifact_export_begin', 'bridge_artifact_export_commit',
      'bridge_artifact_export_begin', 'bridge_artifact_export_commit',
    ]);
  consoleHealth.assertNoCriticalErrors();
});
