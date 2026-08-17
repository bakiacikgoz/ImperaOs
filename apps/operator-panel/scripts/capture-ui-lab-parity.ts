import { chromium, type Page } from '@playwright/test';
import { spawn, spawnSync, type ChildProcess } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';

const SOURCE_ROOT = process.env.UI_LAB_SOURCE_ROOT ?? '/Users/baki/Documents/ImperaOS-UI-Lab';
const SOURCE_SHA = '165208e90dd37376d5f0a21df22b7a1e7756aab5';
const SOURCE_URL = 'http://127.0.0.1:5191';
const TARGET_URL = 'http://127.0.0.1:5192';
const OUTPUT_ROOT = path.resolve(process.cwd(), '../../artifacts/operator-panel-ui/ui-lab-parity');

const viewports = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'compact', width: 1280, height: 800 },
  { name: 'small-desktop', width: 1024, height: 768 },
  { name: 'tablet', width: 768, height: 900 },
  { name: 'mobile', width: 390, height: 844 },
] as const;

const cases = [
  { name: 'home-collapsed', sourcePath: '/', targetPath: '/', sourceSelector: '.codex-home', targetSelector: '.codex-home', collapsed: true },
  { name: 'home-expanded', sourcePath: '/', targetPath: '/', sourceSelector: '.codex-home', targetSelector: '.codex-home', collapsed: false },
  { name: 'task-conversation', sourcePath: '/task/marketing-report', targetPath: '/task/task-visual', sourceSelector: '.conversation-view', targetSelector: '.conversation-view', collapsed: true },
  { name: 'task-workspace', sourcePath: '/task/marketing-report/workspace', targetPath: '/task/task-visual/workspace', sourceSelector: '.workspace-tabbed-surface', targetSelector: '.workspace-tabbed-surface', collapsed: true },
  { name: 'library', sourcePath: '/library', targetPath: '/library', sourceSelector: '.collection-page', targetSelector: '.collection-page', collapsed: true },
  { name: 'approvals', sourcePath: '/approvals', targetPath: '/approvals', sourceSelector: '.collection-page', targetSelector: '.collection-page', collapsed: true },
  { name: 'agents', sourcePath: '/agents', targetPath: '/agents', sourceSelector: '.collection-page', targetSelector: '.collection-page', collapsed: true },
  { name: 'settings', sourcePath: '/settings/general', targetPath: '/settings', sourceSelector: '.settings-shell', targetSelector: '.settings-shell', collapsed: true },
  { name: 'search-modal', sourcePath: '/', targetPath: '/', sourceSelector: '.search-modal', targetSelector: '.search-modal', collapsed: true, search: true },
] as const;

type Geometry = Record<string, { x: number; y: number; width: number; height: number } | null>;

function startServer(cwd: string, port: number): ChildProcess {
  const command = process.platform === 'win32' ? 'npm.cmd' : 'npm';
  return spawn(command, ['run', 'dev', '--', '--host', '127.0.0.1', '--port', String(port)], {
    cwd,
    env: { ...process.env, VITE_OPERATOR_PANEL_PREVIEW: '1' },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
}

async function waitForServer(url: string) {
  const deadline = Date.now() + 45_000;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch {
      // The child server is still starting.
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`Timed out waiting for ${url}`);
}

async function installTargetFixture(page: Page, theme: 'dark' | 'light', collapsed: boolean) {
  const visualProject = {
    projectId: 'project-visual', workspaceId: 'workspace-visual', title: 'ImperaOS-UI-Denemesi',
    rootRef: 'visual-root', rootDisplayName: 'ImperaOS-UI-Denemesi', status: 'active',
    pinned: true, manualOrder: 0, createdAtUtc: '2026-07-25T00:00:00Z',
    updatedAtUtc: '2026-07-25T00:00:00Z', archivedAtUtc: null,
  };
  const visualTask = {
    taskId: 'task-visual', workspaceId: 'workspace-visual', projectId: 'project-visual',
    title: 'UI Lab entegrasyonunu tamamla', status: 'active', priority: 1, pinned: true,
    manualOrder: 0, reasoningEffort: 'very_high', speedProfile: 'standard',
    approvalProfile: 'risk_based', assistantSessionId: 'session-visual',
    assistantTurnId: null, teamJobId: null, createdAtUtc: '2026-07-25T00:00:00Z',
    updatedAtUtc: '2026-07-25T00:00:00Z', archivedAtUtc: null,
  };
  const preferences = {
    state: { theme, sidebarCollapsed: collapsed, sidebarWidth: 300, contextRailOpen: false, dockOpen: false },
    version: 0,
  };
  await page.addInitScript({
    content: `(() => {
      const project = ${JSON.stringify(visualProject)};
      const task = ${JSON.stringify(visualTask)};
      const ok = (data) => ({ ok: true, data, error: null });
      window.__TAURI_INTERNALS__ = {
        transformCallback() { return 1; },
        unregisterCallback() {},
        async invoke(command) {
          if (command === 'bridge_product_project_list') return ok({ projects: [project], nextCursor: null });
          if (command === 'bridge_product_task_list') return ok({ tasks: [task] });
          if (command === 'bridge_product_task_get') return ok(task);
          if (command === 'bridge_product_task_message_list') return ok({ messages: [
            { messageId: 'message-user', workspaceId: 'workspace-visual', taskId: 'task-visual', role: 'user', body: 'UI Lab temasını mevcut ürüne eksiksiz uygula.', createdAtUtc: '2026-07-25T00:00:00Z' },
            { messageId: 'message-assistant', workspaceId: 'workspace-visual', taskId: 'task-visual', role: 'assistant', body: 'Tema sözleşmesi uygulandı ve doğrulama kanıtları hazırlandı.', createdAtUtc: '2026-07-25T00:00:01Z' }
          ] });
          if (command === 'bridge_product_task_link_list') return ok({ links: [] });
          if (command === 'bridge_assistant_provider_models') return ok({ profile: 'balanced', provider: 'all', providers: [], models: [], generatedAtUtc: '2026-07-25T00:00:00Z' });
          if (command === 'bridge_artifact_list') return ok({ items: [], nextCursor: null });
          if (command.includes('approval')) return ok({ pending: [] });
          if (command.includes('agent')) return ok({ agents: [] });
          return null;
        }
      };
      localStorage.setItem('imperaos-product-shell-preferences-v2', ${JSON.stringify(JSON.stringify(preferences))});
    })();`,
  });
}

async function seedPreferences(page: Page, target: 'source' | 'target', theme: 'dark' | 'light', collapsed: boolean) {
  await page.addInitScript(({ targetKind, selectedTheme, sidebarCollapsed }) => {
    if (targetKind === 'source') {
      localStorage.setItem('imperaos-ui-preferences', JSON.stringify({
        state: {
          theme: selectedTheme,
          sidebarCollapsed,
          sidebarWidth: 300,
          rightRailOpen: false,
          bottomDockOpen: false,
          bottomDockTab: 'activity',
          conversationWidth: 54,
          rightRailWidth: 392,
          bottomDockHeight: 290,
          workspaceId: 'duzey',
        },
        version: 6,
      }));
    } else {
      localStorage.setItem('imperaos-product-shell-preferences-v2', JSON.stringify({
        state: {
          theme: selectedTheme,
          sidebarCollapsed,
          sidebarWidth: 300,
          contextRailOpen: false,
          dockOpen: false,
        },
        version: 0,
      }));
    }
  }, { targetKind: target, selectedTheme: theme, sidebarCollapsed: collapsed });
}

async function preparePage(page: Page, url: string, selector: string, search = false) {
  await page.goto(url, { waitUntil: 'networkidle' });
  if (search) await page.keyboard.press(process.platform === 'darwin' ? 'Meta+K' : 'Control+K');
  try {
    await page.locator(selector).first().waitFor({ state: 'visible', timeout: 20_000 });
  } catch (cause) {
    const visibleText = (await page.locator('body').innerText()).slice(0, 800);
    const runtimeState = await page.evaluate(() => ({
      hasTauriInternals: '__TAURI_INTERNALS__' in window,
      invokeType: typeof (window as unknown as { __TAURI_INTERNALS__?: { invoke?: unknown } }).__TAURI_INTERNALS__?.invoke,
    }));
    throw new Error(`Parity selector ${selector} was not visible at ${url}.\n${JSON.stringify(runtimeState)}\n${visibleText}`, { cause });
  }
  await page.addStyleTag({ content: '*,*::before,*::after{animation:none!important;transition:none!important;caret-color:transparent!important}' });
  await page.evaluate(() => document.fonts.ready);
}

async function readGeometry(page: Page): Promise<Geometry> {
  return page.evaluate(() => {
    const selectors = ['.welcome-stage', '.welcome-hero', '.suggestion-grid', '.composer-context-bar', '.codex-composer'];
    return Object.fromEntries(selectors.map((selector) => {
      const element = document.querySelector(selector);
      if (!element) return [selector, null];
      const box = element.getBoundingClientRect();
      return [selector, { x: box.x, y: box.y, width: box.width, height: box.height }];
    }));
  });
}

async function main() {
  if (!fs.existsSync(path.join(SOURCE_ROOT, 'package.json'))) {
    throw new Error(`UI Lab source is unavailable at ${SOURCE_ROOT}`);
  }
  const sourceRevision = spawnSync('git', ['rev-parse', 'HEAD'], {
    cwd: SOURCE_ROOT,
    encoding: 'utf8',
  });
  const sourceHead = sourceRevision.stdout.trim();
  if (sourceRevision.status !== 0 || sourceHead !== SOURCE_SHA) {
    throw new Error(`UI Lab source revision mismatch: expected ${SOURCE_SHA}, received ${sourceHead || 'unavailable'}`);
  }
  fs.mkdirSync(OUTPUT_ROOT, { recursive: true });
  const sourceServer = startServer(SOURCE_ROOT, 5191);
  const targetServer = startServer(process.cwd(), 5192);
  const children = [sourceServer, targetServer];
  const browser = await chromium.launch({ headless: true });
  const rows: Array<Record<string, unknown>> = [];
  const selectedCases = process.env.UI_LAB_PARITY_CASE
    ? cases.filter((item) => item.name === process.env.UI_LAB_PARITY_CASE)
    : cases;
  const selectedViewports = process.env.UI_LAB_PARITY_VIEWPORT
    ? viewports.filter((item) => item.name === process.env.UI_LAB_PARITY_VIEWPORT)
    : viewports;

  try {
    await Promise.all([waitForServer(SOURCE_URL), waitForServer(TARGET_URL)]);
    for (const theme of ['dark', 'light'] as const) {
      for (const viewport of selectedViewports) {
        for (const captureCase of selectedCases) {
          const sourceContext = await browser.newContext({ viewport });
          const targetContext = await browser.newContext({ viewport });
          const sourcePage = await sourceContext.newPage();
          const targetPage = await targetContext.newPage();
          await installTargetFixture(targetPage, theme, captureCase.collapsed);
          await seedPreferences(sourcePage, 'source', theme, captureCase.collapsed);
          await preparePage(targetPage, `${TARGET_URL}/#${captureCase.targetPath}`, captureCase.targetSelector, captureCase.search);
          await preparePage(sourcePage, `${SOURCE_URL}${captureCase.sourcePath}`, captureCase.sourceSelector, captureCase.search);
          const stem = `${theme}-${viewport.name}-${captureCase.name}`;
          const sourceFile = path.join(OUTPUT_ROOT, `${stem}-source.png`);
          const targetFile = path.join(OUTPUT_ROOT, `${stem}-target.png`);
          await sourcePage.screenshot({ path: sourceFile, fullPage: false });
          await targetPage.screenshot({ path: targetFile, fullPage: false });
          rows.push({
            theme,
            viewport,
            case: captureCase.name,
            sourceFile: path.basename(sourceFile),
            targetFile: path.basename(targetFile),
            sourceGeometry: captureCase.name.startsWith('home') ? await readGeometry(sourcePage) : undefined,
            targetGeometry: captureCase.name.startsWith('home') ? await readGeometry(targetPage) : undefined,
          });
          await Promise.all([sourceContext.close(), targetContext.close()]);
        }
      }
    }
  } finally {
    await browser.close();
    children.forEach((child) => child.kill('SIGTERM'));
  }

  fs.writeFileSync(path.join(OUTPUT_ROOT, 'report.json'), JSON.stringify({
    sourceSha: SOURCE_SHA,
    generatedAtUtc: new Date().toISOString(),
    rows,
  }, null, 2));
  fs.writeFileSync(path.join(OUTPUT_ROOT, 'report.html'), [
    '<!doctype html><meta charset="utf-8"><title>UI Lab parity</title>',
    '<style>body{font:14px system-ui;background:#111;color:#eee}section{margin:24px 0}div{display:grid;grid-template-columns:1fr 1fr;gap:8px}img{width:100%;border:1px solid #444}h2{font-size:15px}</style>',
    `<h1>UI Lab parity · ${SOURCE_SHA}</h1>`,
    ...rows.map((row) => `<section><h2>${row.theme} · ${(row.viewport as { name: string }).name} · ${row.case}</h2><div><img src="${row.sourceFile}"><img src="${row.targetFile}"></div></section>`),
  ].join('\n'));
  console.log(`Captured ${rows.length} source/target parity cases in ${OUTPUT_ROOT}`);
}

await main();
