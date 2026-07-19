import { expect, test } from '@playwright/test';

import { gotoOperatorPanel, openPrimaryView } from './helpers';

test('settings persist operator, locale, profile, and raw payload controls after reload', async ({ page }) => {
  const consoleHealth = await gotoOperatorPanel(page);
  await openPrimaryView(page, 'Ayarlar', 'Settings');

  await page.getByLabel('Operator ID').fill('ops-e2e');
  await page.getByLabel('Jobs root').fill('.imperaos/e2e-updated/jobs');
  await page.getByLabel('Language').selectOption('en');
  await page.getByLabel('Enable raw payload mode').check();
  await page.getByRole('button', { name: 'Save', exact: true }).click();

  await expect(page.getByText('Settings saved')).toBeVisible();
  await page.reload();
  await openPrimaryView(page, 'Ayarlar', 'Settings');

  await expect(page.getByLabel('Operator ID')).toHaveValue('ops-e2e');
  await expect(page.getByLabel('Jobs root')).toHaveValue('.imperaos/e2e-updated/jobs');
  await expect(page.getByLabel('Enable raw payload mode')).toBeChecked();

  consoleHealth.assertNoCriticalErrors();
});
