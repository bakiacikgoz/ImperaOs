import { expect, test } from '@playwright/test';

const viewports = [
  { width: 1440, height: 900 },
  { width: 1280, height: 800 },
  { width: 1024, height: 768 },
  { width: 768, height: 900 },
  { width: 390, height: 844 },
];

test('product home preserves the UI Lab hierarchy and responsive bounds', async ({ page }) => {
  for (const viewport of viewports) {
    await page.setViewportSize(viewport);
    await page.goto('/#/', { waitUntil: 'networkidle' });
    await expect(page.locator('style[data-ui-lab-theme]')).toHaveCount(1);
    await expect(page.locator('.app-shell.has-closed-panels')).toBeVisible();
    await expect(page.locator('.new-work-page.codex-home')).toBeVisible();
    await expect(page.locator('.suggestion-grid.codex-suggestions')).toBeVisible();
    await expect(page.locator('.composer-stack.is-home')).toBeVisible();
    await expect(page.locator('.composer.codex-composer')).toBeVisible();
    const overflow = await page.evaluate(() => Math.max(0, document.documentElement.scrollWidth - document.documentElement.clientWidth));
    expect(overflow).toBeLessThanOrEqual(2);
  }
});

test('collection, settings and search surfaces use the UI Lab contracts', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/#/library', { waitUntil: 'networkidle' });
  await expect(page.locator('.collection-page .collection-list')).toBeVisible();

  await page.goto('/#/settings', { waitUntil: 'networkidle' });
  await expect(page.locator('.settings-shell .settings-sidebar')).toBeVisible();
  await expect(page.locator('.settings-content .settings-page')).toBeVisible();

  await page.goto('/#/', { waitUntil: 'networkidle' });
  await page.keyboard.press(process.platform === 'darwin' ? 'Meta+K' : 'Control+K');
  await expect(page.locator('.modal-backdrop .search-modal')).toBeVisible();
});

test('product adapter styles are removed during a real route transition into the legacy shell', async ({ page }) => {
  await page.goto('/#/', { waitUntil: 'networkidle' });
  await expect(page.locator('style[data-product-shell-adapters]')).toHaveCount(1);
  expect(await page.evaluate(() => {
    const probe = document.createElement('div');
    probe.className = 'native-terminal-surface';
    document.body.append(probe);
    return getComputedStyle(probe).display;
  })).toBe('flex');

  await page.goto('/#/system/settings', { waitUntil: 'networkidle' });
  await expect(page.locator('style[data-ui-lab-theme]')).toHaveCount(0);
  await expect(page.locator('style[data-product-shell-adapters]')).toHaveCount(0);
  expect(await page.evaluate(() => {
    const probe = document.createElement('div');
    probe.className = 'native-terminal-surface';
    document.body.append(probe);
    return getComputedStyle(probe).display;
  })).toBe('block');
});

test('expanded product sidebar keeps Codex proportions, hierarchy, and resize bounds', async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('imperaos-product-shell-preferences-v2', JSON.stringify({
      state: {
        contextRailOpen: false,
        dockOpen: false,
        dockHeight: 240,
        sidebarCollapsed: false,
        sidebarWidth: 260,
        theme: 'dark',
      },
      version: 3,
    }));
  });
  await page.setViewportSize({ width: 919, height: 863 });
  await page.goto('/#/', { waitUntil: 'networkidle' });

  const sidebar = page.getByRole('complementary', { name: 'Product navigation' });
  await expect(sidebar).toBeVisible();
  expect(Math.round((await sidebar.boundingBox())?.width ?? 0)).toBe(260);

  const surface = await page.evaluate(() => {
    const aside = document.querySelector<HTMLElement>('.sidebar.codex-sidebar');
    const frame = document.querySelector<HTMLElement>('.app-frame');
    const primary = document.querySelector<HTMLElement>('.sidebar-primary-action.is-active');
    if (!aside || !frame || !primary) throw new Error('Sidebar parity probes are missing.');
    return {
      sidebar: getComputedStyle(aside).backgroundColor,
      frame: getComputedStyle(frame).backgroundColor,
      primary: getComputedStyle(primary).backgroundColor,
    };
  });
  expect(surface.sidebar).not.toBe('rgb(32, 32, 32)');
  expect(surface.sidebar).not.toBe(surface.frame);
  expect(surface.primary).toBe('rgba(0, 0, 0, 0)');

  const separator = page.getByRole('separator', { name: 'Kenar çubuğu genişliği' });
  let separatorBox = await separator.boundingBox();
  if (!separatorBox) throw new Error('Sidebar resize separator is not visible.');
  await page.mouse.move(separatorBox.x + separatorBox.width / 2, separatorBox.y + 40);
  await page.mouse.down();
  await page.mouse.move(separatorBox.x + 500, separatorBox.y + 40);
  await page.mouse.up();
  await expect.poll(async () => Math.round((await sidebar.boundingBox())?.width ?? 0)).toBe(340);

  separatorBox = await separator.boundingBox();
  if (!separatorBox) throw new Error('Sidebar resize separator disappeared.');
  await page.mouse.move(separatorBox.x + separatorBox.width / 2, separatorBox.y + 40);
  await page.mouse.down();
  await page.mouse.move(separatorBox.x - 500, separatorBox.y + 40);
  await page.mouse.up();
  await expect.poll(async () => Math.round((await sidebar.boundingBox())?.width ?? 0)).toBe(220);

  const overflow = await page.evaluate(() => Math.max(0, document.documentElement.scrollWidth - document.documentElement.clientWidth));
  expect(overflow).toBeLessThanOrEqual(2);
});
