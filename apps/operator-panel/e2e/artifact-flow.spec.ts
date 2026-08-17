import { expect, test } from '@playwright/test';

import { flowArtifactEvidence, installFlowArtifactBridgeStub } from './artifact-helpers';
import { gotoOperatorPanel, openPrimaryView } from './helpers';

test('flow artifact edits through React Flow, exposes an outline, and exports sanitized SVG', async ({ page }) => {
  test.setTimeout(90_000);
  const externalRequests: string[] = [];
  page.on('request', (request) => {
    const url = request.url();
    if (!url.startsWith('http://127.0.0.1:5173') && !url.startsWith('blob:') && !url.startsWith('data:')) {
      externalRequests.push(url);
    }
  });

  const consoleHealth = await gotoOperatorPanel(page, { operatorId: 'flow-operator' });
  await openPrimaryView(page, 'AI Assistant', 'Welcome to ImperaOS Assistant');
  await page.getByLabel('Message').fill('Open a governed flow artifact.');
  await page.getByLabel('Message').press('Enter');
  await expect(page.getByRole('button', { name: 'Open Launch plan' })).toBeVisible();
  await installFlowArtifactBridgeStub(page);
  await page.getByRole('button', { name: 'Open Launch plan' }).dispatchEvent('click');

  const workbench = page.getByRole('complementary', { name: 'Workbench' });
  const editor = workbench.getByRole('region', { name: 'Flow editor: Approval flow' });
  await expect(editor).toBeVisible({ timeout: 30_000 });
  await page.context().setOffline(true);
  const outline = editor.getByRole('navigation', { name: 'Flow outline' });
  await expect(outline).toContainText('<Start>');
  await expect(outline).toContainText('Review');
  await expect(editor.locator('.react-flow__node')).toHaveCount(2);
  const startNode = editor.locator('.react-flow__node').filter({ hasText: '<Start>' });
  await expect(startNode).toBeVisible();
  await expect(editor.locator('.react-flow__edge')).toHaveCount(1);
  const box = await startNode.boundingBox();
  if (!box) throw new Error('Start node is not visible.');
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 + 64, box.y + box.height / 2 + 24, { steps: 4 });
  await page.mouse.up();
  await expect.poll(async () => (await flowArtifactEvidence(page)).commands.filter((item) => item === 'bridge_artifact_mutate'))
    .toEqual(['bridge_artifact_mutate']);
  await expect(workbench.getByLabel('Artifact status').getByText('Revision 2')).toBeVisible();

  await workbench.getByRole('button', { name: 'Export', exact: true }).click();
  const exportDialog = workbench.getByRole('dialog', { name: 'Export Approval flow' });
  await exportDialog.getByLabel('Export format').selectOption('svg');
  await exportDialog.getByRole('button', { name: 'Choose destination and export' }).click();
  await expect.poll(async () => (await flowArtifactEvidence(page)).commands.filter((item) => item.includes('export')))
    .toEqual(['bridge_artifact_export_begin', 'bridge_artifact_export_commit']);
  const exported = (await flowArtifactEvidence(page)).exportedText ?? '';
  expect(exported).toContain('<svg');
  expect(exported).toContain('&lt;Start&gt;');
  expect(exported).not.toMatch(/<script|onload=/i);
  expect(externalRequests).toEqual([]);
  consoleHealth.assertNoCriticalErrors();
});
