import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';
import { frontendQaE2eBlockers, type SuiteStatus } from './frontend-qa-policy.ts';

type JsonObject = Record<string, unknown>;

type QaSummary = {
  generatedAtUtc: string;
  commit: string | null;
  packageVersion: string;
  controls: {
    total: number;
    tested: number;
    untested: number;
    working: number;
    disabledWithReason: number;
    removedUntilReady: number;
    deadControls: number;
    missingHandlers: number;
    noopHandlers: number;
    disabledWithoutReason: number;
    bridgeBound: number;
    bridgeMutations: number;
  };
  findings: {
    critical: number;
    high: number;
    medium: number;
    low: number;
  };
  testSuites: Record<string, SuiteStatus>;
  e2e: {
    status: SuiteStatus;
    totalTests: number | null;
    failedTests: number | null;
  };
  accessibility: {
    status: SuiteStatus;
    violations: number | null;
    criticalViolations: number | null;
    unnamedControls: number | null;
    keyboardFailures: number | null;
  };
  responsive: {
    status: SuiteStatus;
    viewportCount: number | null;
    maxHorizontalOverflowPx: number | null;
  };
  bridgeConfidence: {
    previewE2e: SuiteStatus;
    bridgeUnit: SuiteStatus;
    tauriBridgeSmoke: SuiteStatus;
    liveCliSmoke: SuiteStatus;
  };
  artifacts: {
    root: string;
    controlInventory: string;
    deadControls: string;
    e2eReport: string;
    accessibilityReport: string;
    responsiveReport: string;
    tauriBridgeSmoke: string;
    liveCliSmoke: string;
  };
  blockers: string[];
};

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const APP_ROOT = path.resolve(SCRIPT_DIR, '..');
const REPO_ROOT = findRepoRoot(APP_ROOT);
const OUTPUT_ROOT = path.join(REPO_ROOT, 'artifacts', 'operator-panel-ui');
const STATIC_PASSED = process.argv.includes('--static-passed');
const E2E_REQUIRED = process.argv.includes('--e2e-required');

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

function readJson(filePath: string): JsonObject | null {
  if (!fs.existsSync(filePath)) {
    return null;
  }
  try {
    return JSON.parse(fs.readFileSync(filePath, 'utf8')) as JsonObject;
  } catch {
    return null;
  }
}

function asRecord(value: unknown): JsonObject {
  return typeof value === 'object' && value !== null ? (value as JsonObject) : {};
}

function readNumber(source: JsonObject | null | undefined, key: string): number | null {
  if (!source) {
    return null;
  }
  const value = source[key];
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function readString(source: JsonObject | null | undefined, key: string): string | null {
  if (!source) {
    return null;
  }
  const value = source[key];
  return typeof value === 'string' ? value : null;
}

function readGitHead(): string | null {
  const headPath = path.join(REPO_ROOT, '.git', 'HEAD');
  if (!fs.existsSync(headPath)) {
    return null;
  }
  const head = fs.readFileSync(headPath, 'utf8').trim();
  if (!head.startsWith('ref:')) {
    return head;
  }
  const ref = head.slice('ref:'.length).trim();
  const refPath = path.join(REPO_ROOT, '.git', ref);
  return fs.existsSync(refPath) ? fs.readFileSync(refPath, 'utf8').trim() : null;
}

function readPackageVersion(): string {
  const packageJson = readJson(path.join(APP_ROOT, 'package.json'));
  return readString(packageJson, 'version') ?? 'unknown';
}

function collectPlaywrightStats(results: JsonObject | null): { totalTests: number | null; failedTests: number | null } {
  if (!results) {
    return { totalTests: null, failedTests: null };
  }

  let totalTests = 0;
  let failedTests = 0;

  function visitSuite(suite: JsonObject): void {
    const specs = Array.isArray(suite.specs) ? suite.specs : [];
    for (const spec of specs) {
      const specRecord = asRecord(spec);
      const tests = Array.isArray(specRecord.tests) ? specRecord.tests : [];
      for (const test of tests) {
        totalTests += 1;
        const testRecord = asRecord(test);
        const status = readString(testRecord, 'status');
        const expectedStatus = readString(testRecord, 'expectedStatus');
        if (status !== 'expected' || expectedStatus === 'failed') {
          failedTests += 1;
        }
      }
    }

    const childSuites = Array.isArray(suite.suites) ? suite.suites : [];
    for (const child of childSuites) {
      visitSuite(asRecord(child));
    }
  }

  for (const suite of Array.isArray(results.suites) ? results.suites : []) {
    visitSuite(asRecord(suite));
  }

  return { totalTests, failedTests };
}

function collectResponsiveMaxOverflow(responsiveReport: JsonObject | null): { viewportCount: number | null; maxOverflow: number | null } {
  if (!responsiveReport || !Array.isArray(responsiveReport.rows)) {
    return { viewportCount: null, maxOverflow: null };
  }
  const overflows = responsiveReport.rows
    .map((row) => readNumber(asRecord(row), 'overflowX'))
    .filter((value): value is number => value !== null);
  return {
    viewportCount: responsiveReport.rows.length,
    maxOverflow: overflows.length > 0 ? Math.max(...overflows) : null,
  };
}

function relativeArtifact(filePath: string): string {
  return path.relative(REPO_ROOT, filePath);
}

function readSmokeStatus(filePath: string): SuiteStatus {
  const payload = readJson(filePath);
  const status = readString(payload, 'status');
  if (status === 'passed') {
    return 'passed';
  }
  if (status === 'failed') {
    return 'failed';
  }
  return 'skipped';
}

function buildSummary(): QaSummary {
  fs.mkdirSync(OUTPUT_ROOT, { recursive: true });

  const inventoryPath = path.join(OUTPUT_ROOT, 'control-inventory.json');
  const deadControlsPath = path.join(OUTPUT_ROOT, 'dead-controls.md');
  const e2eLastRunPath = path.join(OUTPUT_ROOT, 'e2e-results', '.last-run.json');
  const e2eResultsPath = path.join(OUTPUT_ROOT, 'e2e-json', 'results.json');
  const e2eReportPath = path.join(OUTPUT_ROOT, 'e2e-report', 'index.html');
  const accessibilityPath = path.join(OUTPUT_ROOT, 'accessibility', 'accessibility-report.json');
  const accessibilityMarkdownPath = path.join(OUTPUT_ROOT, 'accessibility', 'accessibility-report.md');
  const responsivePath = path.join(OUTPUT_ROOT, 'responsive', 'responsive-report.json');
  const responsiveMarkdownPath = path.join(OUTPUT_ROOT, 'responsive', 'responsive-report.md');
  const tauriBridgeSmokePath = path.join(OUTPUT_ROOT, 'tauri-bridge-smoke.json');
  const liveCliSmokePath = path.join(OUTPUT_ROOT, 'live-cli-smoke.json');

  const inventory = readJson(inventoryPath);
  const e2eLastRun = readJson(e2eLastRunPath);
  const e2eResults = readJson(e2eResultsPath);
  const accessibility = readJson(accessibilityPath);
  const responsive = readJson(responsivePath);
  const accessibilityCounts = asRecord(accessibility?.counts);
  const playwrightStats = collectPlaywrightStats(e2eResults);
  const responsiveStats = collectResponsiveMaxOverflow(responsive);
  const inventoryControls = Array.isArray(inventory?.controls) ? inventory.controls.map((control) => asRecord(control)) : [];

  const criticalFindings = readNumber(inventory, 'criticalFindings') ?? 0;
  const highFindings = readNumber(inventory, 'highFindings') ?? 0;
  const criticalViolations = readNumber(accessibilityCounts, 'criticalViolations');
  const unnamedControls = readNumber(accessibilityCounts, 'unnamedControls');
  const keyboardFailures = readNumber(accessibilityCounts, 'keyboardFailures');
  const e2eStatus = readString(e2eLastRun, 'status');
  const e2eSuiteStatus: SuiteStatus = e2eStatus === 'passed' ? 'passed' : e2eStatus ? 'failed' : 'skipped';
  const tauriBridgeSmokeStatus = readSmokeStatus(tauriBridgeSmokePath);
  const liveCliSmokeStatus = readSmokeStatus(liveCliSmokePath);
  const accessibilityStatus: SuiteStatus =
    accessibility === null
      ? 'skipped'
      : criticalViolations === 0 && unnamedControls === 0 && keyboardFailures === 0
        ? 'passed'
        : 'failed';
  const responsiveStatus: SuiteStatus =
    responsive === null ? 'skipped' : (responsiveStats.maxOverflow ?? 0) <= 2 ? 'passed' : 'failed';

  const blockers = [
    ...(criticalFindings > 0 ? [`Critical UI control findings: ${criticalFindings}`] : []),
    ...(highFindings > 0 ? [`High UI control findings: ${highFindings}`] : []),
    ...frontendQaE2eBlockers(e2eSuiteStatus, E2E_REQUIRED),
    ...(tauriBridgeSmokeStatus === 'failed' ? ['Tauri bridge smoke failed'] : []),
    ...(liveCliSmokeStatus === 'failed' ? ['Live CLI smoke failed'] : []),
    ...(accessibilityStatus === 'failed' ? ['Accessibility smoke failed'] : []),
    ...(responsiveStatus === 'failed' ? ['Responsive smoke failed'] : []),
  ];

  return {
    generatedAtUtc: new Date().toISOString(),
    commit: readGitHead(),
    packageVersion: readPackageVersion(),
    controls: {
      total: readNumber(inventory, 'totalControls') ?? 0,
      tested: inventoryControls.filter((control) => readString(control, 'testCoverage') === 'covered').length,
      untested: inventoryControls.filter((control) => readString(control, 'testCoverage') === 'missing').length,
      working:
        readNumber(inventory, 'workingControls') ??
        inventoryControls.filter((control) => readString(control, 'status') === 'working').length,
      disabledWithReason:
        readNumber(inventory, 'disabledWithReasonControls') ??
        inventoryControls.filter((control) => readString(control, 'status') === 'disabled_with_reason').length,
      removedUntilReady:
        readNumber(inventory, 'removedUntilReadyControls') ??
        inventoryControls.filter((control) => readString(control, 'status') === 'removed_until_ready').length,
      deadControls: Array.isArray(inventory?.findings)
        ? inventory.findings
            .map((finding) => readString(asRecord(finding), 'rule'))
            .filter((rule) => rule === 'missing-handler' || rule === 'noop-handler').length
        : 0,
      missingHandlers: readNumber(inventory, 'missingHandlers') ?? 0,
      noopHandlers: readNumber(inventory, 'noopHandlers') ?? 0,
      disabledWithoutReason: readNumber(inventory, 'disabledWithoutReason') ?? 0,
      bridgeBound: inventoryControls.filter((control) => Boolean(readString(control, 'bridgeFunction'))).length,
      bridgeMutations: inventoryControls.filter((control) => readString(control, 'risk') === 'bridge_mutation').length,
    },
    findings: {
      critical: criticalFindings,
      high: highFindings,
      medium: readNumber(inventory, 'mediumFindings') ?? 0,
      low: readNumber(inventory, 'lowFindings') ?? 0,
    },
    testSuites: {
      audit: inventory ? 'passed' : 'skipped',
      unitInteraction: STATIC_PASSED ? 'passed' : 'skipped',
      lint: STATIC_PASSED ? 'passed' : 'skipped',
      build: STATIC_PASSED ? 'passed' : 'skipped',
      e2e: e2eSuiteStatus,
      accessibility: accessibilityStatus,
      responsive: responsiveStatus,
    },
    e2e: {
      status: e2eSuiteStatus,
      totalTests: playwrightStats.totalTests,
      failedTests: playwrightStats.failedTests,
    },
    accessibility: {
      status: accessibilityStatus,
      violations: readNumber(accessibilityCounts, 'violations'),
      criticalViolations,
      unnamedControls,
      keyboardFailures,
    },
    responsive: {
      status: responsiveStatus,
      viewportCount: responsiveStats.viewportCount,
      maxHorizontalOverflowPx: responsiveStats.maxOverflow,
    },
    bridgeConfidence: {
      previewE2e: e2eSuiteStatus,
      bridgeUnit: STATIC_PASSED ? 'passed' : 'skipped',
      tauriBridgeSmoke: tauriBridgeSmokeStatus,
      liveCliSmoke: liveCliSmokeStatus,
    },
    artifacts: {
      root: relativeArtifact(OUTPUT_ROOT),
      controlInventory: relativeArtifact(inventoryPath),
      deadControls: relativeArtifact(deadControlsPath),
      e2eReport: relativeArtifact(e2eReportPath),
      accessibilityReport: relativeArtifact(accessibilityMarkdownPath),
      responsiveReport: relativeArtifact(responsiveMarkdownPath),
      tauriBridgeSmoke: relativeArtifact(tauriBridgeSmokePath),
      liveCliSmoke: relativeArtifact(liveCliSmokePath),
    },
    blockers,
  };
}

function writeSummary(summary: QaSummary): void {
  fs.writeFileSync(path.join(OUTPUT_ROOT, 'qa-summary.json'), `${JSON.stringify(summary, null, 2)}\n`);

  const markdown = [
    '# Operator Panel Frontend QA Summary',
    '',
    `Generated: ${summary.generatedAtUtc}`,
    `Commit: ${summary.commit ?? 'unknown'}`,
    `Package version: ${summary.packageVersion}`,
    '',
    '## Gate Status',
    '',
    '| Gate | Status |',
    '|---|---|',
    ...Object.entries(summary.testSuites).map(([suite, status]) => `| ${suite} | ${status} |`),
    '',
    '## Findings',
    '',
    `- Critical UI findings: ${summary.findings.critical}`,
    `- High UI findings: ${summary.findings.high}`,
    `- Medium UI findings: ${summary.findings.medium}`,
    `- Low UI findings: ${summary.findings.low}`,
    `- Total controls: ${summary.controls.total}`,
    `- Working controls: ${summary.controls.working}`,
    `- Disabled with reason: ${summary.controls.disabledWithReason}`,
    `- Removed until ready: ${summary.controls.removedUntilReady}`,
    `- Controls with test coverage evidence: ${summary.controls.tested}`,
    `- Controls missing test coverage evidence: ${summary.controls.untested}`,
    `- Dead controls: ${summary.controls.deadControls}`,
    `- Missing handlers: ${summary.controls.missingHandlers}`,
    `- Disabled without explicit reason: ${summary.controls.disabledWithoutReason}`,
    '',
    '## Browser QA',
    '',
    `- E2E status: ${summary.e2e.status}${summary.e2e.totalTests !== null ? ` (${summary.e2e.totalTests} tests)` : ''}`,
    `- Accessibility: ${summary.accessibility.status}; critical violations ${summary.accessibility.criticalViolations ?? 'n/a'}, unnamed controls ${summary.accessibility.unnamedControls ?? 'n/a'}`,
    `- Responsive: ${summary.responsive.status}; max horizontal overflow ${summary.responsive.maxHorizontalOverflowPx ?? 'n/a'}px`,
    '',
    '## Bridge Confidence',
    '',
    `- Preview E2E: ${summary.bridgeConfidence.previewE2e}`,
    `- Bridge unit: ${summary.bridgeConfidence.bridgeUnit}`,
    `- Tauri bridge smoke: ${summary.bridgeConfidence.tauriBridgeSmoke}`,
    `- Live CLI smoke: ${summary.bridgeConfidence.liveCliSmoke}`,
    '',
    '## Artifacts',
    '',
    `- Control inventory: ${summary.artifacts.controlInventory}`,
    `- Dead controls: ${summary.artifacts.deadControls}`,
    `- Playwright report: ${summary.artifacts.e2eReport}`,
    `- Accessibility report: ${summary.artifacts.accessibilityReport}`,
    `- Responsive report: ${summary.artifacts.responsiveReport}`,
    `- Tauri bridge smoke: ${summary.artifacts.tauriBridgeSmoke}`,
    `- Live CLI smoke: ${summary.artifacts.liveCliSmoke}`,
    '',
    '## Blockers',
    '',
    summary.blockers.length > 0 ? summary.blockers.map((blocker) => `- ${blocker}`).join('\n') : 'No gate blockers.',
    '',
  ];

  fs.writeFileSync(path.join(OUTPUT_ROOT, 'qa-summary.md'), `${markdown.join('\n')}\n`);
}

function main(): void {
  const summary = buildSummary();
  writeSummary(summary);
  console.log(
    `Frontend QA summary: ${summary.blockers.length} blocker(s), E2E ${summary.e2e.status}, accessibility ${summary.accessibility.status}, responsive ${summary.responsive.status}`,
  );

  if (summary.blockers.length > 0) {
    process.exitCode = 1;
  }
}

main();
