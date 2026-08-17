import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { routes } from '../src/routeRegistry.ts';

type ManifestPage = {
  routeId?: string;
  nav?: string;
  heading?: string;
  screenshot?: string;
  renderMs?: number;
};

type Manifest = {
  generatedAtUtc?: string;
  pages?: ManifestPage[];
};

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const APP_ROOT = path.resolve(SCRIPT_DIR, '..');
const REPO_ROOT = findRepoRoot(APP_ROOT);
const ARTIFACT_ROOT = path.join(REPO_ROOT, 'artifacts', 'operator-panel-ui');
const MANIFEST_PATH = path.join(ARTIFACT_ROOT, 'productized-pages', 'manifest.json');
const OUTPUT_PATH = path.join(ARTIFACT_ROOT, 'route-timings', 'route-timing-report.json');
const SLOW_ROUTE_THRESHOLD_MS = Number(process.env.OPERATOR_PANEL_ROUTE_SLOW_MS ?? 2_000);

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

function readManifest(): Manifest {
  if (!fs.existsSync(MANIFEST_PATH)) {
    return {};
  }
  return JSON.parse(fs.readFileSync(MANIFEST_PATH, 'utf8')) as Manifest;
}

const manifest = readManifest();
const manifestPages = new Map((manifest.pages ?? []).map((page) => [String(page.routeId ?? ''), page]));
const rows = routes.map((route) => {
  const manifestPage = manifestPages.get(route.routeId);
  const renderMs = typeof manifestPage?.renderMs === 'number' ? manifestPage.renderMs : null;
  return {
    routeId: route.routeId,
    nav: route.label,
    heading: route.heading,
    renderMs,
    status: renderMs === null ? 'not_measured' : renderMs > SLOW_ROUTE_THRESHOLD_MS ? 'slow' : 'ok',
  };
});
const measuredRows = rows.filter((row) => row.renderMs !== null);
const slowRows = rows.filter((row) => row.status === 'slow');
const maxRenderMs = measuredRows.reduce((max, row) => Math.max(max, row.renderMs ?? 0), 0);
const totalRenderMs = measuredRows.reduce((sum, row) => sum + (row.renderMs ?? 0), 0);
const report = {
  schemaVersion: 'operator-panel.route-timings/v1',
  generatedAtUtc: new Date().toISOString(),
  sourceManifest: fs.existsSync(MANIFEST_PATH) ? path.relative(REPO_ROOT, MANIFEST_PATH) : null,
  thresholdMs: SLOW_ROUTE_THRESHOLD_MS,
  measuredRouteCount: measuredRows.length,
  routeCount: routes.length,
  maxRenderMs,
  averageRenderMs: measuredRows.length > 0 ? Math.round(totalRenderMs / measuredRows.length) : null,
  slowRoutes: slowRows.map((row) => row.routeId),
  routes: rows,
};

fs.mkdirSync(path.dirname(OUTPUT_PATH), { recursive: true });
fs.writeFileSync(OUTPUT_PATH, `${JSON.stringify(report, null, 2)}\n`);

console.log(
  JSON.stringify(
    {
      status: slowRows.length === 0 ? 'passed' : 'warning',
      report: path.relative(REPO_ROOT, OUTPUT_PATH),
      measuredRouteCount: measuredRows.length,
      slowRoutes: slowRows.map((row) => row.routeId),
    },
    null,
    2,
  ),
);
