import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

import { installArtifactBridgeStub } from './artifact-helpers';
import { gotoOperatorPanel, openPrimaryView } from './helpers';

test('artifact workbench has no critical axe violations and remains keyboard reachable', async ({ page }) => {
  const consoleHealth = await gotoOperatorPanel(page, { operatorId: 'artifact-a11y-operator' });
  await openPrimaryView(page, 'AI Assistant', 'Welcome to ImperaOS Assistant');
  await page.getByLabel('Message').fill('Create a governed document artifact.');
  await page.getByLabel('Message').press('Enter');
  await expect(page.getByRole('button', { name: 'Open Launch plan' })).toBeVisible();
  await installArtifactBridgeStub(page);
  await page.getByRole('button', { name: 'Open Launch plan' }).click();

  const workbench = page.getByRole('complementary', { name: 'Workbench' });
  await expect(workbench.getByRole('region', { name: 'Document editor: Launch plan' })).toBeVisible();
  const result = await new AxeBuilder({ page }).include('[aria-label="Workbench"]').analyze();
  expect(result.violations.filter((violation) => violation.impact === 'critical')).toEqual([]);

  await workbench.getByRole('tab', { name: 'Launch plan' }).focus();
  await expect(workbench.getByRole('tab', { name: 'Launch plan' })).toBeFocused();
  consoleHealth.assertNoCriticalErrors();
});
