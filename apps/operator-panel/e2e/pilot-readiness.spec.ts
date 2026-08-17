import { expect, test } from '@playwright/test';

import { gotoOperatorPanel, openPrimaryView, operationOutput } from './helpers';

test('pilot readiness flow exposes governed run, approval, evidence, reports, and blocked live surfaces', async ({
  page,
}) => {
  page.on('dialog', async (dialog) => {
    await dialog.accept();
  });
  const consoleHealth = await gotoOperatorPanel(page, { operatorId: 'qa-operator' });

  await openPrimaryView(page, 'Dashboard', 'Dashboard');
  await expect(page.getByTestId('page-primary-region')).toContainText('Policy, approvals, evidence');
  await expect(page.getByTestId('page-primary-region')).toContainText('Pilot Launch Candidate');

  await openPrimaryView(page, 'Agents', 'Agents');
  await expect(page.getByRole('heading', { name: 'Governed Ops Agent', exact: true })).toBeVisible();

  await openPrimaryView(page, 'Policy', 'Policy Simulation');
  await expect(page.getByTestId('page-primary-region')).toContainText('require_approval');

  await openPrimaryView(page, 'Çalıştırmalar', 'Runs');
  const runRow = page.locator('button.list-row').filter({ hasText: 'run_20260308_0910' });
  await expect(runRow).toHaveCount(1);
  await expect(runRow).toBeVisible();

  await openPrimaryView(page, 'Onaylar', 'Approvals');
  await expect(page.getByRole('button', { name: 'Approve', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: 'Approve', exact: true }).click();
  await expect(page.getByText('Approve OK', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Execute', exact: true }).click();
  await expect(page.getByText('Execute OK', { exact: true })).toBeVisible();

  await openPrimaryView(page, 'Evidence', 'Signed Evidence');
  await expect(page.getByText('evp-preview-run', { exact: true })).toBeVisible();
  await expect(page.getByTestId('page-primary-region')).toContainText('Evidence corpus');
  await page.getByRole('button', { name: 'Verify latest', exact: true }).click();
  await expect(page.getByText('Evidence verification completed', { exact: true })).toBeVisible();

  await openPrimaryView(page, 'Raporlar', 'Reports');
  await expect(page.getByTestId('page-primary-region')).toContainText('Pilot Launch Candidate');
  await expect(page.getByTestId('page-primary-region')).toContainText('Evidence pack evp-preview-run');
  await expect(page.getByTestId('page-primary-region')).toContainText('Pilot metrics');

  await openPrimaryView(page, 'Yürütmeler', 'Operations');
  await page.getByRole('button', { name: 'Support', exact: true }).click();
  await page.getByRole('button', { name: 'Export support bundle', exact: true }).click();
  await expect(operationOutput(page)).toContainText('imperaos-support.zip');

  await openPrimaryView(page, 'Execution Surfaces', 'Execution Surfaces');
  await expect(page.getByTestId('page-primary-region')).toContainText('Computer-use');
  await expect(page.getByTestId('page-primary-region')).toContainText('blocked');
  await expect(page.getByTestId('page-primary-region')).toContainText('Live start disabled');

  consoleHealth.assertNoCriticalErrors();
});
