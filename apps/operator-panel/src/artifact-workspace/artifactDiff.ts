import type { ArtifactContent, ArtifactKind } from './artifactContracts';
import {
  parseDocumentArtifactContent,
  type DocumentBlock,
} from './editors/document/documentAdapter';

export const MAX_ARTIFACT_DIFF_ENTRIES = 500;
export const MAX_ARTIFACT_DIFF_INSPECTED_ITEMS = 20_000;
const MAX_OBJECT_DEPTH = 12;

export type ArtifactDiffScope = 'block' | 'line' | 'cell' | 'object' | 'slide' | 'schema';
export type ArtifactDiffChange = 'removed' | 'added' | 'moved' | 'changed';

export type ArtifactDiffEntry = {
  scope: ArtifactDiffScope;
  key: string;
  change: ArtifactDiffChange;
  fields?: string[];
};

export type ArtifactDiffResult = {
  kind: ArtifactKind;
  entries: ArtifactDiffEntry[];
  inspectedItems: number;
  totalChanges: number;
  totalChangesIsLowerBound: boolean;
  omittedChanges: number;
  truncated: boolean;
};

type DiffAccumulator = {
  entries: ArtifactDiffEntry[];
  inspectedItems: number;
  inspectionTruncated: boolean;
  totalChanges: number;
};

const CHANGE_ORDER: Record<ArtifactDiffChange, number> = { removed: 0, added: 1, moved: 2, changed: 3 };

function compareCodeUnits(left: string, right: string): number {
  return left < right ? -1 : left > right ? 1 : 0;
}

function compareEntries(left: ArtifactDiffEntry, right: ArtifactDiffEntry): number {
  return CHANGE_ORDER[left.change] - CHANGE_ORDER[right.change]
    || compareCodeUnits(left.key, right.key)
    || compareCodeUnits(left.scope, right.scope)
    || compareCodeUnits(left.fields?.join('\u0000') ?? '', right.fields?.join('\u0000') ?? '');
}

function record(value: unknown, label: string): Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    throw new Error(`${label} must be an object.`);
  }
  const prototype = Object.getPrototypeOf(value);
  if (prototype !== Object.prototype && prototype !== null) {
    throw new Error('Artifact content is not serializable.');
  }
  return value as Record<string, unknown>;
}

function array(value: unknown, label: string): unknown[] {
  if (!Array.isArray(value)) throw new Error(`${label} must be an array.`);
  return value;
}

function inspect(accumulator: DiffAccumulator, count = 1): boolean {
  if (accumulator.inspectedItems + count > MAX_ARTIFACT_DIFF_INSPECTED_ITEMS) {
    accumulator.inspectionTruncated = true;
    return false;
  }
  accumulator.inspectedItems += count;
  return true;
}

function add(accumulator: DiffAccumulator, entry: ArtifactDiffEntry): void {
  accumulator.totalChanges += 1;
  if (accumulator.entries.length < MAX_ARTIFACT_DIFF_ENTRIES) {
    accumulator.entries.push(entry);
    return;
  }
  let worstIndex = 0;
  for (let index = 1; index < accumulator.entries.length; index += 1) {
    if (compareEntries(accumulator.entries[index], accumulator.entries[worstIndex]) > 0) worstIndex = index;
  }
  if (compareEntries(entry, accumulator.entries[worstIndex]) < 0) accumulator.entries[worstIndex] = entry;
}

function primitiveEqual(left: unknown, right: unknown): boolean {
  for (const value of [left, right]) {
    if (
      value === undefined
      || typeof value === 'bigint'
      || typeof value === 'function'
      || typeof value === 'symbol'
      || (typeof value === 'number' && !Number.isFinite(value))
    ) throw new Error('Artifact content is not serializable.');
  }
  return Object.is(left, right);
}

function escapePointer(segment: string): string {
  return segment.replaceAll('~', '~0').replaceAll('/', '~1');
}

function sampledOwnKeys(value: Record<string, unknown>, limit: number, accumulator: DiffAccumulator): string[] {
  const keys: string[] = [];
  for (const key in value) {
    if (!Object.prototype.hasOwnProperty.call(value, key)) continue;
    if (keys.length >= limit) {
      accumulator.inspectionTruncated = true;
      break;
    }
    keys.push(key);
  }
  return keys.sort(compareCodeUnits);
}

function hasOwn(value: Record<string, unknown>, key: string): boolean {
  return Object.prototype.hasOwnProperty.call(value, key);
}

function validateJsonValue(value: unknown, accumulator: DiffAccumulator, depth: number): void {
  if (!inspect(accumulator)) return;
  if (depth > MAX_OBJECT_DEPTH) throw new Error('Artifact diff object depth exceeded.');
  if (Array.isArray(value)) {
    for (let index = 0; index < value.length; index += 1) {
      if (!(index in value)) throw new Error('Artifact content is not serializable.');
      validateJsonValue(value[index], accumulator, depth + 1);
      if (accumulator.inspectedItems >= MAX_ARTIFACT_DIFF_INSPECTED_ITEMS) return;
    }
    return;
  }
  if (typeof value === 'object' && value !== null) {
    const object = record(value, 'Artifact diff value');
    const remaining = MAX_ARTIFACT_DIFF_INSPECTED_ITEMS - accumulator.inspectedItems;
    for (const key of sampledOwnKeys(object, remaining, accumulator)) {
      validateJsonValue(object[key], accumulator, depth + 1);
      if (accumulator.inspectedItems >= MAX_ARTIFACT_DIFF_INSPECTED_ITEMS) return;
    }
    return;
  }
  primitiveEqual(value, value);
}

function validateThenAdd(
  accumulator: DiffAccumulator,
  value: unknown,
  entry: ArtifactDiffEntry,
  depth = 0,
): void {
  validateJsonValue(value, accumulator, depth);
  add(accumulator, entry);
}

function compareObject(
  before: unknown,
  after: unknown,
  scope: 'object' | 'schema',
  accumulator: DiffAccumulator,
  path = '',
  depth = 0,
): void {
  if (!inspect(accumulator)) return;
  if (depth > MAX_OBJECT_DEPTH) throw new Error('Artifact diff object depth exceeded.');
  const beforeArray = Array.isArray(before);
  const afterArray = Array.isArray(after);
  const beforeObject = typeof before === 'object' && before !== null && !beforeArray;
  const afterObject = typeof after === 'object' && after !== null && !afterArray;

  if (beforeArray || afterArray) {
    if (!beforeArray || !afterArray) {
      add(accumulator, { scope, key: path || '/', change: 'changed' });
      return;
    }
    const count = Math.max(before.length, after.length);
    for (let index = 0; index < count; index += 1) {
      if ((index < before.length && !(index in before)) || (index < after.length && !(index in after))) {
        throw new Error('Artifact content is not serializable.');
      }
      if (accumulator.inspectedItems >= MAX_ARTIFACT_DIFF_INSPECTED_ITEMS) {
        accumulator.inspectionTruncated = true;
        return;
      }
      compareObject(before[index], after[index], scope, accumulator, `${path}/${index}`, depth + 1);
    }
    return;
  }

  if (beforeObject || afterObject) {
    if (!beforeObject || !afterObject) {
      add(accumulator, { scope, key: path || '/', change: 'changed' });
      return;
    }
    const left = record(before, 'Artifact diff value');
    const right = record(after, 'Artifact diff value');
    const remaining = MAX_ARTIFACT_DIFF_INSPECTED_ITEMS - accumulator.inspectedItems;
    if (remaining <= 0) {
      accumulator.inspectionTruncated = true;
      return;
    }
    const leftKeys = sampledOwnKeys(left, Math.ceil(remaining / 2), accumulator);
    const rightKeys = sampledOwnKeys(right, Math.floor(remaining / 2), accumulator);
    const keys = Array.from(new Set([...leftKeys, ...rightKeys])).sort(compareCodeUnits);
    for (const key of keys) {
      if (accumulator.inspectedItems >= MAX_ARTIFACT_DIFF_INSPECTED_ITEMS) {
        accumulator.inspectionTruncated = true;
        return;
      }
      const nextPath = `${path}/${escapePointer(key)}`;
      if (!hasOwn(left, key)) {
        add(accumulator, { scope, key: nextPath, change: 'added' });
        validateJsonValue(right[key], accumulator, depth + 1);
        if (accumulator.inspectedItems >= MAX_ARTIFACT_DIFF_INSPECTED_ITEMS) return;
      } else if (!hasOwn(right, key)) {
        add(accumulator, { scope, key: nextPath, change: 'removed' });
        validateJsonValue(left[key], accumulator, depth + 1);
        if (accumulator.inspectedItems >= MAX_ARTIFACT_DIFF_INSPECTED_ITEMS) return;
      } else {
        compareObject(left[key], right[key], scope, accumulator, nextPath, depth + 1);
      }
    }
    return;
  }

  if (before === undefined || after === undefined) {
    if (before !== after) {
      add(accumulator, {
        scope,
        key: path || '/',
        change: before === undefined ? 'added' : 'removed',
      });
    }
  } else if (!primitiveEqual(before, after)) {
    add(accumulator, {
      scope,
      key: path || '/',
      change: 'changed',
    });
  }
}

function differs(before: unknown, after: unknown, accumulator: DiffAccumulator, depth = 0): boolean | null {
  if (!inspect(accumulator)) return null;
  if (depth > MAX_OBJECT_DEPTH) throw new Error('Artifact diff object depth exceeded.');
  const leftArray = Array.isArray(before);
  const rightArray = Array.isArray(after);
  if (leftArray || rightArray) {
    if (!leftArray || !rightArray || before.length !== after.length) return true;
    for (let index = 0; index < before.length; index += 1) {
      if (!(index in before) || !(index in after)) throw new Error('Artifact content is not serializable.');
      const result = differs(before[index], after[index], accumulator, depth + 1);
      if (result !== false) return result;
    }
    return false;
  }
  const leftObject = typeof before === 'object' && before !== null;
  const rightObject = typeof after === 'object' && after !== null;
  if (leftObject || rightObject) {
    if (!leftObject || !rightObject) return true;
    const left = record(before, 'Artifact diff value');
    const right = record(after, 'Artifact diff value');
    const remaining = MAX_ARTIFACT_DIFF_INSPECTED_ITEMS - accumulator.inspectedItems;
    const leftKeys = sampledOwnKeys(left, Math.ceil(remaining / 2), accumulator);
    const rightKeys = sampledOwnKeys(right, Math.floor(remaining / 2), accumulator);
    if (accumulator.inspectionTruncated) return null;
    if (leftKeys.length !== rightKeys.length) return true;
    for (let index = 0; index < leftKeys.length; index += 1) {
      if (leftKeys[index] !== rightKeys[index]) return true;
      const result = differs(left[leftKeys[index]], right[rightKeys[index]], accumulator, depth + 1);
      if (result !== false) return result;
    }
    return false;
  }
  return !primitiveEqual(before, after);
}

type FlatBlock = { block: DocumentBlock; parentId: string | null; index: number; ordinal: number };

function flattenBlocks(blocks: DocumentBlock[], limit: number, accumulator: DiffAccumulator): Map<string, FlatBlock> {
  const flattened = new Map<string, FlatBlock>();
  let ordinal = 0;
  let complete = true;
  const visit = (items: DocumentBlock[], parentId: string | null) => {
    for (let index = 0; index < items.length; index += 1) {
      if (flattened.size >= limit) {
        complete = false;
        return;
      }
      const block = items[index];
      flattened.set(block.id, { block, parentId, index, ordinal: ordinal++ });
      visit(block.children, block.id);
      if (!complete) return;
    }
  };
  visit(blocks, null);
  if (!inspect(accumulator, flattened.size)) return new Map();
  if (!complete) accumulator.inspectionTruncated = true;
  return flattened;
}

function longestIncreasingSubsequencePositions(values: number[]): Set<number> {
  const tails: number[] = [];
  const tailPositions: number[] = [];
  const previous = new Array<number>(values.length).fill(-1);
  values.forEach((value, position) => {
    let low = 0;
    let high = tails.length;
    while (low < high) {
      const middle = (low + high) >>> 1;
      if (tails[middle] < value) low = middle + 1;
      else high = middle;
    }
    tails[low] = value;
    if (low > 0) previous[position] = tailPositions[low - 1];
    tailPositions[low] = position;
  });
  const retained = new Set<number>();
  let position = tailPositions[tails.length - 1] ?? -1;
  while (position >= 0) {
    retained.add(position);
    position = previous[position];
  }
  return retained;
}

function compareDocument(before: ArtifactContent, after: ArtifactContent, accumulator: DiffAccumulator): void {
  const left = parseDocumentArtifactContent(before);
  const right = parseDocumentArtifactContent(after);
  compareObject(
    { language: left.language, pageMode: left.pageMode },
    { language: right.language, pageMode: right.pageMode },
    'object', accumulator,
  );
  const remaining = MAX_ARTIFACT_DIFF_INSPECTED_ITEMS - accumulator.inspectedItems;
  const beforeBlocks = flattenBlocks(left.blocks, Math.ceil(remaining / 2), accumulator);
  const afterBlocks = flattenBlocks(right.blocks, Math.floor(remaining / 2), accumulator);

  for (const item of [...beforeBlocks.values()].sort((a, b) => a.ordinal - b.ordinal)) {
    if (!afterBlocks.has(item.block.id)) {
      validateThenAdd(accumulator, item.block, { scope: 'block', key: item.block.id, change: 'removed' });
    }
  }
  for (const item of [...afterBlocks.values()].sort((a, b) => a.ordinal - b.ordinal)) {
    if (!beforeBlocks.has(item.block.id)) {
      validateThenAdd(accumulator, item.block, { scope: 'block', key: item.block.id, change: 'added' });
    }
  }

  const moved = new Set<string>();
  for (const [id, current] of afterBlocks) {
    const prior = beforeBlocks.get(id);
    if (prior && prior.parentId !== current.parentId) moved.add(id);
  }
  const parentIds = new Set<string | null>();
  for (const item of afterBlocks.values()) parentIds.add(item.parentId);
  for (const parentId of parentIds) {
    const candidates = [...afterBlocks.values()]
      .filter((item) => item.parentId === parentId && beforeBlocks.get(item.block.id)?.parentId === parentId)
      .sort((a, b) => a.index - b.index);
    const beforeIndices = candidates.map((item) => beforeBlocks.get(item.block.id)?.index ?? -1);
    const retained = longestIncreasingSubsequencePositions(beforeIndices);
    candidates.forEach((item, position) => {
      const prior = beforeBlocks.get(item.block.id);
      if (prior && !retained.has(position)) moved.add(item.block.id);
    });
  }
  [...moved]
    .sort((a, b) => (afterBlocks.get(a)?.ordinal ?? 0) - (afterBlocks.get(b)?.ordinal ?? 0) || compareCodeUnits(a, b))
    .forEach((id) => add(accumulator, { scope: 'block', key: id, change: 'moved' }));

  for (const current of [...afterBlocks.values()].sort((a, b) => a.ordinal - b.ordinal)) {
    const prior = beforeBlocks.get(current.block.id);
    if (!prior) continue;
    const fields: string[] = [];
    for (const field of ['type', 'props', 'content'] as const) {
      const different = differs(prior.block[field], current.block[field], accumulator);
      if (different === null) return;
      if (different) fields.push(field);
    }
    if (fields.length > 0) add(accumulator, { scope: 'block', key: current.block.id, change: 'changed', fields });
  }
}

function compareCode(before: ArtifactContent, after: ArtifactContent, accumulator: DiffAccumulator): void {
  const left = record(before, 'Code content');
  const right = record(after, 'Code content');
  compareObject(
    { filename: left.filename, language: left.language, lineEnding: left.lineEnding, executionPolicy: left.executionPolicy },
    { filename: right.filename, language: right.language, lineEnding: right.lineEnding, executionPolicy: right.executionPolicy },
    'object', accumulator,
  );
  if (typeof left.text !== 'string' || typeof right.text !== 'string') throw new Error('Code content text must be a string.');
  const beforeLines = left.text.replaceAll('\r\n', '\n').split('\n');
  const afterLines = right.text.replaceAll('\r\n', '\n').split('\n');
  const count = Math.max(beforeLines.length, afterLines.length);
  for (let index = 0; index < count; index += 1) {
    if (!inspect(accumulator)) return;
    if (beforeLines[index] === afterLines[index]) continue;
    add(accumulator, {
      scope: 'line', key: String(index + 1),
      change: beforeLines[index] === undefined ? 'added' : afterLines[index] === undefined ? 'removed' : 'changed',
    });
  }
}

function sampledKeyedMap(items: unknown[], prefix: string, limit: number, accumulator: DiffAccumulator): Map<string, Record<string, unknown>> {
  const result = new Map<string, Record<string, unknown>>();
  const count = Math.min(items.length, limit);
  for (let index = 0; index < count; index += 1) {
    if (!inspect(accumulator)) break;
    const value = record(items[index], 'Artifact diff item');
    if (typeof value.id !== 'string' || !value.id) throw new Error('Artifact diff item requires an ID.');
    const key = `${prefix}${value.id}`;
    if (result.has(key)) throw new Error('Artifact diff item IDs must be unique.');
    result.set(key, value);
  }
  if (items.length > count) accumulator.inspectionTruncated = true;
  return result;
}

function reorderedKeys(
  left: Map<string, unknown>,
  right: Map<string, unknown>,
): string[] {
  const beforePositions = new Map([...left.keys()].map((key, index) => [key, index]));
  const candidates = [...right.keys()].filter((key) => left.has(key));
  const retained = longestIncreasingSubsequencePositions(
    candidates.map((key) => beforePositions.get(key) ?? -1),
  );
  return candidates.filter((_, position) => !retained.has(position));
}

function compareKeyedRecords(beforeItems: unknown[], afterItems: unknown[], prefix: string, accumulator: DiffAccumulator): void {
  const remaining = MAX_ARTIFACT_DIFF_INSPECTED_ITEMS - accumulator.inspectedItems;
  const left = sampledKeyedMap(beforeItems, prefix, Math.ceil(remaining / 2), accumulator);
  const right = sampledKeyedMap(afterItems, prefix, Math.floor(remaining / 2), accumulator);
  for (const key of [...left.keys()].sort(compareCodeUnits)) {
    if (!right.has(key)) validateThenAdd(accumulator, left.get(key), { scope: 'object', key, change: 'removed' });
  }
  for (const key of [...right.keys()].sort(compareCodeUnits)) {
    if (!left.has(key)) validateThenAdd(accumulator, right.get(key), { scope: 'object', key, change: 'added' });
  }
  for (const key of [...right.keys()].sort(compareCodeUnits)) {
    if (!left.has(key)) continue;
    const different = differs(left.get(key), right.get(key), accumulator);
    if (different === null) return;
    if (different) add(accumulator, { scope: 'object', key, change: 'changed' });
  }
}

function compareFlow(before: ArtifactContent, after: ArtifactContent, accumulator: DiffAccumulator): void {
  const left = record(before, 'Flow content');
  const right = record(after, 'Flow content');
  compareObject(left.viewport, right.viewport, 'object', accumulator, '/viewport');
  compareKeyedRecords(array(left.nodes, 'Flow nodes'), array(right.nodes, 'Flow nodes'), 'node:', accumulator);
  compareKeyedRecords(array(left.edges, 'Flow edges'), array(right.edges, 'Flow edges'), 'edge:', accumulator);
}

type SampledSheet = { id: string; metadata: Record<string, unknown>; cells: Record<string, unknown> };

function sampledSheets(value: ArtifactContent, limit: number, accumulator: DiffAccumulator): Map<string, SampledSheet> {
  const items = array(record(value, 'Spreadsheet content').sheets, 'Spreadsheet sheets');
  const result = new Map<string, SampledSheet>();
  const count = Math.min(items.length, limit);
  for (let index = 0; index < count; index += 1) {
    if (!inspect(accumulator)) break;
    const sheet = record(items[index], 'Spreadsheet sheet');
    if (typeof sheet.id !== 'string' || !sheet.id || result.has(sheet.id)) throw new Error('Spreadsheet sheets require unique IDs.');
    result.set(sheet.id, {
      id: sheet.id,
      metadata: { name: sheet.name, columns: sheet.columns },
      cells: record(sheet.cells, 'Spreadsheet cells'),
    });
  }
  if (items.length > count) accumulator.inspectionTruncated = true;
  return result;
}

function sampledCellKeys(cells: Record<string, unknown>, limit: number, accumulator: DiffAccumulator): string[] {
  return sampledOwnKeys(cells, limit, accumulator);
}

function compareSpreadsheet(before: ArtifactContent, after: ArtifactContent, accumulator: DiffAccumulator): void {
  const leftRoot = record(before, 'Spreadsheet content');
  const rightRoot = record(after, 'Spreadsheet content');
  compareObject(leftRoot.calculationMode, rightRoot.calculationMode, 'object', accumulator, '/calculationMode');
  let remaining = MAX_ARTIFACT_DIFF_INSPECTED_ITEMS - accumulator.inspectedItems;
  const left = sampledSheets(before, Math.ceil(remaining / 2), accumulator);
  const right = sampledSheets(after, Math.floor(remaining / 2), accumulator);
  for (const id of [...left.keys()].sort(compareCodeUnits)) {
    if (!right.has(id)) validateThenAdd(accumulator, left.get(id), { scope: 'object', key: `sheet:${id}`, change: 'removed' });
  }
  for (const id of [...right.keys()].sort(compareCodeUnits)) {
    if (!left.has(id)) validateThenAdd(accumulator, right.get(id), { scope: 'object', key: `sheet:${id}`, change: 'added' });
  }
  for (const id of reorderedKeys(left, right)) add(accumulator, { scope: 'object', key: `sheet:${id}`, change: 'moved' });
  for (const sheetId of [...right.keys()].sort(compareCodeUnits)) {
    const beforeSheet = left.get(sheetId);
    const afterSheet = right.get(sheetId);
    if (!beforeSheet || !afterSheet) continue;
    compareObject(beforeSheet.metadata, afterSheet.metadata, 'object', accumulator, `/sheets/${escapePointer(sheetId)}`);
    remaining = MAX_ARTIFACT_DIFF_INSPECTED_ITEMS - accumulator.inspectedItems;
    if (remaining <= 0) {
      accumulator.inspectionTruncated = true;
      return;
    }
    const beforeKeys = sampledCellKeys(beforeSheet.cells, Math.ceil(remaining / 2), accumulator);
    const afterKeys = sampledCellKeys(afterSheet.cells, Math.floor(remaining / 2), accumulator);
    const addresses = Array.from(new Set([...beforeKeys, ...afterKeys])).sort(compareCodeUnits);
    for (const address of addresses) {
      if (!inspect(accumulator)) return;
      const key = `${sheetId}!${address}`;
      if (!hasOwn(beforeSheet.cells, address)) {
        validateThenAdd(accumulator, afterSheet.cells[address], { scope: 'cell', key, change: 'added' });
      } else if (!hasOwn(afterSheet.cells, address)) {
        validateThenAdd(accumulator, beforeSheet.cells[address], { scope: 'cell', key, change: 'removed' });
      }
      else {
        const different = differs(beforeSheet.cells[address], afterSheet.cells[address], accumulator);
        if (different === null) return;
        if (different) add(accumulator, { scope: 'cell', key, change: 'changed' });
      }
    }
  }
}

function compareSlides(before: ArtifactContent, after: ArtifactContent, accumulator: DiffAccumulator): void {
  const leftRoot = record(before, 'Slides content');
  const rightRoot = record(after, 'Slides content');
  compareObject(leftRoot.theme, rightRoot.theme, 'object', accumulator, '/theme');
  const remaining = MAX_ARTIFACT_DIFF_INSPECTED_ITEMS - accumulator.inspectedItems;
  const left = sampledKeyedMap(array(leftRoot.slides, 'Slides'), '', Math.ceil(remaining / 2), accumulator);
  const right = sampledKeyedMap(array(rightRoot.slides, 'Slides'), '', Math.floor(remaining / 2), accumulator);
  for (const id of [...left.keys()].sort(compareCodeUnits)) {
    if (!right.has(id)) validateThenAdd(accumulator, left.get(id), { scope: 'slide', key: id, change: 'removed' });
  }
  for (const id of [...right.keys()].sort(compareCodeUnits)) {
    if (!left.has(id)) validateThenAdd(accumulator, right.get(id), { scope: 'slide', key: id, change: 'added' });
  }
  for (const id of reorderedKeys(left, right)) add(accumulator, { scope: 'slide', key: id, change: 'moved' });
  for (const id of [...right.keys()].sort(compareCodeUnits)) {
    if (!left.has(id)) continue;
    const different = differs(left.get(id), right.get(id), accumulator);
    if (different === null) return;
    if (different) add(accumulator, { scope: 'slide', key: id, change: 'changed' });
  }
}

export function compareArtifactContent(before: ArtifactContent, after: ArtifactContent): ArtifactDiffResult {
  if (before.kind !== after.kind) throw new Error('Artifact diff kind mismatch.');
  if (before.schemaVersion !== after.schemaVersion) throw new Error('Artifact diff schema version mismatch.');
  const accumulator: DiffAccumulator = {
    entries: [], inspectedItems: 0, inspectionTruncated: false, totalChanges: 0,
  };
  switch (before.kind) {
    case 'document': compareDocument(before, after, accumulator); break;
    case 'code': compareCode(before, after, accumulator); break;
    case 'spreadsheet': compareSpreadsheet(before, after, accumulator); break;
    case 'flow': compareFlow(before, after, accumulator); break;
    case 'slides': compareSlides(before, after, accumulator); break;
    case 'form': {
      const left = record(before, 'Form content');
      const right = record(after, 'Form content');
      compareObject(left.schema, right.schema, 'schema', accumulator);
      compareObject(
        { uiSchema: left.uiSchema, behavior: left.behavior, sensitivePaths: left.sensitivePaths },
        { uiSchema: right.uiSchema, behavior: right.behavior, sensitivePaths: right.sensitivePaths },
        'object', accumulator,
      );
      break;
    }
    case 'canvas': {
      const left = record(before, 'Canvas content');
      const right = record(after, 'Canvas content');
      compareObject(left.snapshot, right.snapshot, 'object', accumulator);
      compareObject(
        { assetIds: left.assetIds, embeds: left.embeds, remoteAssets: left.remoteAssets },
        { assetIds: right.assetIds, embeds: right.embeds, remoteAssets: right.remoteAssets },
        'object', accumulator,
      );
      break;
    }
    default: throw new Error('Artifact diff kind is unsupported.');
  }
  const entries = accumulator.entries.sort(compareEntries);
  const omittedChanges = Math.max(0, accumulator.totalChanges - entries.length);
  return {
    kind: before.kind,
    entries,
    inspectedItems: accumulator.inspectedItems,
    totalChanges: accumulator.totalChanges,
    totalChangesIsLowerBound: accumulator.inspectionTruncated,
    omittedChanges,
    truncated: accumulator.inspectionTruncated || omittedChanges > 0,
  };
}
