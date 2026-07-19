import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

type JsonObject = Record<string, unknown>;

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const APP_ROOT = path.resolve(SCRIPT_DIR, '..');
const REPO_ROOT = findRepoRoot(APP_ROOT);
const SNAPSHOT_FIXTURE_PATH = path.join(
  REPO_ROOT,
  'contracts',
  'operator_panel',
  'fixtures',
  'control_plane_snapshot_preview.json',
);
const REQUIRED_SOURCE_MARKERS = [
  ['Dashboard', 'src/components/control-plane/ControlPlaneDashboard.tsx', 'Pilot Launch Candidate'],
  ['Evidence corpus UI', 'src/components/control-plane/EvidencePackView.tsx', 'Evidence corpus'],
  ['Reports viewer', 'src/components/product-pages/ProductizedPages.tsx', 'Pilot launch report'],
  ['Install rehearsal button', 'src/App.tsx', 'runInstallRehearsal'],
  ['Security review button', 'src/App.tsx', 'generateSecurityReview'],
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

const failures: string[] = [];
if (!fs.existsSync(SNAPSHOT_FIXTURE_PATH)) {
  failures.push(`missing fixture: ${SNAPSHOT_FIXTURE_PATH}`);
} else {
  const snapshot = readJson(SNAPSHOT_FIXTURE_PATH);
  const pilotLaunch = asRecord(snapshot.pilotLaunch);
  const dataSource = asRecord(snapshot.dataSource);
  const adminProposals = asArray(pilotLaunch.adminProposals);
  if (pilotLaunch.schemaVersion !== 'control-plane.pilot-launch-readiness/v1') {
    failures.push('pilotLaunch schemaVersion mismatch');
  }
  if (pilotLaunch.status !== 'conditional') {
    failures.push('preview pilotLaunch must remain conditional');
  }
  if (dataSource.mode !== 'preview_fixture' || dataSource.isSilentFallback !== false) {
    failures.push('preview fixture runtime truth must remain explicit and fail-closed');
  }
  if (asRecord(pilotLaunch.evidenceCorpus).status !== 'ready') {
    failures.push('evidence corpus tile missing from preview snapshot');
  }
  if (adminProposals.length === 0) {
    failures.push('admin proposal summaries missing from preview snapshot');
  }
  if (asRecord(pilotLaunch.claimGuard).status === 'ready') {
    failures.push('preview claim guard tile must not present preview data as live ready evidence');
  }
}

for (const [name, relativePath, marker] of REQUIRED_SOURCE_MARKERS) {
  const sourcePath = path.join(APP_ROOT, relativePath);
  if (!fs.existsSync(sourcePath)) {
    failures.push(`${name}: missing ${relativePath}`);
    continue;
  }
  const source = fs.readFileSync(sourcePath, 'utf8');
  if (!source.includes(marker)) {
    failures.push(`${name}: missing marker ${marker}`);
  }
}

if (failures.length > 0) {
  console.error(['Pilot launch page assertion failed:', ...failures.map((item) => `- ${item}`)].join('\n'));
  process.exit(1);
}

console.log('Pilot launch page assertion passed.');
