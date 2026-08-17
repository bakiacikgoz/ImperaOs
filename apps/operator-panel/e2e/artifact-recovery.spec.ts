import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

import { installArtifactBridgeStub } from './artifact-helpers';
import { gotoOperatorPanel, openPrimaryView } from './helpers';

const SETTINGS_KEY = 'imperaos.operator.settings.v1';
const SENSITIVE_DRAFT = 'phase-12-3-sensitive-draft-canary';

async function readWebStorage(page: import('@playwright/test').Page) {
  return page.evaluate(() => ({
    local: Object.fromEntries(Object.entries(localStorage)),
    session: Object.fromEntries(Object.entries(sessionStorage)),
  }));
}

test('full renderer reload never persists a sensitive in-flight draft to Web Storage', async ({ page }) => {
  test.setTimeout(90_000);
  const consoleHealth = await gotoOperatorPanel(page, { operatorId: 'recovery-operator' });
  await openPrimaryView(page, 'AI Assistant', 'Welcome to ImperaOS Assistant');
  await page.getByLabel('Message').fill('Create a governed document artifact.');
  await page.getByLabel('Message').press('Enter');
  const openArtifact = page.getByRole('button', { name: 'Open Launch plan' });
  await expect(openArtifact).toBeVisible();
  await installArtifactBridgeStub(page);
  await openArtifact.click();

  const workbench = page.getByRole('complementary', { name: 'Workbench' });
  const editor = workbench
    .getByRole('region', { name: 'Document editor: Launch plan' })
    .getByRole('textbox');
  await expect(editor).toBeVisible({ timeout: 30_000 });
  await page.evaluate(() => {
    const state = (window as unknown as {
      __artifactE2eState: { holdMutations: () => void };
    }).__artifactE2eState;
    state.holdMutations();
  });
  await editor.fill(SENSITIVE_DRAFT);
  await page.waitForFunction(() => {
    const state = (window as unknown as {
      __artifactE2eState?: { snapshot: () => { mutationRequests: unknown[] } };
    }).__artifactE2eState;
    return (state?.snapshot().mutationRequests.length ?? 0) > 0;
  });

  const accessibility = await new AxeBuilder({ page }).include('.assistant-workbench').analyze();
  const criticalViolations = accessibility.violations.filter(
    (violation) => violation.impact === 'critical',
  );
  expect(criticalViolations, JSON.stringify(criticalViolations, null, 2)).toEqual([]);

  const beforeReload = await readWebStorage(page);
  expect(Object.keys(beforeReload.local)).toEqual([SETTINGS_KEY]);
  expect(beforeReload.session).toEqual({});
  expect(JSON.stringify(beforeReload)).not.toContain(SENSITIVE_DRAFT);

  await page.reload({ waitUntil: 'domcontentloaded' });
  await expect(page).toHaveTitle('ImperaOS Operator Panel');
  const afterReload = await readWebStorage(page);
  expect(Object.keys(afterReload.local)).toEqual([SETTINGS_KEY]);
  expect(afterReload.session).toEqual({});
  expect(JSON.stringify(afterReload)).not.toContain(SENSITIVE_DRAFT);
  await expect(page.locator('body')).not.toContainText(SENSITIVE_DRAFT);
  consoleHealth.assertNoCriticalErrors();
});
