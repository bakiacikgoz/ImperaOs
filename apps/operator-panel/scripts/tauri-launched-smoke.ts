import { spawn, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

type CheckStatus = 'passed' | 'failed' | 'skipped' | 'conditional';
type Check = {
  name: string;
  status: CheckStatus;
  detail: string;
};

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const APP_ROOT = path.resolve(SCRIPT_DIR, '..');
const REPO_ROOT = findRepoRoot(APP_ROOT);
const OUTPUT_ROOT = path.join(REPO_ROOT, 'artifacts', 'operator-panel-ui', 'tauri-smoke');
const LEGACY_REPORT_PATH = path.join(REPO_ROOT, 'artifacts', 'operator-panel-ui', 'tauri-bridge-smoke.json');
const REPORT_PATH = path.join(OUTPUT_ROOT, 'report.json');
const MARKDOWN_PATH = path.join(OUTPUT_ROOT, 'TAURI_LAUNCHED_SMOKE.md');
const MODE = readMode();
const RUN_LAUNCH = MODE === 'launched' || process.argv.includes('--launch') || process.env.OPERATOR_PANEL_TAURI_LAUNCH === '1';
const SKIP_RUST = process.argv.includes('--skip-rust');
const LAUNCH_TIMEOUT_MS = readTimeoutMs();
const REQUIRED_HANDLERS = [
  'bridge_handshake',
  'bridge_config_resolve',
  'bridge_control_plane_snapshot',
  'bridge_assistant_provider_models',
  'bridge_assistant_start_turn',
  'bridge_assistant_cancel_turn',
  'bridge_team_list',
  'bridge_approval_pending',
  'bridge_control_plane_evidence_verify',
  'bridge_control_plane_claims_verify',
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

function readTimeoutMs(): number {
  const raw = Number(process.env.OPERATOR_PANEL_TAURI_LAUNCH_TIMEOUT_MS ?? 20_000);
  return Number.isFinite(raw) && raw >= 5_000 ? raw : 20_000;
}

function readMode(): 'contract' | 'launched' {
  const modeIndex = process.argv.indexOf('--mode');
  const mode = modeIndex >= 0 ? process.argv[modeIndex + 1] : undefined;
  if (mode === 'launched') {
    return 'launched';
  }
  return 'contract';
}

function addCheck(checks: Check[], name: string, status: CheckStatus, detail: string): void {
  checks.push({ name, status, detail });
}

function readJson(filePath: string): Record<string, unknown> {
  return JSON.parse(fs.readFileSync(filePath, 'utf8')) as Record<string, unknown>;
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null ? (value as Record<string, unknown>) : {};
}

function runRustBridgeSmoke(checks: Check[]): void {
  if (SKIP_RUST) {
    addCheck(checks, 'rustBridgeTests', 'skipped', 'Skipped by --skip-rust.');
    return;
  }

  const result = spawnSync('cargo', ['test', '-q', '--manifest-path', 'apps/operator-panel/src-tauri/Cargo.toml'], {
    cwd: REPO_ROOT,
    encoding: 'utf8',
  });
  if (result.status === 0) {
    addCheck(checks, 'rustBridgeTests', 'passed', 'Tauri bridge Rust tests passed.');
    return;
  }

  const output = `${result.stdout}\n${result.stderr}`.trim();
  addCheck(checks, 'rustBridgeTests', 'failed', output.slice(-1_200) || 'cargo test failed.');
}

function checkTauriContract(checks: Check[]): void {
  const configPath = path.join(APP_ROOT, 'src-tauri', 'tauri.conf.json');
  const libPath = path.join(APP_ROOT, 'src-tauri', 'src', 'lib.rs');
  const packagePath = path.join(APP_ROOT, 'package.json');

  if (!fs.existsSync(configPath)) {
    addCheck(checks, 'tauriConfig', 'failed', 'src-tauri/tauri.conf.json is missing.');
  } else {
    const config = readJson(configPath);
    addCheck(checks, 'tauriConfig', 'passed', `devUrl=${asRecord(config.build).devUrl ?? 'unknown'}`);
  }

  const packageJson = readJson(packagePath);
  const scripts = asRecord(packageJson.scripts);
  addCheck(
    checks,
    'tauriScripts',
    scripts['tauri:dev'] && scripts['tauri:build'] ? 'passed' : 'failed',
    'package scripts expose tauri:dev and tauri:build.',
  );

  const libSource = fs.existsSync(libPath) ? fs.readFileSync(libPath, 'utf8') : '';
  const missingHandlers = REQUIRED_HANDLERS.filter((handler) => !libSource.includes(`bridge::${handler}`));
  addCheck(
    checks,
    'bridgeHandlers',
    missingHandlers.length === 0 ? 'passed' : 'failed',
    missingHandlers.length === 0
      ? `Registered handlers: ${REQUIRED_HANDLERS.join(', ')}.`
      : `Missing handlers: ${missingHandlers.join(', ')}.`,
  );
}

function checkPreviewRuntimeTruth(checks: Check[]): void {
  const fixturePath = path.join(REPO_ROOT, 'contracts', 'operator_panel', 'fixtures', 'control_plane_snapshot_preview.json');
  const snapshot = readJson(fixturePath);
  const dataSource = asRecord(snapshot.dataSource);
  const evidencePacks = Array.isArray(snapshot.evidencePacks) ? snapshot.evidencePacks : [];
  const approvals = Array.isArray(snapshot.approvals) ? snapshot.approvals : [];
  const runs = Array.isArray(snapshot.runs) ? snapshot.runs : [];

  addCheck(
    checks,
    'runtimeTruthFixture',
    dataSource.isSilentFallback === false && dataSource.mode === 'preview_fixture' ? 'passed' : 'failed',
    `mode=${String(dataSource.mode)} silentFallback=${String(dataSource.isSilentFallback)}`,
  );
  addCheck(
    checks,
    'controlPlaneSnapshotFixture',
    evidencePacks.length > 0 && approvals.length > 0 && runs.length > 0 ? 'passed' : 'failed',
    `runs=${runs.length} approvals=${approvals.length} evidencePacks=${evidencePacks.length}`,
  );
}

function checkNoPreviewFallbackInProductMode(checks: Check[]): void {
  const bridgeSource = fs.readFileSync(path.join(APP_ROOT, 'src', 'bridge.ts'), 'utf8');
  const hasExplicitTrue = /previewFallbackAllowed\s*[:=]\s*true/.test(bridgeSource);
  addCheck(
    checks,
    'assistantPreviewFallback',
    hasExplicitTrue ? 'failed' : 'passed',
    hasExplicitTrue
      ? 'previewFallbackAllowed=true was found in product bridge source.'
      : 'No product-mode previewFallbackAllowed=true marker found.',
  );
}

async function runOptionalLaunch(checks: Check[]): Promise<void> {
  if (!RUN_LAUNCH) {
    addCheck(
      checks,
      'desktopLaunch',
      'conditional',
      'Real launched GUI probe not executed. Set OPERATOR_PANEL_TAURI_LAUNCH=1 or pass --launch.',
    );
    return;
  }

  await new Promise<void>((resolve) => {
    const child = spawn('corepack', ['pnpm', '--dir', 'apps/operator-panel', 'tauri:dev'], {
      cwd: REPO_ROOT,
      env: { ...process.env, VITE_OPERATOR_PANEL_PREVIEW: '1' },
      stdio: ['ignore', 'pipe', 'pipe'],
      detached: process.platform !== 'win32',
    });
    let output = '';
    let settled = false;
    const append = (chunk: Buffer) => {
      output += chunk.toString('utf8');
      output = output.slice(-4_000);
    };
    const terminateChild = () => {
      child.stdout?.destroy();
      child.stderr?.destroy();
      if (child.pid) {
        try {
          if (process.platform === 'win32') {
            child.kill('SIGTERM');
          } else {
            process.kill(-child.pid, 'SIGTERM');
          }
        } catch {
          child.kill('SIGTERM');
        }
      }
      child.unref();
    };
    const finish = (name: string, status: CheckStatus, detail: string) => {
      if (settled) {
        return;
      }
      settled = true;
      clearTimeout(timer);
      addCheck(checks, name, status, detail);
      resolve();
    };
    child.stdout.on('data', append);
    child.stderr.on('data', append);
    const timer = setTimeout(() => {
      const failed = /panic|error while running operator panel|failed/i.test(output);
      terminateChild();
      finish(
        'desktopLaunch',
        failed ? 'failed' : 'passed',
        failed ? output.slice(-1_200) : `Tauri dev process stayed alive for ${LAUNCH_TIMEOUT_MS}ms.`,
      );
    }, LAUNCH_TIMEOUT_MS);
    child.on('exit', (code) => {
      finish(
        'desktopLaunch',
        code === 0 ? 'passed' : 'failed',
        `Tauri dev exited with code ${String(code)}. ${output.slice(-1_200)}`,
      );
    });
    child.on('error', (error) => {
      terminateChild();
      finish('desktopLaunch', 'failed', error.message);
    });
  });

  const launched = checks.find((check) => check.name === 'desktopLaunch');
  if (launched?.status === 'passed') {
    addCheck(
      checks,
      'launchedBridgeProbe',
      'conditional',
      'partial: Tauri process launched; bridge command instrumentation is contract/Rust-harness backed in this smoke.',
    );
    addCheck(
      checks,
      'assistantStartTurn',
      'conditional',
      'setup_required or stream event must be verified by local assistant runtime gate; no fake_response is accepted here.',
    );
  }
}

function writeReports(checks: Check[]): boolean {
  fs.mkdirSync(path.join(OUTPUT_ROOT, 'screenshots'), { recursive: true });
  const failed = checks.filter((check) => check.status === 'failed');
  const conditional = checks.filter((check) => check.status === 'conditional');
  const report = {
    schemaVersion: 'operator-panel.tauri-launched-smoke/v1',
    generatedAtUtc: new Date().toISOString(),
    mode: MODE,
    status: failed.length > 0 ? 'failed' : conditional.length > 0 ? 'conditional' : 'passed',
    launchRequested: RUN_LAUNCH,
    launchTimeoutMs: LAUNCH_TIMEOUT_MS,
    desktopLaunch: checks.find((check) => check.name === 'desktopLaunch') ?? null,
    launchedBridgeProbe:
      checks.find((check) => check.name === 'launchedBridgeProbe') ??
      (RUN_LAUNCH ? { status: 'failed', detail: 'desktop launch did not pass.' } : { status: 'not_executed' }),
    assistantStartTurn:
      checks.find((check) => check.name === 'assistantStartTurn') ??
      { status: 'conditional', detail: 'assistant start-turn is covered by assistant runtime gate.' },
    checks,
    notes: [
      'Default mode verifies the Tauri bridge contract, Rust bridge smoke tests, runtime truth fixture, and reportability.',
      'Set OPERATOR_PANEL_TAURI_LAUNCH=1 for a local GUI launch probe on a desktop session.',
      'Launched bridge instrumentation is partial unless a desktop automation harness is available.',
      'No live computer-use gates are opened by this smoke.',
    ],
  };
  fs.writeFileSync(REPORT_PATH, `${JSON.stringify(report, null, 2)}\n`);
  fs.writeFileSync(LEGACY_REPORT_PATH, `${JSON.stringify(report, null, 2)}\n`);
  fs.writeFileSync(
    MARKDOWN_PATH,
    [
      '# Tauri Launched Smoke',
      '',
      `Status: **${report.status}**`,
      `Mode: **${report.mode}**`,
      `Generated: ${report.generatedAtUtc}`,
      `Launch requested: ${String(RUN_LAUNCH)}`,
      '',
      '| Check | Status | Detail |',
      '|---|---|---|',
      ...checks.map((check) => `| ${check.name} | ${check.status} | ${check.detail.replace(/\|/g, '\\|')} |`),
      '',
      '## Notes',
      ...report.notes.map((note) => `- ${note}`),
      '',
    ].join('\n'),
  );
  return failed.length === 0;
}

const checks: Check[] = [];
checkTauriContract(checks);
checkPreviewRuntimeTruth(checks);
checkNoPreviewFallbackInProductMode(checks);
runRustBridgeSmoke(checks);
await runOptionalLaunch(checks);

const passed = writeReports(checks);
const report = readJson(REPORT_PATH);
console.log(JSON.stringify({ status: report.status, report: path.relative(REPO_ROOT, REPORT_PATH) }, null, 2));
if (!passed) {
  process.exit(1);
}
