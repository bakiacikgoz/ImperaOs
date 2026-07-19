import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';
import ts from 'typescript';

type UiControlKind =
  | 'button'
  | 'link'
  | 'tab'
  | 'input'
  | 'select'
  | 'checkbox'
  | 'textarea'
  | 'menu-item'
  | 'quick-action';

type UiControlRisk =
  | 'read_only'
  | 'state_change'
  | 'bridge_read'
  | 'bridge_mutation'
  | 'destructive_or_sensitive'
  | 'debug_or_raw_payload';

type UiControlStatus =
  | 'working'
  | 'disabled_with_reason'
  | 'removed_until_ready'
  | 'missing_handler'
  | 'noop_handler'
  | 'unknown_handler'
  | 'needs_manual_review';

type FindingSeverity = 'Critical' | 'High' | 'Medium' | 'Low';
type TestCoverageStatus = 'covered' | 'missing' | 'not_required';
type UiPage =
  | 'Mission Control'
  | 'AI Assistant'
  | 'Tasks'
  | 'Approvals'
  | 'Runs'
  | 'System'
  | 'Operations'
  | 'Settings'
  | 'Shared';

type UiControlInventoryItem = {
  id: string;
  file: string;
  line: number;
  component: string;
  kind: UiControlKind;
  accessibleName: string;
  visibleText: string;
  handlerName: string | null;
  disabledExpression: string | null;
  disabledReasonExpression: string | null;
  bridgeFunction: string | null;
  effectEvidence: string[];
  page: UiPage;
  risk: UiControlRisk;
  status: UiControlStatus;
  requiresTest: boolean;
  testCoverage: TestCoverageStatus;
  testCoverageEvidence: string[];
  notes: string[];
};

type UiControlFinding = {
  severity: FindingSeverity;
  rule: string;
  controlId: string;
  file: string;
  line: number;
  message: string;
};

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const APP_ROOT = path.resolve(SCRIPT_DIR, '..');
const REPO_ROOT = findRepoRoot(APP_ROOT);
const SRC_ROOT = path.join(APP_ROOT, 'src');
const E2E_ROOT = path.join(APP_ROOT, 'e2e');
const OUTPUT_ROOT = resolveOutputRoot();
const BRIDGE_FILE = path.join(SRC_ROOT, 'bridge.ts');
const PRODUCT_PAGES: Exclude<UiPage, 'Shared'>[] = [
  'Mission Control',
  'AI Assistant',
  'Tasks',
  'Approvals',
  'Runs',
  'System',
  'Operations',
  'Settings',
];
const PAGE_E2E_TESTS: Record<Exclude<UiPage, 'Shared'>, string[]> = {
  'Mission Control': ['e2e/workspace.spec.ts'],
  'AI Assistant': ['e2e/assistant.spec.ts'],
  Tasks: ['e2e/tasks.spec.ts'],
  Approvals: ['e2e/approvals.spec.ts'],
  Runs: ['e2e/runs.spec.ts'],
  System: ['e2e/system.spec.ts'],
  Operations: ['e2e/operations.spec.ts'],
  Settings: ['e2e/settings.spec.ts'],
};
const PAGE_NAV_KEYS: Record<string, Exclude<UiPage, 'Shared'>> = {
  workspace: 'Mission Control',
  assistant: 'AI Assistant',
  tasks: 'Tasks',
  approvals: 'Approvals',
  runs: 'Runs',
  system: 'System',
  operations: 'Operations',
  settings: 'Settings',
};

const INTERACTIVE_TAGS = new Set(['button', 'a', 'input', 'select', 'textarea', 'Button']);
const BRIDGE_MUTATION_PREFIXES = [
  'decide',
  'execute',
  'submit',
  'resume',
  'pause',
  'stop',
  'export',
  'create',
  'verify',
  'plan',
  'dryRun',
  'run',
  'rotate',
];
const BRIDGE_READ_PREFIXES = ['fetch', 'get', 'list', 'resolve', 'check', 'snapshot', 'handshake', 'read', 'tail'];
const DESTRUCTIVE_TOKENS = [
  'approve',
  'approval',
  'reject',
  'execute',
  'cancel',
  'delete',
  'remove',
  'stop',
  'start',
  'resume',
  'pause',
  'export',
  'backup',
  'restore',
  'migration',
  'migrate',
  'rotate',
  'key',
  'support',
  'qualification',
  'computer-use',
  'computer use',
  'onay',
  'reddet',
  'iptal',
  'durdur',
  'baslat',
  'calistir',
  'yurut',
  'yedek',
  'geri yukle',
  'disari aktar',
];
const RAW_DEBUG_TOKENS = ['raw', 'debug', 'json', 'payload', 'stderr', 'secret', 'token'];

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

function resolveOutputRoot(): string {
  const preferred = path.join(REPO_ROOT, 'artifacts', 'operator-panel-ui');
  const fallback = path.join(APP_ROOT, 'artifacts', 'operator-panel-ui');
  return canWriteDirectory(preferred) ? preferred : fallback;
}

function canWriteDirectory(directory: string): boolean {
  try {
    fs.mkdirSync(directory, { recursive: true });
    const probe = path.join(directory, '.write-test');
    fs.writeFileSync(probe, '');
    fs.unlinkSync(probe);
    return true;
  } catch {
    return false;
  }
}

function walkFiles(root: string): string[] {
  const entries = fs.readdirSync(root, { withFileTypes: true });
  return entries.flatMap((entry) => {
    const fullPath = path.join(root, entry.name);
    if (entry.isDirectory()) {
      return walkFiles(fullPath);
    }
    if (!entry.name.endsWith('.tsx')) {
      return [];
    }
    if (fullPath.includes(`${path.sep}components${path.sep}primitives${path.sep}`)) {
      return [];
    }
    // This is the typed button primitive itself, not a product-surface control.
    if (fullPath.endsWith(`${path.sep}artifact-workspace${path.sep}ui${path.sep}ArtifactPrimitives.tsx`)) {
      return [];
    }
    if (entry.name.includes('.test.') || entry.name.includes('.interaction.') || entry.name.includes('.integration.')) {
      return [];
    }
    return [fullPath];
  });
}

function readBridgeFunctionNames(): string[] {
  if (!fs.existsSync(BRIDGE_FILE)) {
    return [];
  }
  const source = fs.readFileSync(BRIDGE_FILE, 'utf8');
  return Array.from(source.matchAll(/export\s+async\s+function\s+([A-Za-z0-9_]+)/g)).map((match) => match[1]);
}

function attributeMap(node: ts.JsxOpeningLikeElement, source: ts.SourceFile): Map<string, string | true> {
  const attrs = new Map<string, string | true>();
  for (const attr of node.attributes.properties) {
    if (ts.isJsxSpreadAttribute(attr)) {
      attrs.set('...spread', attr.expression.getText(source));
      continue;
    }
    const name = attr.name.getText(source);
    if (!attr.initializer) {
      attrs.set(name, true);
      continue;
    }
    if (ts.isStringLiteral(attr.initializer)) {
      attrs.set(name, attr.initializer.text);
      continue;
    }
    if (ts.isJsxExpression(attr.initializer)) {
      attrs.set(name, attr.initializer.expression?.getText(source) ?? '');
      continue;
    }
    attrs.set(name, attr.initializer.getText(source));
  }
  return attrs;
}

function attr(attrs: Map<string, string | true>, name: string): string | null {
  const value = attrs.get(name);
  if (value === undefined) {
    return null;
  }
  return value === true ? 'true' : value;
}

function expressionLabelText(expression: ts.Expression, source: ts.SourceFile): string {
  if (ts.isStringLiteral(expression) || ts.isNoSubstitutionTemplateLiteral(expression)) {
    return expression.text;
  }
  const text = expression.getText(source).replace(/\s+/g, ' ').trim();
  if (!text || text.length > 80) {
    return '';
  }
  if (/^[A-Za-z0-9_.$]+$/.test(text)) {
    return text.replace(/^t\./, '').replace(/^copy\./, '');
  }
  return '';
}

function collectText(node: ts.Node, source: ts.SourceFile): string {
  const parts: string[] = [];
  function visitText(child: ts.Node): void {
    if (ts.isJsxText(child)) {
      const text = child.getText().replace(/\s+/g, ' ').trim();
      if (text) {
        parts.push(text);
      }
      return;
    }
    if (ts.isStringLiteral(child) || ts.isNoSubstitutionTemplateLiteral(child)) {
      parts.push(child.text);
      return;
    }
    if (ts.isJsxExpression(child) && child.expression) {
      const label = expressionLabelText(child.expression, source);
      if (label) {
        parts.push(label);
      }
      return;
    }
    child.forEachChild(visitText);
  }
  node.forEachChild(visitText);
  return parts.join(' ').replace(/\s+/g, ' ').trim();
}

function enclosingLabelText(node: ts.Node, source: ts.SourceFile): string {
  let current = node.parent;
  while (current && !ts.isSourceFile(current)) {
    if (
      ts.isJsxElement(current) &&
      current.openingElement.tagName.getText(source) === 'label'
    ) {
      return collectText(current, source);
    }
    current = current.parent;
  }
  return '';
}

function getTagName(node: ts.JsxOpeningLikeElement, source: ts.SourceFile): string {
  return node.tagName.getText(source);
}

function isControl(node: ts.JsxOpeningLikeElement, source: ts.SourceFile, attrs: Map<string, string | true>): boolean {
  const tag = getTagName(node, source);
  if (INTERACTIVE_TAGS.has(tag)) {
    return true;
  }
  const role = attr(attrs, 'role');
  return role === 'tab' || role === 'menuitem' || tag.endsWith('Button');
}

function getKind(node: ts.JsxOpeningLikeElement, source: ts.SourceFile, attrs: Map<string, string | true>): UiControlKind {
  const tag = getTagName(node, source);
  const role = attr(attrs, 'role');
  const className = attr(attrs, 'className') ?? '';
  if (role === 'tab' || className.toLowerCase().includes('tab')) {
    return 'tab';
  }
  if (role === 'menuitem') {
    return 'menu-item';
  }
  if (tag === 'a') {
    return 'link';
  }
  if (tag === 'select') {
    return 'select';
  }
  if (tag === 'textarea') {
    return 'textarea';
  }
  if (tag === 'input') {
    return attr(attrs, 'type') === 'checkbox' ? 'checkbox' : 'input';
  }
  if (className.toLowerCase().includes('quick')) {
    return 'quick-action';
  }
  return 'button';
}

function findHandler(kind: UiControlKind, attrs: Map<string, string | true>): string | null {
  const candidates =
    kind === 'input' || kind === 'select' || kind === 'checkbox' || kind === 'textarea'
      ? ['onChange', 'onInput', 'onClick']
      : ['onClick', 'onSubmit', 'onChange', 'onPointerDown', 'onPointerUp'];
  for (const name of candidates) {
    const value = attr(attrs, name);
    if (value) {
      return value;
    }
  }
  if (kind === 'link' && attr(attrs, 'href')) {
    return `href:${attr(attrs, 'href')}`;
  }
  return null;
}

function isNoop(handler: string | null): boolean {
  if (!handler) {
    return false;
  }
  const normalized = handler.replace(/\s+/g, '');
  return (
    normalized === 'noop' ||
    normalized === '()=>undefined' ||
    normalized === '()=>{}' ||
    normalized === 'function(){}' ||
    normalized === 'functionnoop(){}'
  );
}

function nearestAccessibleName(
  attrs: Map<string, string | true>,
  visibleText: string,
  kind: UiControlKind,
): string {
  return (
    attr(attrs, 'aria-label') ??
    attr(attrs, 'title') ??
    visibleText ??
    attr(attrs, 'placeholder') ??
    attr(attrs, 'name') ??
    (kind === 'checkbox' ? attr(attrs, 'value') : null) ??
    ''
  );
}

function inferBridgeFunction(sourceText: string, bridgeFunctions: string[]): string | null {
  const normalized = sourceText.toLowerCase();
  const matched = bridgeFunctions.find((name) => normalized.includes(name.toLowerCase()));
  return matched ?? null;
}

function collectLocalFunctionBodies(source: ts.SourceFile): Map<string, string> {
  const functions = new Map<string, string>();

  function visit(node: ts.Node): void {
    if (ts.isFunctionDeclaration(node) && node.name && node.body) {
      functions.set(node.name.text, node.body.getText(source));
    }
    if (
      ts.isVariableDeclaration(node) &&
      ts.isIdentifier(node.name) &&
      node.initializer &&
      (ts.isArrowFunction(node.initializer) || ts.isFunctionExpression(node.initializer))
    ) {
      functions.set(node.name.text, node.initializer.getText(source));
    }
    node.forEachChild(visit);
  }

  visit(source);
  return functions;
}

function referencedFunctionNames(handler: string | null): string[] {
  if (!handler) {
    return [];
  }
  const names = new Set<string>();
  for (const match of handler.matchAll(/\b([A-Za-z_$][A-Za-z0-9_$]*)\s*\(/g)) {
    names.add(match[1]);
  }
  if (/^[A-Za-z_$][A-Za-z0-9_$]*$/.test(handler.trim())) {
    names.add(handler.trim());
  }
  return Array.from(names);
}

function resolveHandlerSource(handler: string | null, localFunctionBodies: Map<string, string>): string {
  if (!handler) {
    return '';
  }
  const parts = [handler];
  for (const name of referencedFunctionNames(handler)) {
    const body = localFunctionBodies.get(name);
    if (body) {
      parts.push(body);
    }
  }
  return parts.join('\n');
}

function inferEffectEvidence(
  handlerName: string | null,
  kind: UiControlKind,
  attrs: Map<string, string | true>,
  handlerSource: string,
  bridgeFunction: string | null,
): string[] {
  const evidence: string[] = [];
  const source = handlerSource;
  if (attr(attrs, 'type') === 'submit') {
    evidence.push('form-submit');
  }
  if (kind === 'link' && attr(attrs, 'href')) {
    evidence.push('href-navigation');
  }
  if (bridgeFunction) {
    evidence.push(`bridge:${bridgeFunction}`);
  }
  if (/\bset[A-Z][A-Za-z0-9_]*\b|\b(update|persist|select|undo|redo|addSheet|renameSheet|pasteSelection|moveSelected)\b|\bupdateSettings\b|\bsaveSettings\b/.test(source)) {
    evidence.push('state-update');
  }
  if (/\bpushToast\b|\bset[A-Za-z0-9_]*Error\b|\bset[A-Za-z0-9_]*Warning\b/.test(source)) {
    evidence.push('feedback');
  }
  if (/\bwindow\.(confirm|prompt)\b|\bconfirmRawDisclosure\b/.test(source)) {
    evidence.push('operator-confirmation');
  }
  if (/\bnavigator\.clipboard\b/.test(source)) {
    evidence.push('clipboard-write');
  }
  if (/\bscroll(To|IntoView)[A-Za-z0-9_]*\b|\bscrollTop\b/.test(source)) {
    evidence.push('scroll-position');
  }
  if (/^on[A-Z]/.test(handlerName ?? '') || /\bon[A-Z][A-Za-z0-9_]*\b/.test(source)) {
    evidence.push('required-callback-prop');
  }
  return Array.from(new Set(evidence));
}

function inferredDisabledReason(disabledExpression: string | null): string | null {
  // Every artifact editor exposes an adjacent read-only state. Treat that
  // canonical mode guard as a reason even when the native control has no
  // redundant tooltip.
  return disabledExpression && /!\s*(?:props\.)?editable\b|\breadOnly\b|\bisReadOnly\b/.test(disabledExpression)
    ? 'canonical-read-only-state'
    : null;
}

function inferRisk(itemText: string, bridgeFunction: string | null, hasHandler: boolean): UiControlRisk {
  const normalized = itemText.toLowerCase();
  if (RAW_DEBUG_TOKENS.some((token) => normalized.includes(token))) {
    return 'debug_or_raw_payload';
  }
  if (DESTRUCTIVE_TOKENS.some((token) => normalized.includes(token))) {
    return 'destructive_or_sensitive';
  }
  if (bridgeFunction) {
    if (BRIDGE_MUTATION_PREFIXES.some((prefix) => bridgeFunction.startsWith(prefix))) {
      return 'bridge_mutation';
    }
    if (BRIDGE_READ_PREFIXES.some((prefix) => bridgeFunction.startsWith(prefix))) {
      return 'bridge_read';
    }
  }
  return hasHandler ? 'state_change' : 'read_only';
}

function statusFor(
  kind: UiControlKind,
  handlerName: string | null,
  disabledExpression: string | null,
  disabledReasonExpression: string | null,
  effectEvidence: string[],
  hasSpread: boolean,
  attrs: Map<string, string | true>,
): UiControlStatus {
  if (isNoop(handlerName)) {
    return 'noop_handler';
  }
  if (disabledExpression && disabledReasonExpression) {
    return 'disabled_with_reason';
  }
  if (disabledExpression) {
    return 'needs_manual_review';
  }
  if (attr(attrs, 'type') === 'submit') {
    return 'working';
  }
  if (handlerName) {
    return effectEvidence.length > 0 ? 'working' : 'needs_manual_review';
  }
  if (hasSpread) {
    return 'unknown_handler';
  }
  if (kind === 'link' && attr(attrs, 'href')) {
    return 'working';
  }
  if (kind === 'input' || kind === 'select' || kind === 'checkbox' || kind === 'textarea') {
    return attr(attrs, 'readOnly') || attr(attrs, 'disabled') ? 'disabled_with_reason' : 'missing_handler';
  }
  return 'missing_handler';
}

function shouldRequireTest(risk: UiControlRisk, status: UiControlStatus): boolean {
  return (
    status === 'working' ||
    status === 'disabled_with_reason' ||
    risk === 'bridge_mutation' ||
    risk === 'destructive_or_sensitive' ||
    risk === 'debug_or_raw_payload' ||
    status === 'missing_handler' ||
    status === 'noop_handler' ||
    status === 'unknown_handler'
  );
}

type PageRange = {
  page: Exclude<UiPage, 'Shared'>;
  startLine: number;
  endLine: number;
};

function buildAppPageRanges(source: ts.SourceFile): PageRange[] {
  const ranges: Array<Omit<PageRange, 'endLine'>> = [];
  const sourceText = source.getFullText();
  for (const match of sourceText.matchAll(/activeView\s*===\s*'([^']+)'/g)) {
    const page = PAGE_NAV_KEYS[match[1]];
    if (!page || match.index === undefined) {
      continue;
    }
    ranges.push({
      page,
      startLine: source.getLineAndCharacterOfPosition(match.index).line + 1,
    });
  }
  return ranges.map((range, index) => ({
    ...range,
    endLine: (ranges[index + 1]?.startLine ?? Number.MAX_SAFE_INTEGER) - 1,
  }));
}

function inferPage(relativeFile: string, line: number, component: string, appPageRanges: PageRange[]): UiPage {
  if (relativeFile.endsWith('App.tsx')) {
    const matched = appPageRanges.find((range) => line >= range.startLine && line <= range.endLine);
    return matched?.page ?? 'Shared';
  }
  if (relativeFile.includes('/components/assistant/')) {
    return 'AI Assistant';
  }
  if (relativeFile.includes('/components/mission/')) {
    return 'Mission Control';
  }
  if (component.includes('Settings')) {
    return 'Settings';
  }
  return 'Shared';
}

function testFiles(root: string): string[] {
  if (!fs.existsSync(root)) {
    return [];
  }
  const entries = fs.readdirSync(root, { withFileTypes: true });
  return entries.flatMap((entry) => {
    const fullPath = path.join(root, entry.name);
    if (entry.isDirectory()) {
      return testFiles(fullPath);
    }
    if (
      entry.name.endsWith('.test.tsx') ||
      entry.name.endsWith('.test.ts') ||
      entry.name.endsWith('.interaction.test.tsx') ||
      entry.name.endsWith('.integration.test.tsx') ||
      entry.name.endsWith('.spec.ts')
    ) {
      return [fullPath];
    }
    return [];
  });
}

function readTestIndex(): Map<string, string> {
  const index = new Map<string, string>();
  for (const filePath of [...testFiles(SRC_ROOT), ...testFiles(E2E_ROOT)]) {
    const relativeTestPath = path.relative(APP_ROOT, filePath).split(path.sep).join('/');
    index.set(relativeTestPath, fs.readFileSync(filePath, 'utf8'));
  }
  return index;
}

function hasComponentCoverage(relativeFile: string, component: string, testIndex: Map<string, string>): string | null {
  const sourceBase = path.basename(relativeFile, '.tsx');
  const candidateNames = new Set([sourceBase, component].filter(Boolean));
  for (const testPath of testIndex.keys()) {
    for (const candidate of candidateNames) {
      if (
        testPath.endsWith(`${candidate}.test.tsx`) ||
        testPath.endsWith(`${candidate}.interaction.test.tsx`) ||
        testPath.endsWith(`${candidate}.integration.test.tsx`)
      ) {
        return testPath;
      }
    }
  }
  return null;
}

function hasPageCoverage(page: UiPage, testIndex: Map<string, string>): string | null {
  if (page === 'Shared') {
    return null;
  }
  const candidates = PAGE_E2E_TESTS[page];
  return candidates.find((candidate) => testIndex.has(candidate)) ?? null;
}

function hasNameCoverage(accessibleName: string, testIndex: Map<string, string>): string | null {
  const name = accessibleName.trim();
  if (!name || name.includes('.') || name.length < 3) {
    return null;
  }
  for (const [testPath, text] of testIndex) {
    if (text.includes(name)) {
      return testPath;
    }
  }
  return null;
}

function inferTestCoverage(
  control: Pick<UiControlInventoryItem, 'file' | 'component' | 'page' | 'accessibleName' | 'requiresTest'>,
  testIndex: Map<string, string>,
): { status: TestCoverageStatus; evidence: string[] } {
  if (!control.requiresTest) {
    return { status: 'not_required', evidence: [] };
  }
  const evidence = [
    hasComponentCoverage(control.file, control.component, testIndex),
    hasPageCoverage(control.page, testIndex),
    hasNameCoverage(control.accessibleName, testIndex),
  ].filter((item): item is string => Boolean(item));
  return {
    status: evidence.length > 0 ? 'covered' : 'missing',
    evidence: Array.from(new Set(evidence)),
  };
}

function auditFile(
  filePath: string,
  bridgeFunctions: string[],
  testIndex: Map<string, string>,
): UiControlInventoryItem[] {
  const sourceText = fs.readFileSync(filePath, 'utf8');
  const source = ts.createSourceFile(filePath, sourceText, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const localFunctionBodies = collectLocalFunctionBodies(source);
  const appPageRanges = buildAppPageRanges(source);
  const controls: UiControlInventoryItem[] = [];
  const relativeFile = path.relative(REPO_ROOT, filePath).split(path.sep).join('/');

  function visit(node: ts.Node, component: string): void {
    let nextComponent = component;
    if (ts.isFunctionDeclaration(node) && node.name && /^[A-Z]/.test(node.name.text)) {
      nextComponent = node.name.text;
    }
    if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name) && /^[A-Z]/.test(node.name.text)) {
      nextComponent = node.name.text;
    }

    if (ts.isJsxOpeningElement(node) || ts.isJsxSelfClosingElement(node)) {
      const attrs = attributeMap(node, source);
      if (isControl(node, source, attrs)) {
        const kind = getKind(node, source, attrs);
        const parent = ts.isJsxOpeningElement(node) ? node.parent : node;
        const visibleText = collectText(parent, source) || enclosingLabelText(node, source);
        const handlerName = findHandler(kind, attrs);
        const disabledExpression = attr(attrs, 'disabled') ?? attr(attrs, 'aria-disabled');
        const disabledReasonExpression =
          attr(attrs, 'title') ?? attr(attrs, 'aria-describedby') ?? attr(attrs, 'data-disabled-reason') ?? inferredDisabledReason(disabledExpression);
        const line = source.getLineAndCharacterOfPosition(node.getStart(source)).line + 1;
        const handlerSource = resolveHandlerSource(handlerName, localFunctionBodies);
        const fullControlText = `${visibleText} ${handlerName ?? ''} ${handlerSource} ${node.getText(source)}`;
        const bridgeFunction = inferBridgeFunction(fullControlText, bridgeFunctions);
        const effectEvidence = inferEffectEvidence(handlerName, kind, attrs, handlerSource, bridgeFunction);
        const risk = inferRisk(fullControlText, bridgeFunction, Boolean(handlerName));
        const hasSpread = attrs.has('...spread');
        const status = statusFor(
          kind,
          handlerName,
          disabledExpression,
          disabledReasonExpression,
          effectEvidence,
          hasSpread,
          attrs,
        );
        const accessibleName = nearestAccessibleName(attrs, visibleText, kind);
        const page = inferPage(relativeFile, line, nextComponent || 'Unknown', appPageRanges);
        const requiresTest = shouldRequireTest(risk, status);
        const coverage = inferTestCoverage(
          {
            file: relativeFile,
            component: nextComponent || 'Unknown',
            page,
            accessibleName,
            requiresTest,
          },
          testIndex,
        );
        const notes: string[] = [];

        if (hasSpread) {
          notes.push('Props are spread into this control; handler requires manual review.');
        }
        if (disabledExpression && !disabledReasonExpression) {
          notes.push('Disabled expression is present without an explicit reason surface.');
        }
        if (!accessibleName) {
          notes.push('No accessible name inferred from aria-label, title, visible text, placeholder, or name.');
        }

        controls.push({
          id: `${relativeFile}:${line}:${controls.length + 1}`,
          file: relativeFile,
          line,
          component: nextComponent || 'Unknown',
          kind,
          accessibleName,
          visibleText,
          handlerName,
          disabledExpression,
          disabledReasonExpression,
          bridgeFunction,
          effectEvidence,
          page,
          risk,
          status,
          requiresTest,
          testCoverage: coverage.status,
          testCoverageEvidence: coverage.evidence,
          notes,
        });
      }
    }

    node.forEachChild((child) => visit(child, nextComponent));
  }

  visit(source, 'Unknown');
  return controls;
}

function buildFindings(controls: UiControlInventoryItem[]): UiControlFinding[] {
  const findings: UiControlFinding[] = [];
  for (const control of controls) {
    if (control.status === 'missing_handler' && ['button', 'tab', 'menu-item', 'quick-action'].includes(control.kind)) {
      findings.push({
        severity: 'High',
        rule: 'missing-handler',
        controlId: control.id,
        file: control.file,
        line: control.line,
        message: `${control.kind} has no explicit handler or spread props.`,
      });
    }
    if (control.status === 'noop_handler') {
      findings.push({
        severity: 'High',
        rule: 'noop-handler',
        controlId: control.id,
        file: control.file,
        line: control.line,
        message: `${control.kind} is wired to a no-op handler.`,
      });
    }
    if (control.status === 'needs_manual_review') {
      findings.push({
        severity: 'Medium',
        rule: 'unclear-control-effect',
        controlId: control.id,
        file: control.file,
        line: control.line,
        message: `${control.kind} is enabled or partially wired, but the audit cannot prove state, callback, feedback, navigation, or bridge effect.`,
      });
    }
    if (control.status === 'unknown_handler') {
      findings.push({
        severity: 'Medium',
        rule: 'unknown-handler',
        controlId: control.id,
        file: control.file,
        line: control.line,
        message: `${control.kind} uses spread props or an unresolved handler and needs explicit coverage.`,
      });
    }
    if (control.disabledExpression && !control.disabledReasonExpression) {
      findings.push({
        severity: 'Medium',
        rule: 'disabled-without-reason',
        controlId: control.id,
        file: control.file,
        line: control.line,
        message: `${control.kind} has disabled state without title, aria-describedby, or data-disabled-reason.`,
      });
    }
    if (!control.accessibleName) {
      findings.push({
        severity: 'Medium',
        rule: 'missing-accessible-name',
        controlId: control.id,
        file: control.file,
        line: control.line,
        message: `${control.kind} has no inferred accessible name.`,
      });
    }
    if (control.requiresTest && control.testCoverage === 'missing') {
      findings.push({
        severity: 'Medium',
        rule: 'missing-test-coverage',
        controlId: control.id,
        file: control.file,
        line: control.line,
        message: `${control.kind} has no component, page, or accessible-name test coverage evidence.`,
      });
    }
    if (control.risk === 'debug_or_raw_payload' && !/confirm|onConfirm|showRaw|debugRaw/i.test(control.handlerName ?? '')) {
      findings.push({
        severity: 'Low',
        rule: 'raw-debug-manual-review',
        controlId: control.id,
        file: control.file,
        line: control.line,
        message: `${control.kind} references raw/debug payload text and needs manual disclosure review.`,
      });
    }
  }
  return findings;
}

function findDefaultNoopCallbackFindings(files: string[]): UiControlFinding[] {
  const findings: UiControlFinding[] = [];
  const noopCallbackPattern = /\bon[A-Z][A-Za-z0-9_]*\s*=\s*\(\)\s*=>\s*(?:undefined|\{\})/g;

  for (const filePath of files) {
    const sourceText = fs.readFileSync(filePath, 'utf8');
    const source = ts.createSourceFile(filePath, sourceText, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
    const relativeFile = path.relative(REPO_ROOT, filePath);
    for (const match of sourceText.matchAll(noopCallbackPattern)) {
      if (match.index === undefined) {
        continue;
      }
      const line = source.getLineAndCharacterOfPosition(match.index).line + 1;
      findings.push({
        severity: 'High',
        rule: 'default-noop-callback',
        controlId: `${relativeFile}:${line}:default-noop-callback`,
        file: relativeFile,
        line,
        message: 'Component prop defaults to a no-op callback; production parents must wire critical actions explicitly.',
      });
    }
  }

  return findings;
}

function severityCount(findings: UiControlFinding[], severity: FindingSeverity): number {
  return findings.filter((finding) => finding.severity === severity).length;
}

function writeMarkdown(controls: UiControlInventoryItem[], findings: UiControlFinding[]): void {
  const highOrCritical = findings.filter((finding) => finding.severity === 'High' || finding.severity === 'Critical');
  const medium = findings.filter((finding) => finding.severity === 'Medium');
  const lines = [
    '# Operator Panel UI Control Audit',
    '',
    `Generated: ${new Date().toISOString()}`,
    `Total controls: ${controls.length}`,
    `Critical findings: ${severityCount(findings, 'Critical')}`,
    `High findings: ${severityCount(findings, 'High')}`,
    `Medium findings: ${severityCount(findings, 'Medium')}`,
    '',
    '## Gate Findings',
    '',
  ];

  if (highOrCritical.length === 0) {
    lines.push('No Critical or High dead-control findings.');
  } else {
    lines.push('| Severity | Rule | Location | Message |');
    lines.push('|---|---|---|---|');
    for (const finding of highOrCritical) {
      lines.push(
        `| ${finding.severity} | ${finding.rule} | ${finding.file}:${finding.line} | ${finding.message} |`,
      );
    }
  }

  lines.push('', '## Medium Findings', '');
  if (medium.length === 0) {
    lines.push('No Medium findings.');
  } else {
    lines.push('| Rule | Location | Message |');
    lines.push('|---|---|---|');
    for (const finding of medium) {
      lines.push(`| ${finding.rule} | ${finding.file}:${finding.line} | ${finding.message} |`);
    }
  }

  fs.writeFileSync(path.join(OUTPUT_ROOT, 'dead-controls.md'), `${lines.join('\n')}\n`);

  const inventoryLines = [
    '# Operator Panel UI Control Inventory',
    '',
    `Generated: ${new Date().toISOString()}`,
    '',
    '| Page | Kind | Status | Risk | Test | Location | Name | Handler | Effect |',
    '|---|---|---|---|---|---|---|---|---|',
    ...controls.map((control) =>
      [
        control.page,
        control.kind,
        control.status,
        control.risk,
        control.testCoverage,
        `${control.file}:${control.line}`,
        escapePipe(control.accessibleName || control.visibleText || '-'),
        escapePipe(control.handlerName ?? '-'),
        escapePipe(control.effectEvidence.join(', ') || '-'),
      ].join(' | '),
    ),
  ];
  fs.writeFileSync(path.join(OUTPUT_ROOT, 'control-inventory.md'), `${inventoryLines.join('\n')}\n`);
}

function writeQaSummary(controls: UiControlInventoryItem[], findings: UiControlFinding[]): void {
  const summary = {
    generatedAtUtc: new Date().toISOString(),
    commit: readGitHead(),
    packageVersion: readPackageVersion(),
    totalControls: controls.length,
    workingControls: controls.filter((control) => control.status === 'working').length,
    disabledWithReasonControls: controls.filter((control) => control.status === 'disabled_with_reason').length,
    removedUntilReadyControls: controls.filter((control) => control.status === 'removed_until_ready').length,
    testedControls: controls.filter((control) => control.testCoverage === 'covered').length,
    untestedControls: controls.filter((control) => control.testCoverage === 'missing').length,
    deadControls: findings.filter((finding) => finding.rule === 'missing-handler' || finding.rule === 'noop-handler')
      .length,
    missingHandlers: controls.filter((control) => control.status === 'missing_handler').length,
    noopHandlers: controls.filter((control) => control.status === 'noop_handler').length,
    disabledWithoutReason: findings.filter((finding) => finding.rule === 'disabled-without-reason').length,
    bridgeBoundControls: controls.filter((control) => control.bridgeFunction).length,
    bridgeMutationControls: controls.filter((control) => control.risk === 'bridge_mutation').length,
    criticalFindings: severityCount(findings, 'Critical'),
    highFindings: severityCount(findings, 'High'),
    mediumFindings: severityCount(findings, 'Medium'),
    lowFindings: severityCount(findings, 'Low'),
    testSuites: {
      unit: 'skipped',
      interaction: 'skipped',
      e2e: 'skipped',
      accessibility: 'skipped',
      responsive: 'skipped',
      build: 'skipped',
      lint: 'skipped',
    },
    blockers: findings
      .filter((finding) => finding.severity === 'Critical' || finding.severity === 'High')
      .map((finding) => `${finding.rule}: ${finding.file}:${finding.line}`),
  };
  fs.writeFileSync(path.join(OUTPUT_ROOT, 'qa-summary.json'), `${JSON.stringify(summary, null, 2)}\n`);

  const markdown = [
    '# Operator Panel Frontend QA Summary',
    '',
    `Generated: ${summary.generatedAtUtc}`,
    `Commit: ${summary.commit ?? 'unknown'}`,
    `Package version: ${summary.packageVersion}`,
    '',
    `Total controls: ${summary.totalControls}`,
    `Working controls: ${summary.workingControls}`,
    `Disabled with reason: ${summary.disabledWithReasonControls}`,
    `Removed until ready: ${summary.removedUntilReadyControls}`,
    `Missing test coverage evidence: ${summary.untestedControls}`,
    `Critical findings: ${summary.criticalFindings}`,
    `High findings: ${summary.highFindings}`,
    `Medium findings: ${summary.mediumFindings}`,
    '',
    summary.blockers.length > 0 ? '## Blockers' : '## Blockers',
    '',
    summary.blockers.length > 0 ? summary.blockers.map((blocker) => `- ${blocker}`).join('\n') : 'No gate blockers.',
  ];
  fs.writeFileSync(path.join(OUTPUT_ROOT, 'qa-summary.md'), `${markdown.join('\n')}\n`);
}

function checklistStatus(testIndex: Map<string, string>, page: Exclude<UiPage, 'Shared'>, patterns: string[]): string {
  const pageTests = PAGE_E2E_TESTS[page];
  const corpus = [...pageTests, 'src/App.integration.test.tsx', 'src/bridge.tauri.test.ts']
    .map((testPath) => testIndex.get(testPath) ?? '')
    .join('\n');
  return patterns.every((pattern) => corpus.includes(pattern)) ? 'Covered' : 'Needs review';
}

function pageRenderStatus(testIndex: Map<string, string>, page: Exclude<UiPage, 'Shared'>): string {
  return PAGE_E2E_TESTS[page].some((testPath) => testIndex.has(testPath)) ? 'Covered' : 'Needs review';
}

function writeManualChecklist(testIndex: Map<string, string>): void {
  const pageChecklist = [
    '# Operator Panel Page-Level Functional Checklist',
    '',
    '| Page | Render | Primary actions | Disabled reasons | Success/error feedback | Bridge/state args |',
    '|---|---|---|---|---|---|',
    ...PRODUCT_PAGES.map((page) => {
      const render = pageRenderStatus(testIndex, page);
      const primary = checklistStatus(testIndex, page, [
        page === 'Mission Control'
          ? 'workspace smoke renders preview mission control'
          : page === 'AI Assistant'
            ? 'AI Assistant model selection'
            : page === 'Tasks'
              ? 'tasks submit flow'
              : page === 'Approvals'
                ? 'approval lifecycle'
                : page === 'Runs'
                  ? 'runs workspace exposes'
                  : page === 'System'
                    ? 'system workspace refreshes'
                    : page === 'Operations'
                      ? 'operations workspace runs'
                      : 'settings persist',
      ]);
      const disabled = checklistStatus(testIndex, page, [
        page === 'AI Assistant'
          ? 'Search assistant context'
          : page === 'Tasks'
            ? 'Start session'
            : page === 'Approvals'
              ? 'toHaveAttribute'
              : page === 'Runs'
                ? 'toHaveAttribute'
                : page === 'Mission Control'
                  ? 'MACOS_COMPUTER_USE_NOT_QUALIFIED'
                  : 'expect',
      ]);
      const feedback = checklistStatus(testIndex, page, [
        page === 'Tasks'
          ? 'Submit run OK'
          : page === 'Approvals'
            ? 'Approve OK'
            : page === 'Runs'
              ? 'Export completed'
              : page === 'Settings'
                ? 'Settings saved'
                : page === 'Operations'
                  ? 'operationOutput'
                  : page === 'AI Assistant'
                    ? 'Summarize the active run safely.'
                    : page === 'System'
                      ? 'qwen3.5:4b'
                      : 'Mission Control',
      ]);
      const bridgeArgs = checklistStatus(testIndex, page, [
        page === 'AI Assistant'
          ? 'startAssistantTurn'
          : page === 'Tasks'
            ? 'submitTeamRun'
            : page === 'Approvals'
              ? 'decideApproval'
              : page === 'Runs'
                ? 'exportRunArtifacts'
                : page === 'System'
                  ? 'resolveConfig'
                  : page === 'Operations'
                    ? 'checkPermission'
                    : page === 'Settings'
                      ? 'localStorage'
                      : 'executeApproval',
      ]);
      return `| ${page} | ${render} | ${primary} | ${disabled} | ${feedback} | ${bridgeArgs} |`;
    }),
  ];
  fs.writeFileSync(path.join(OUTPUT_ROOT, 'page-level-checklist.md'), `${pageChecklist.join('\n')}\n`);

  const checklist = [
    '# Operator Panel Manual Exploratory Checklist',
    '',
    '| Area | Check | Result | Notes |',
    '|---|---|---|---|',
    '| Workspace | First screen content is clear and honest. | Not run | |',
    '| Sidebar | Every menu opens the expected view. | Not run | |',
    '| Top Refresh | Refresh gives visible feedback. | Not run | |',
    '| Tasks | Empty submit is safely blocked. | Not run | |',
    '| Tasks | Valid submit gives success or safe error feedback. | Not run | |',
    '| Approvals | Mutations stay disabled without operator ID. | Not run | |',
    '| Runs | Run selection, tabs, and export are wired. | Not run | |',
    '| System | Doctor, config, and capabilities are readable. | Not run | |',
    '| Operations | Each tab action updates output through mock/preview. | Not run | |',
    '| Settings | Saved settings persist after reload. | Not run | |',
    '| Computer-use | Start remains disabled when not qualified. | Not run | |',
    '| Debug Raw | Raw payload requires explicit confirmation. | Not run | |',
    '| Error UX | Bridge errors are safe and actionable. | Not run | |',
    '| Mobile | Navigation and primary CTAs are usable. | Not run | |',
    '| Keyboard | Core flows work without a mouse. | Not run | |',
  ];
  fs.writeFileSync(path.join(OUTPUT_ROOT, 'manual-exploratory-checklist.md'), `${checklist.join('\n')}\n`);
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
  const packageJson = JSON.parse(fs.readFileSync(path.join(APP_ROOT, 'package.json'), 'utf8')) as {
    version?: string;
  };
  return packageJson.version ?? 'unknown';
}

function escapePipe(value: string): string {
  return value.replace(/\|/g, '\\|').replace(/\s+/g, ' ').trim();
}

function main(): void {
  fs.mkdirSync(OUTPUT_ROOT, { recursive: true });
  const bridgeFunctions = readBridgeFunctionNames();
  const testIndex = readTestIndex();
  const sourceFiles = walkFiles(SRC_ROOT);
  const controls = sourceFiles.flatMap((filePath) => auditFile(filePath, bridgeFunctions, testIndex));
  const findings = [...buildFindings(controls), ...findDefaultNoopCallbackFindings(sourceFiles)];
  const summary = {
    generatedAtUtc: new Date().toISOString(),
    sourceRoot: path.relative(REPO_ROOT, SRC_ROOT),
    totalControls: controls.length,
    workingControls: controls.filter((control) => control.status === 'working').length,
    disabledWithReasonControls: controls.filter((control) => control.status === 'disabled_with_reason').length,
    removedUntilReadyControls: controls.filter((control) => control.status === 'removed_until_ready').length,
    missingHandlers: controls.filter((control) => control.status === 'missing_handler').length,
    noopHandlers: controls.filter((control) => control.status === 'noop_handler').length,
    disabledWithoutReason: findings.filter((finding) => finding.rule === 'disabled-without-reason').length,
    missingTestCoverage: controls.filter((control) => control.testCoverage === 'missing').length,
    needsManualReview: controls.filter((control) => control.status === 'unknown_handler' || control.requiresTest).length,
    criticalFindings: severityCount(findings, 'Critical'),
    highFindings: severityCount(findings, 'High'),
    mediumFindings: severityCount(findings, 'Medium'),
    lowFindings: severityCount(findings, 'Low'),
  };

  fs.writeFileSync(
    path.join(OUTPUT_ROOT, 'control-inventory.json'),
    `${JSON.stringify({ ...summary, controls, findings }, null, 2)}\n`,
  );
  writeMarkdown(controls, findings);
  writeQaSummary(controls, findings);
  writeManualChecklist(testIndex);

  console.log(
    `UI control audit: ${summary.totalControls} controls, ${summary.criticalFindings} critical, ${summary.highFindings} high, ${summary.mediumFindings} medium`,
  );

  if (summary.criticalFindings > 0 || summary.highFindings > 0) {
    process.exitCode = 1;
  }
}

main();
