import { test, expect } from '@playwright/test';

test('enterprise workspace route renders from preview snapshot', async ({ page }) => {
  await page.goto('/?view=enterprise-workspace#/system');
  await expect(page.getByTestId('page-primary-region')).toBeVisible();
});
