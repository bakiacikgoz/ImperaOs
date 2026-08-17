import { expect, type Page } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

const SETTINGS_KEY = 'imperaos.operator.settings.v1';
const REPO_ROOT = findRepoRoot(process.cwd());

type E2eSettings = {
  mode: 'auto' | 'external' | 'bundled';
  cliPath: string;
  bundledPythonPath: string;
  profile: string;
  rootDir: string;
  operatorId: string;
  locale: 'auto' | 'en' | 'tr';
  remoteTelemetry: boolean;
  updaterMode: 'off' | 'manual' | 'auto';
  debugRaw: boolean;
  theme: 'light' | 'dark' | 'system';
  assistantProvider: string;
  assistantFallbackProvider: string;
  assistantModel: string;
  assistantHfModelId: string;
};

type ConsoleHealth = {
  errors: string[];
  assertNoCriticalErrors: () => void;
};

type LayoutMetrics = {
  viewportWidth: number;
  viewportHeight: number;
  clientWidth: number;
  documentScrollWidth: number;
  bodyScrollWidth: number;
  overflowX: number;
};

const defaultSettings: E2eSettings = {
  mode: 'auto',
  cliPath: '',
  bundledPythonPath: '',
  profile: 'balanced',
  rootDir: '.imperaos/e2e-preview/jobs',
  operatorId: '',
  locale: 'en',
  remoteTelemetry: false,
  updaterMode: 'off',
  debugRaw: false,
  theme: 'light',
  assistantProvider: '',
  assistantFallbackProvider: '',
  assistantModel: '',
  assistantHfModelId: '',
};

const ignoredConsolePatterns = [/favicon/i, /ResizeObserver loop/i];

function findRepoRoot(start: string): string {
  let current = start;
  while (current !== path.dirname(current)) {
    if (fs.existsSync(path.join(current, 'pnpm-workspace.yaml')) || fs.existsSync(path.join(current, '.git'))) {
      return current;
    }
    current = path.dirname(current);
  }
  return start;
}

export function collectConsoleHealth(page: Page): ConsoleHealth {
  const errors: string[] = [];

  page.on('console', (message) => {
    if (message.type() === 'error') {
      errors.push(message.text());
    }
  });
  page.on('pageerror', (error) => {
    errors.push(error.message);
  });

  return {
    errors,
    assertNoCriticalErrors() {
      expect(errors.filter((message) => !ignoredConsolePatterns.some((pattern) => pattern.test(message)))).toEqual([]);
    },
  };
}

export async function gotoOperatorPanel(page: Page, settings: Partial<E2eSettings> = {}): Promise<ConsoleHealth> {
  const consoleHealth = collectConsoleHealth(page);
  const seededSettings = { ...defaultSettings, ...settings };

  await page.addInitScript(
    ({ key, value }) => {
      // Each scenario defines its own operator authority. Do not inherit a
      // persisted identity from another scenario, but preserve a setting that
      // the current scenario saves before it reloads the page.
      if (localStorage.getItem(key) === null) {
        localStorage.setItem(key, JSON.stringify(value));
      }
    },
    { key: SETTINGS_KEY, value: seededSettings },
  );

  // The v2 product shell is the default application. Legacy E2E scenarios
  // exercise the retained rollback shell through its explicit system route.
  await page.goto('/#/system', { waitUntil: 'domcontentloaded' });
  await expect(page).toHaveTitle('ImperaOS Operator Panel');
  await expect(page.locator('#root')).toContainText('Mission Control');
  await expect(page.locator('.pill-preview')).toHaveText('Preview');
  await expectFrameworkOverlayAbsent(page);

  return consoleHealth;
}

export async function openPrimaryView(page: Page, navName: string, headingName: string): Promise<void> {
  const nav = page.getByRole('navigation', { name: 'Ana navigasyon' });
  await nav.getByRole('button', { name: navName, exact: true }).click();
  const pageHeading = page.getByRole('heading', { name: headingName, exact: true, level: 2 });
  if ((await pageHeading.count()) > 0) {
    await expect(pageHeading).toBeVisible();
  } else {
    await expect(page.getByRole('heading', { name: headingName, exact: true, level: 1 })).toBeVisible();
  }
  await expectFrameworkOverlayAbsent(page);
}

export async function expectFrameworkOverlayAbsent(page: Page): Promise<void> {
  await expect(
    page.locator('vite-error-overlay, [data-nextjs-dialog-overlay], .webpack-dev-server-client-overlay'),
  ).toHaveCount(0);
}

export function e2eArtifactPath(...segments: string[]): string {
  const artifactPath = path.resolve(REPO_ROOT, 'artifacts/operator-panel-ui', ...segments);
  fs.mkdirSync(path.dirname(artifactPath), { recursive: true });
  return artifactPath;
}

export async function saveE2eScreenshot(page: Page, name: string): Promise<void> {
  await page.screenshot({ path: e2eArtifactPath('screenshots', `${name}.png`), fullPage: false });
}

export async function readLayoutMetrics(page: Page): Promise<LayoutMetrics> {
  return page.evaluate(() => {
    const documentElement = document.documentElement;
    const body = document.body;
    const clientWidth = documentElement.clientWidth;
    const documentScrollWidth = documentElement.scrollWidth;
    const bodyScrollWidth = body?.scrollWidth ?? 0;
    const maxScrollWidth = Math.max(documentScrollWidth, bodyScrollWidth);

    return {
      viewportWidth: window.innerWidth,
      viewportHeight: window.innerHeight,
      clientWidth,
      documentScrollWidth,
      bodyScrollWidth,
      overflowX: Math.max(0, maxScrollWidth - clientWidth),
    };
  });
}

export async function expectNoHorizontalOverflow(page: Page, context: string): Promise<LayoutMetrics> {
  const metrics = await readLayoutMetrics(page);
  expect(
    metrics.overflowX,
    `${context} horizontal overflow: ${JSON.stringify(metrics)}`,
  ).toBeLessThanOrEqual(2);
  return metrics;
}

export function operationOutput(page: Page) {
  return page
    .locator('article.page-card')
    .filter({ has: page.getByRole('heading', { name: 'Operation output', exact: true }) });
}
