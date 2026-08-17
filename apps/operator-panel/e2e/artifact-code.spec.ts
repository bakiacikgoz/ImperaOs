import { expect, test } from '@playwright/test';

import { codeArtifactCommands, codeArtifactExportedText, installCodeArtifactBridgeStub } from './artifact-helpers';
import { gotoOperatorPanel, openPrimaryView } from './helpers';

test('code artifact uses local Monaco workers, autosaves, reopens, and exports without execution', async ({ page }) => {
  test.setTimeout(90_000);
  const externalRequests: string[] = [];
  const documentCsp: string[] = [];
  page.on('request', (request) => {
    const url = request.url();
    if (!url.startsWith('http://127.0.0.1:5173') && !url.startsWith('blob:') && !url.startsWith('data:')) {
      externalRequests.push(url);
    }
  });
  page.on('response', (response) => {
    if (response.request().resourceType() === 'document') {
      documentCsp.push(response.headers()['content-security-policy'] ?? '');
    }
  });
  await page.addInitScript(() => {
    window.addEventListener('securitypolicyviolation', (event) => {
      const evidence = document.createElement('meta');
      evidence.setAttribute('name', 'artifact-code-csp-violation');
      evidence.setAttribute('content', JSON.stringify({
        directive: event.violatedDirective, blockedUri: event.blockedURI, sample: event.sample,
      }));
      document.head.append(evidence);
    });
  });

  const consoleHealth = await gotoOperatorPanel(page, { operatorId: 'code-operator' });
  expect(documentCsp[0]).toContain("script-src 'self'");
  expect(documentCsp[0]).toContain("worker-src 'self' blob:");
  expect(documentCsp[0]).not.toContain("'unsafe-eval'");
  await openPrimaryView(page, 'AI Assistant', 'Welcome to ImperaOS Assistant');
  await page.getByLabel('Message').fill('Open a governed code artifact.');
  await page.getByLabel('Message').press('Enter');
  await expect(page.getByRole('button', { name: 'Open Launch plan' })).toBeVisible();

  await installCodeArtifactBridgeStub(page);
  await page.getByRole('button', { name: 'Open Launch plan' }).dispatchEvent('click');
  const workbench = page.getByRole('complementary', { name: 'Workbench' });
  const editor = workbench.getByRole('region', { name: 'Code editor: Safe code' });
  await expect(editor).toBeVisible({ timeout: 30_000 });
  await expect(editor.getByText('Code execution is disabled.', { exact: false })).toBeVisible();
  await expect(workbench.getByRole('button', { name: /run|execute|terminal/i })).toHaveCount(0);

  const textbox = editor.getByRole('textbox', { name: 'Code text: main.py' });
  await expect(textbox).toHaveAttribute('aria-multiline', 'true');
  const monaco = editor.locator('.monaco-editor');
  await expect(monaco).toBeVisible({ timeout: 30_000 });
  await textbox.focus();
  await page.context().setOffline(true);
  await textbox.evaluate((element, text) => {
    const input = element as HTMLTextAreaElement;
    input.value = text;
    input.dispatchEvent(new InputEvent('input', {
      bubbles: true,
      data: text,
      inputType: 'insertText',
    }));
  }, "print('saved locally')\n");
  await expect(editor.locator('.view-lines')).toContainText("print('saved locally')");
  await expect.poll(async () => (await codeArtifactCommands(page)).filter((command) => command === 'bridge_artifact_mutate'))
    .toEqual(['bridge_artifact_mutate']);
  await expect(workbench.getByLabel('Artifact status').getByText('Revision 2')).toBeVisible();

  await workbench.getByRole('button', { name: 'Close Safe code' }).dispatchEvent('click');
  await workbench.getByRole('button', { name: 'Refresh', exact: true }).click();
  await workbench.getByLabel('Artifact navigator').getByRole('button', { name: /Safe code/ }).click();
  await expect(editor.locator('.view-lines')).toContainText("print('saved locally')");
  await workbench.getByRole('button', { name: 'Export', exact: true }).click();
  const exportDialog = workbench.getByRole('dialog', { name: 'Export Safe code' });
  await exportDialog.getByLabel('Export format').selectOption('source');
  await exportDialog.getByRole('button', { name: 'Choose destination and export' }).click();
  await expect.poll(async () => (await codeArtifactCommands(page)).filter((command) => command.includes('export')))
    .toEqual(['bridge_artifact_export_begin', 'bridge_artifact_export_commit']);
  await expect.poll(() => codeArtifactExportedText(page)).toBe(
    "print('saved locally')\nprint('display only')\n",
  );

  expect(externalRequests).toEqual([]);
  const violations = page.locator('meta[name="artifact-code-csp-violation"]');
  const violationCount = await violations.count();
  expect(violationCount, violationCount ? await violations.first().getAttribute('content') ?? '' : '').toBe(0);
  consoleHealth.assertNoCriticalErrors();
});
