import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';
import { boundaryBucket, findRepoRoot, readJson } from './fallow-policy.ts';

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const APP_ROOT = path.resolve(SCRIPT_DIR, '..');
const REPO_ROOT = findRepoRoot(APP_ROOT);
const BOUNDARY_PATH = path.join(
  REPO_ROOT,
  'artifacts',
  'code-intelligence',
  'fallow',
  'boundary-violations.json',
);

function fail(message: string): never {
  console.error(`Fallow boundary assertion failed: ${message}`);
  process.exit(1);
}

function main(): void {
  const bucket = boundaryBucket(readJson(BOUNDARY_PATH));
  const mode = process.env.BOUNDARY_GATE_MODE === 'warn' ? 'warn' : 'enforce';
  if (mode === 'enforce' && bucket.errors > 0) {
    fail(`${bucket.errors} architecture boundary violation(s) found`);
  }
  console.log(`Fallow boundary gate passed in ${mode} mode with ${bucket.total} violation(s).`);
}

main();
