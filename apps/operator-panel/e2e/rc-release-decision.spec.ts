import { expect, test } from '@playwright/test';

import { gotoOperatorPanel } from './helpers';

test('rc release decision page renders conditional dossier without raw payloads', async ({ page }) => {
  await gotoOperatorPanel(page);
  await page.getByRole('button', { name: /RC Release Decision/i }).click();

  await expect(page.getByTestId('rc-release-decision')).toBeVisible();
  await expect(page.getByRole('heading', { name: /Human sign-off|Insan onayi/i })).toBeVisible();
  await expect(page.getByText('Hat B', { exact: true })).toBeVisible();
  await expect(page.getByText('blocked_external_credentials', { exact: true })).toBeVisible();
  await expect(page.getByText(/rawPayload/i)).toHaveCount(0);
});
