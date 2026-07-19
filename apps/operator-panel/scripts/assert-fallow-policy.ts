import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';
import {
  computeVerdict,
  findRepoRoot,
  readJson,
  type CodeIntelligenceSummary,
} from './fallow-policy.ts';

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const APP_ROOT = path.resolve(SCRIPT_DIR, '..');
const REPO_ROOT = findRepoRoot(APP_ROOT);
const SUMMARY_PATH = path.join(REPO_ROOT, 'artifacts', 'code-intelligence', 'fallow', 'summary.json');

function fail(message: string): never {
  console.error(`Fallow policy assertion failed: ${message}`);
  process.exit(1);
}

function main(): void {
  const summary = readJson(SUMMARY_PATH) as unknown as CodeIntelligenceSummary;
  if (summary.version !== 'control-plane.code-intelligence/v1') {
    fail(`unexpected summary version: ${String(summary.version)}`);
  }
  if (summary.tool !== 'fallow') {
    fail(`unexpected tool: ${String(summary.tool)}`);
  }
  if (!summary.telemetry_disabled) {
    fail('telemetry must be disabled for Fallow analysis');
  }
  const verdict = computeVerdict(summary);
  const mode = process.env.FALLOW_GATE_MODE === 'enforce' ? 'enforce' : 'warn';
  if (verdict.blockingReasons.length > 0) {
    fail(`blocking reasons present: ${verdict.blockingReasons.join(', ')}`);
  }
  if (mode === 'enforce' && verdict.warnings.length > 0) {
    fail(`warnings are not allowed in enforce mode: ${verdict.warnings.join(', ')}`);
  }
  if (!summary.artifacts.includes('artifacts/code-intelligence/fallow/SUMMARY.md')) {
    fail('markdown summary artifact is missing from summary.artifacts');
  }
  console.log(
    `Fallow policy passed in ${mode} mode with verdict=${summary.verdict} warnings=${verdict.warnings.length}`,
  );
}

main();
