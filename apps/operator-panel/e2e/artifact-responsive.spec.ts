import { expect, test } from '@playwright/test';

import { installArtifactBridgeStub } from './artifact-helpers';
import { gotoOperatorPanel, openPrimaryView } from './helpers';

test('artifact workbench remains bounded at the mobile viewport', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const consoleHealth = await gotoOperatorPanel(page, { operatorId: 'artifact-responsive-operator' });
  await page.getByRole('button', { name: 'Navigasyonu aç', exact: true }).click();
  await openPrimaryView(page, 'AI Assistant', 'Welcome to ImperaOS Assistant');
  await page.getByLabel('Message').fill('Create a governed document artifact.');
  await page.getByLabel('Message').press('Enter');
  await expect(page.getByRole('button', { name: 'Open Launch plan' })).toBeVisible();
  await installArtifactBridgeStub(page);
  await page.getByRole('button', { name: 'Open Launch plan' }).click();

  const workbench = page.getByRole('complementary', { name: 'Workbench' });
  await expect(workbench.getByRole('region', { name: 'Document editor: Launch plan' })).toBeVisible();
  const bounds = await workbench.evaluate((element) => ({
    viewportWidth: window.innerWidth,
    left: element.getBoundingClientRect().left,
    right: element.getBoundingClientRect().right,
    scrollWidth: element.scrollWidth,
    clientWidth: element.clientWidth,
  }));
  expect(bounds.left).toBeGreaterThanOrEqual(0);
  expect(bounds.right).toBeLessThanOrEqual(bounds.viewportWidth + 1);
  expect(bounds.scrollWidth).toBeLessThanOrEqual(bounds.clientWidth + 1);
  consoleHealth.assertNoCriticalErrors();
});
