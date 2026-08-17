import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

type JsonObject = Record<string, unknown>;
type Check = {
  name: string;
  status: 'passed' | 'failed';
  detail: string;
};

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const APP_ROOT = path.resolve(SCRIPT_DIR, '..');
const REPO_ROOT = findRepoRoot(APP_ROOT);
const OPERATOR_ARTIFACT_ROOT = path.join(REPO_ROOT, 'artifacts', 'operator-panel-ui');
const PILOT_ROOT = path.join(REPO_ROOT, 'artifacts', 'pilot-readiness');
const SNAPSHOT_FIXTURE_PATH = path.join(
  REPO_ROOT,
  'contracts',
  'operator_panel',
  'fixtures',
  'control_plane_snapshot_preview.json',
);
const PRODUCTIZED_MANIFEST_PATH = path.join(OPERATOR_ARTIFACT_ROOT, 'productized-pages', 'manifest.json');
const E2E_RESULTS_PATH = path.join(OPERATOR_ARTIFACT_ROOT, 'e2e-json', 'results.json');
const TAURI_SMOKE_PATH = path.join(OPERATOR_ARTIFACT_ROOT, 'tauri-smoke', 'report.json');
const REQUIRED_E2E_SPECS = [
  'pilot-readiness.spec.ts',
  'all-pages-no-placeholder.spec.ts',
  'no-raw-json-primary.spec.ts',
  'evidence.spec.ts',
  'accessibility.spec.ts',
  'responsive.spec.ts',
];

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

function readJson(filePath: string): JsonObject {
  return JSON.parse(fs.readFileSync(filePath, 'utf8')) as JsonObject;
}

function asRecord(value: unknown): JsonObject {
  return typeof value === 'object' && value !== null ? (value as JsonObject) : {};
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function addCheck(checks: Check[], name: string, passed: boolean, detail: string): void {
  checks.push({ name, status: passed ? 'passed' : 'failed', detail });
}

function walkSpecs(suite: JsonObject, rows: Array<{ file: string; passed: boolean }>): void {
  for (const spec of asArray(suite.specs)) {
    const specRecord = asRecord(spec);
    const tests = asArray(specRecord.tests);
    rows.push({
      file: String(specRecord.file ?? ''),
      passed:
        tests.length > 0 &&
        tests.every((test) => {
          const testRecord = asRecord(test);
          return testRecord.status === 'expected' && testRecord.expectedStatus === 'passed';
        }),
    });
  }
  for (const child of asArray(suite.suites)) {
    walkSpecs(asRecord(child), rows);
  }
}

function collectE2eSpecs(): Array<{ file: string; passed: boolean }> {
  if (!fs.existsSync(E2E_RESULTS_PATH)) {
    return [];
  }
  const results = readJson(E2E_RESULTS_PATH);
  const specs: Array<{ file: string; passed: boolean }> = [];
  for (const suite of asArray(results.suites)) {
    walkSpecs(asRecord(suite), specs);
  }
  return specs;
}

function buildClaimGuardMatrix(snapshot: JsonObject): JsonObject {
  const executionSurfaces = asArray(snapshot.executionSurfaces).map(asRecord);
  const alerts = asArray(snapshot.alerts).map(asRecord);
  return {
    schemaVersion: 'pilot-readiness.claim-guard-matrix/v1',
    generatedAtUtc: new Date().toISOString(),
    executionSurfaces: executionSurfaces.map((surface) => ({
      surfaceId: surface.surfaceId,
      label: surface.label,
      status: surface.status,
      reasonCodes: surface.reasonCodes,
      claimId: surface.claimId,
    })),
    blockedAlerts: alerts
      .filter((alert) => alert.status === 'active')
      .map((alert) => ({
        alertId: alert.alertId,
        reasonCode: alert.reasonCode,
        severity: alert.severity,
        linkedEvidencePackId: alert.linkedEvidencePackId,
      })),
  };
}

function writePilotArtifacts(snapshot: JsonObject, checks: Check[]): void {
  const claimGuardMatrix = buildClaimGuardMatrix(snapshot);
  const tauriSmoke = fs.existsSync(TAURI_SMOKE_PATH) ? readJson(TAURI_SMOKE_PATH) : {};
  const productizedManifest = fs.existsSync(PRODUCTIZED_MANIFEST_PATH) ? readJson(PRODUCTIZED_MANIFEST_PATH) : {};

  for (const directory of ['evidence', 'reports', 'screenshots', 'support-bundle', 'tauri-smoke']) {
    fs.mkdirSync(path.join(PILOT_ROOT, directory), { recursive: true });
  }

  fs.writeFileSync(path.join(PILOT_ROOT, 'control-plane-snapshot.json'), `${JSON.stringify(snapshot, null, 2)}\n`);
  fs.writeFileSync(path.join(PILOT_ROOT, 'claim-guard-matrix.json'), `${JSON.stringify(claimGuardMatrix, null, 2)}\n`);
  fs.writeFileSync(
    path.join(PILOT_ROOT, 'tauri-smoke', 'report.json'),
    `${JSON.stringify(tauriSmoke, null, 2)}\n`,
  );
  fs.writeFileSync(
    path.join(PILOT_ROOT, 'reports', 'operator-panel-productized-pages.json'),
    `${JSON.stringify(productizedManifest, null, 2)}\n`,
  );
  fs.writeFileSync(
    path.join(PILOT_ROOT, 'PILOT_READINESS_REPORT.md'),
    [
      '# Pilot Readiness Report',
      '',
      `Generated: ${new Date().toISOString()}`,
      '',
      '| Check | Status | Detail |',
      '|---|---|---|',
      ...checks.map((check) => `| ${check.name} | ${check.status} | ${check.detail.replace(/\|/g, '\\|')} |`),
      '',
      '## Claim Boundaries',
      '',
      '- Computer-use live execution remains qualification-gated.',
      '- Public desktop installer readiness remains blocked without signed clean-machine evidence.',
      '- Preview fixture data is explicit and is not labeled as live pilot evidence.',
      '',
    ].join('\n'),
  );
}

if (!fs.existsSync(SNAPSHOT_FIXTURE_PATH)) {
  console.error(`Pilot readiness assertion failed: missing ${SNAPSHOT_FIXTURE_PATH}`);
  process.exit(1);
}

const checks: Check[] = [];
const snapshot = readJson(SNAPSHOT_FIXTURE_PATH);
const dataSource = asRecord(snapshot.dataSource);
const dashboard = asRecord(snapshot.dashboard);
const agents = asArray(snapshot.agents);
const runs = asArray(snapshot.runs);
const approvals = asArray(snapshot.approvals);
const evidencePacks = asArray(snapshot.evidencePacks);
const reports = asArray(snapshot.reports);
const executionSurfaces = asArray(snapshot.executionSurfaces).map(asRecord);
const computerUseSurface = executionSurfaces.find((surface) => surface.surfaceId === 'computer-use');

addCheck(
  checks,
  'runtimeTruth',
  dataSource.mode === 'preview_fixture' && dataSource.isSilentFallback === false,
  `mode=${String(dataSource.mode)} silentFallback=${String(dataSource.isSilentFallback)}`,
);
addCheck(checks, 'agents', agents.length > 0, `${agents.length} agent(s) in snapshot`);
addCheck(checks, 'runs', runs.length > 0, `${runs.length} run(s) in snapshot`);
addCheck(checks, 'approvals', approvals.length > 0, `${approvals.length} approval(s) in snapshot`);
addCheck(checks, 'evidencePacks', evidencePacks.length > 0, `${evidencePacks.length} pack(s) in snapshot`);
addCheck(checks, 'reports', reports.length > 0, `${reports.length} report(s) in snapshot`);
addCheck(
  checks,
  'computerUseBoundary',
  computerUseSurface?.status === 'blocked',
  `computer-use status=${String(computerUseSurface?.status ?? 'missing')}`,
);
addCheck(
  checks,
  'dashboardEvidenceCount',
  dashboard.evidencePackCount === evidencePacks.length,
  `dashboard=${String(dashboard.evidencePackCount)} actual=${evidencePacks.length}`,
);

const productizedManifest = fs.existsSync(PRODUCTIZED_MANIFEST_PATH) ? readJson(PRODUCTIZED_MANIFEST_PATH) : null;
const pages = productizedManifest ? asArray(productizedManifest.pages) : [];
addCheck(checks, 'productizedPages', pages.length > 0, `${pages.length} productized page screenshot(s)`);

const specs = collectE2eSpecs();
for (const requiredSpec of REQUIRED_E2E_SPECS) {
  const spec = specs.find((row) => row.file.endsWith(requiredSpec));
  addCheck(checks, `e2e:${requiredSpec}`, Boolean(spec?.passed), spec ? 'passed in latest Playwright results' : 'missing');
}

const tauriSmoke = fs.existsSync(TAURI_SMOKE_PATH) ? readJson(TAURI_SMOKE_PATH) : null;
addCheck(
  checks,
  'tauriSmoke',
  tauriSmoke?.status === 'passed',
  tauriSmoke ? `status=${String(tauriSmoke.status)}` : 'missing tauri smoke report',
);

writePilotArtifacts(snapshot, checks);

const failed = checks.filter((check) => check.status === 'failed');
console.log(
  JSON.stringify(
    {
      status: failed.length === 0 ? 'passed' : 'failed',
      failedChecks: failed.map((check) => check.name),
      outputRoot: path.relative(REPO_ROOT, PILOT_ROOT),
    },
    null,
    2,
  ),
);
if (failed.length > 0) {
  process.exit(1);
}
