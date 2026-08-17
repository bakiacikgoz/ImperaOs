import { expect, test } from '@playwright/test';

import { installArtifactBridgeStub } from './artifact-helpers';
import { gotoOperatorPanel, openPrimaryView } from './helpers';

test('assistant committed artifact card opens the matching real workspace tab', async ({ page }) => {
  test.setTimeout(90_000);
  const consoleHealth = await gotoOperatorPanel(page, { operatorId: 'e2e-operator' });
  await openPrimaryView(page, 'AI Assistant', 'Welcome to ImperaOS Assistant');
  await page.getByLabel('Message').fill('Create a governed document artifact.');
  await page.getByLabel('Message').press('Enter');

  const cardAction = page.getByRole('button', { name: 'Open Launch plan' });
  await expect(cardAction).toBeVisible();
  await installArtifactBridgeStub(page);
  await cardAction.click();

  const workbench = page.getByRole('complementary', { name: 'Workbench' });
  await expect(workbench.getByRole('tab', { name: 'Launch plan' })).toHaveAttribute('aria-selected', 'true');
  await expect(workbench.getByRole('region', { name: 'Document editor: Launch plan' })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole('button', { name: 'Close workbench' })).toHaveAttribute('aria-expanded', 'true');
  consoleHealth.assertNoCriticalErrors();
});
