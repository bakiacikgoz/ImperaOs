import { expect, test } from '@playwright/test';

import { gotoOperatorPanel, openPrimaryView } from './helpers';

test('AI Assistant model selection is visible and used before sending a preview message', async ({ page }) => {
  const consoleHealth = await gotoOperatorPanel(page, { operatorId: 'qa-operator' });
  await openPrimaryView(page, 'AI Assistant', 'Welcome to ImperaOS Assistant');

  await expect(page.getByRole('textbox', { name: 'Search' })).toBeEnabled();
  await expect(page.getByRole('button', { name: 'Terminal' })).toBeEnabled();
  await expect(page.getByRole('button', { name: 'Notifications' })).toBeEnabled();

  await page.getByLabel('Assistant provider').selectOption('ollama');
  await page.getByLabel('Assistant model', { exact: true }).fill('qwen3.5:4b');
  await page.getByLabel('Assistant fallback provider').selectOption('transformers');

  await expect(page.getByLabel('Selected assistant model')).toContainText('ollama / qwen3.5:4b');
  const desktopContextRail = page.locator('.assistant-context-rail-desktop').getByLabel('Assistant context rail');
  if (await desktopContextRail.isVisible()) {
    await expect(desktopContextRail.getByText('Assistant Runtime')).toBeVisible();
    await expect(desktopContextRail.getByText('Effective', { exact: true })).toBeVisible();
  } else {
    await page.getByRole('button', { name: 'Open assistant context' }).click();
    const contextPanel = page.getByRole('complementary', { name: 'Assistant context panel' });
    await expect(contextPanel.getByText('Assistant Runtime')).toBeVisible();
    await expect(contextPanel.getByText('Effective', { exact: true })).toBeVisible();
    await contextPanel.getByLabel('Close assistant context').click();
  }

  await page.getByLabel('Message').fill('Summarize the active run safely.');
  await page.getByLabel('Message').press('Enter');

  await expect(page.getByText('Summarize the active run safely.')).toBeVisible();
  await expect(page.getByText('The selected run is blocked by an approval gate.')).toBeVisible();
  await page.getByRole('textbox', { name: 'Search' }).fill('approval');
  await expect(page.getByRole('status', { name: 'Search' }).getByText('Assistant response')).toBeVisible();
  await page.getByRole('button', { name: 'Notifications' }).click();
  await expect(page.getByRole('status', { name: 'Notifications' }).getByText('Assistant status')).toBeVisible();
  await page.getByRole('button', { name: 'Terminal' }).click();
  await expect(page.getByRole('heading', { name: 'Runs', exact: true, level: 2 })).toBeVisible();
  await page.getByRole('navigation', { name: 'Ana navigasyon' }).getByRole('button', { name: 'AI Assistant' }).click();
  await expect(page.getByText('The selected run is blocked by an approval gate.')).toBeVisible();
  await expect
    .poll(async () => {
      return page.evaluate(() => {
        const transcript = document.querySelector('.assistant-transcript');
        const composer = document.querySelector('.assistant-composer');
        const turns = Array.from(document.querySelectorAll('.assistant-turn'));
        const lastTurn = turns.at(-1);
        if (!transcript || !composer || !lastTurn) {
          return { composerOverlapsTranscript: true, latestContentHiddenBehindComposer: true, followsLatest: false };
        }
        const transcriptRect = transcript.getBoundingClientRect();
        const composerRect = composer.getBoundingClientRect();
        const lastTurnRect = lastTurn.getBoundingClientRect();
        const maxScrollTop = Math.max(0, transcript.scrollHeight - transcript.clientHeight);
        return {
          composerOverlapsTranscript: composerRect.top < transcriptRect.bottom - 1,
          latestContentHiddenBehindComposer:
            lastTurnRect.bottom > transcriptRect.bottom + 1 || lastTurnRect.bottom > composerRect.top + 1,
          followsLatest: maxScrollTop <= 24 || transcript.scrollTop >= maxScrollTop - 8,
        };
      });
    })
    .toEqual({ composerOverlapsTranscript: false, latestContentHiddenBehindComposer: false, followsLatest: true });
  await expect(page.getByLabel('Selected assistant model')).toContainText('ollama / qwen3.5:4b');
  consoleHealth.assertNoCriticalErrors();
});
