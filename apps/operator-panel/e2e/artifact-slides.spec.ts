import { expect, test } from '@playwright/test';

import { installStructuredArtifactBridgeStub, structuredArtifactCommands } from './artifact-helpers';
import { gotoOperatorPanel, openPrimaryView } from './helpers';

test('slides editor edits structured content and exports PPTX', async ({ page }) => {
  const consoleHealth = await gotoOperatorPanel(page, { operatorId: 'slides-operator' });
  await openPrimaryView(page, 'AI Assistant', 'Welcome to ImperaOS Assistant');
  await page.getByLabel('Message').fill('Open a governed slides artifact.');
  await page.getByLabel('Message').press('Enter');
  await expect(page.getByRole('button', { name: 'Open Launch plan' })).toBeVisible();
  await installStructuredArtifactBridgeStub(page, 'slides');
  await page.getByRole('button', { name: 'Open Launch plan' }).dispatchEvent('click');

  const workbench = page.getByRole('complementary', { name: 'Workbench' });
  const editor = workbench.getByRole('region', { name: 'Structured slides editor' });
  await expect(editor).toBeVisible();
  await editor.getByRole('button', { name: 'Export PPTX' }).click();
  await workbench.getByRole('dialog', { name: 'Export Deck' }).getByRole('button', { name: 'Choose destination and export' }).click();
  await expect.poll(async () => (await structuredArtifactCommands(page)).filter((item) => item.includes('export')))
    .toEqual(['bridge_artifact_export_begin', 'bridge_artifact_export_commit']);
  await editor.getByRole('button', { name: 'text element text-1' }).click();
  await editor.getByRole('textbox', { name: 'Text' }).fill('Updated governed deck');
  await expect(editor.getByRole('button', { name: 'text element text-1' })).toContainText('Updated governed deck');
  await expect(workbench.getByLabel('Artifact status').getByText('dirty')).toBeVisible();
  consoleHealth.assertNoCriticalErrors();
});
