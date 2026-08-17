import { expect, test } from '@playwright/test';

import { installStructuredArtifactBridgeStub } from './artifact-helpers';
import { gotoOperatorPanel, openPrimaryView } from './helpers';

async function prepareArtifactCard(page: import('@playwright/test').Page) {
  const consoleHealth = await gotoOperatorPanel(page, { operatorId: 'artifact-security-operator' });
  await openPrimaryView(page, 'AI Assistant', 'Welcome to ImperaOS Assistant');
  await page.getByLabel('Message').fill('Open a governed canvas artifact.');
  await page.getByLabel('Message').press('Enter');
  await expect(page.getByRole('button', { name: 'Open Launch plan' })).toBeVisible();
  return consoleHealth;
}

test('artifact editor renders hostile markup as text without script execution', async ({ page }) => {
  const consoleHealth = await prepareArtifactCard(page);
  await installStructuredArtifactBridgeStub(page, 'canvas');
  await page.getByRole('button', { name: 'Open Launch plan' }).dispatchEvent('click');

  const editor = page.getByRole('region', { name: 'Canvas editor: Board' });
  await expect(editor).toContainText('<script>local text only</script>');
  await expect(page.locator('script', { hasText: 'local text only' })).toHaveCount(0);
  consoleHealth.assertNoCriticalErrors();
});

test('unsafe artifact schema is rejected before an editor or fallback opens', async ({ page }) => {
  const consoleHealth = await prepareArtifactCard(page);
  await installStructuredArtifactBridgeStub(page, 'canvas');
  await page.evaluate(() => {
    const tauri = (window as unknown as {
      __TAURI_INTERNALS__: {
        invoke(command: string, args: Record<string, unknown>): Promise<unknown>;
      };
    }).__TAURI_INTERNALS__;
    const originalInvoke = tauri.invoke.bind(tauri);
    tauri.invoke = async (command, args) => {
      const response = await originalInvoke(command, args) as {
        ok: boolean;
        data?: { artifact: unknown; revision: unknown; content: unknown };
        error: unknown;
      };
      if (command !== 'bridge_artifact_get' || !response.ok || !response.data) return response;
      return {
        ...response,
        data: {
          ...response.data,
          content: {
            kind: 'canvas', schemaVersion: 2,
            snapshot: { objects: [{
              id: 'image-unsafe', type: 'image', x: 0, y: 0, width: 100, height: 100,
              assetId: 'cross-workspace-asset',
            }] },
            assetIds: [], embeds: 'deny', remoteAssets: 'deny',
          },
        },
      };
    };
  });

  await page.getByRole('button', { name: 'Open Launch plan' }).dispatchEvent('click');
  await expect(page.getByRole('complementary', { name: 'Workbench' }).getByRole('alert')).toBeVisible();
  await expect(page.getByRole('region', { name: 'canvas read-only fallback' })).toHaveCount(0);
  consoleHealth.assertNoCriticalErrors();
});
