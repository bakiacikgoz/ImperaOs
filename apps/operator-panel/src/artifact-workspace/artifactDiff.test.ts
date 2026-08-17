import { describe, expect, it } from 'vitest';

import {
  compareArtifactContent,
  MAX_ARTIFACT_DIFF_ENTRIES,
  MAX_ARTIFACT_DIFF_INSPECTED_ITEMS,
} from './artifactDiff';

const base = { schemaVersion: 1 } as const;

describe('bounded artifact revision comparisons', () => {
  it('compares document blocks by stable ID without phantom moves', () => {
    const block = (id: string, text = id) => ({
      id, type: 'paragraph', props: {}, content: [{ type: 'text', text, styles: {} }], children: [],
    });
    const before = { ...base, kind: 'document' as const, language: 'en', pageMode: 'document', blocks: [block('a'), block('b'), block('c')] };
    const after = { ...base, kind: 'document' as const, language: 'en', pageMode: 'document', blocks: [block('c', 'changed'), block('a'), block('b'), block('d')] };

    const result = compareArtifactContent(before, after);

    expect(result.entries).toEqual([
      expect.objectContaining({ scope: 'block', key: 'd', change: 'added' }),
      expect.objectContaining({ scope: 'block', key: 'c', change: 'moved' }),
      expect.objectContaining({ scope: 'block', key: 'c', change: 'changed', fields: ['content'] }),
    ]);
    expect(result).toMatchObject({ kind: 'document', totalChanges: 3, truncated: false, omittedChanges: 0 });
  });

  it('does not let an insertion mask a real sibling move', () => {
    const block = (id: string) => ({ id, type: 'paragraph', props: {}, content: [], children: [] });
    const before = { ...base, kind: 'document' as const, language: 'en', pageMode: 'document', blocks: ['a', 'b', 'c'].map(block) };
    const after = { ...base, kind: 'document' as const, language: 'en', pageMode: 'document', blocks: ['x', 'b', 'a', 'c'].map(block) };

    expect(compareArtifactContent(before, after).entries).toEqual([
      expect.objectContaining({ scope: 'block', key: 'x', change: 'added' }),
      expect.objectContaining({ scope: 'block', key: 'b', change: 'moved' }),
    ]);
  });

  it('compares code by bounded line position', () => {
    const before = { ...base, kind: 'code' as const, filename: 'a.ts', language: 'typescript' as const, text: 'one\ntwo', lineEnding: 'lf' as const, executionPolicy: 'deny' as const };
    const after = { ...before, text: 'one\nchanged\nthree' };

    expect(compareArtifactContent(before, after).entries).toEqual([
      { scope: 'line', key: '3', change: 'added' },
      { scope: 'line', key: '2', change: 'changed' },
    ]);
  });

  it('compares spreadsheet cells, flow objects, slides, form schema, and canvas objects', () => {
    const cases = [
      [
        { ...base, kind: 'spreadsheet', calculationMode: 'disabled', sheets: [{ id: 's1', name: 'Sheet', cells: { A1: { value: 1, style: {} } }, columns: [] }] },
        { ...base, kind: 'spreadsheet', calculationMode: 'disabled', sheets: [{ id: 's1', name: 'Sheet', cells: { A1: { value: 2, style: {} }, B1: { value: 3, style: {} } }, columns: [] }] },
        [['cell', 's1!B1', 'added'], ['cell', 's1!A1', 'changed']],
      ],
      [
        { ...base, kind: 'flow', nodes: [{ id: 'n1', type: 'input', position: { x: 0, y: 0 }, data: {} }], edges: [], viewport: { x: 0, y: 0, zoom: 1 } },
        { ...base, kind: 'flow', nodes: [{ id: 'n1', type: 'input', position: { x: 1, y: 0 }, data: {} }, { id: 'n2', type: 'output', position: { x: 2, y: 0 }, data: {} }], edges: [], viewport: { x: 0, y: 0, zoom: 1 } },
        [['object', 'node:n2', 'added'], ['object', 'node:n1', 'changed']],
      ],
      [
        { ...base, kind: 'slides', theme: {}, slides: [{ id: 'slide-1', elements: [] }] },
        { ...base, kind: 'slides', theme: {}, slides: [{ id: 'slide-1', elements: [{ id: 'e1', type: 'text' }] }, { id: 'slide-2', elements: [] }] },
        [['slide', 'slide-2', 'added'], ['slide', 'slide-1', 'changed']],
      ],
      [
        { ...base, kind: 'form', schema: { type: 'object', properties: { name: { type: 'string' } } }, uiSchema: {}, behavior: { submitMode: 'explicit', externalContinuation: 'deny' }, sensitivePaths: [] },
        { ...base, kind: 'form', schema: { type: 'object', properties: { name: { type: 'number' }, age: { type: 'integer' } } }, uiSchema: {}, behavior: { submitMode: 'explicit', externalContinuation: 'deny' }, sensitivePaths: [] },
        [['schema', '/properties/age', 'added'], ['schema', '/properties/name/type', 'changed']],
      ],
      [
        { ...base, kind: 'canvas', snapshot: { store: { shape1: { x: 1 } } }, assetIds: [], embeds: 'deny', remoteAssets: 'deny' },
        { ...base, kind: 'canvas', snapshot: { store: { shape1: { x: 2 }, shape2: {} } }, assetIds: [], embeds: 'deny', remoteAssets: 'deny' },
        [['object', '/store/shape2', 'added'], ['object', '/store/shape1/x', 'changed']],
      ],
    ] as const;

    for (const [before, after, expected] of cases) {
      const actual = compareArtifactContent(before, after).entries.map((entry) => [entry.scope, entry.key, entry.change]);
      expect(actual).toEqual(expected);
    }
  });

  it('fails closed on kind/schema mismatch and malformed document identity', () => {
    expect(() => compareArtifactContent(
      { ...base, kind: 'code', filename: 'a', language: 'plaintext', text: '', lineEnding: 'lf', executionPolicy: 'deny' },
      { ...base, kind: 'flow', nodes: [], edges: [], viewport: { x: 0, y: 0, zoom: 1 } },
    )).toThrow('Artifact diff kind mismatch.');
    expect(() => compareArtifactContent(
      { ...base, kind: 'document', language: 'en', pageMode: 'document', blocks: [{ id: 'same', type: 'paragraph', content: [], children: [] }, { id: 'same', type: 'paragraph', content: [], children: [] }] },
      { ...base, kind: 'document', language: 'en', pageMode: 'document', blocks: [] },
    )).toThrow('Document block IDs must be unique.');
  });

  it('sorts before truncating and reports omitted details deterministically', () => {
    const before = { ...base, kind: 'canvas' as const, snapshot: {}, assetIds: [], embeds: 'deny', remoteAssets: 'deny' };
    const snapshot = Object.fromEntries(Array.from({ length: MAX_ARTIFACT_DIFF_ENTRIES + 2 }, (_, index) => [`k${String(index).padStart(4, '0')}`, index]));
    const after = { ...before, snapshot };

    const first = compareArtifactContent(before, after);
    const second = compareArtifactContent(before, after);

    expect(first.entries).toHaveLength(MAX_ARTIFACT_DIFF_ENTRIES);
    expect(first).toMatchObject({ totalChanges: MAX_ARTIFACT_DIFF_ENTRIES + 2, omittedChanges: 2, truncated: true });
    expect(first.entries.at(-1)?.key).toBe('/k0499');
    expect(second).toEqual(first);
  });

  it('reports metadata-only changes for every persisted artifact kind', () => {
    const cases = [
      [
        { ...base, kind: 'document', language: 'en', pageMode: 'document', blocks: [] },
        { ...base, kind: 'document', language: 'tr', pageMode: 'paginated', blocks: [] },
      ],
      [
        { ...base, kind: 'code', filename: 'a.ts', language: 'typescript', text: '', lineEnding: 'lf', executionPolicy: 'deny' },
        { ...base, kind: 'code', filename: 'b.js', language: 'javascript', text: '', lineEnding: 'crlf', executionPolicy: 'deny' },
      ],
      [
        { ...base, kind: 'flow', nodes: [], edges: [], viewport: { x: 0, y: 0, zoom: 1 } },
        { ...base, kind: 'flow', nodes: [], edges: [], viewport: { x: 4, y: 0, zoom: 2 } },
      ],
      [
        { ...base, kind: 'spreadsheet', calculationMode: 'disabled', sheets: [{ id: 's', name: 'Before', cells: {}, columns: [] }] },
        { ...base, kind: 'spreadsheet', calculationMode: 'disabled', sheets: [{ id: 's', name: 'After', cells: {}, columns: [{ width: 20 }] }] },
      ],
      [
        { ...base, kind: 'slides', theme: { color: 'blue' }, slides: [] },
        { ...base, kind: 'slides', theme: { color: 'red' }, slides: [] },
      ],
      [
        { ...base, kind: 'form', schema: { type: 'object' }, uiSchema: {}, behavior: { submitMode: 'explicit', externalContinuation: 'deny' }, sensitivePaths: [] },
        { ...base, kind: 'form', schema: { type: 'object' }, uiSchema: { name: { 'ui:widget': 'text' } }, behavior: { submitMode: 'explicit', externalContinuation: 'deny' }, sensitivePaths: ['/name'] },
      ],
      [
        { ...base, kind: 'canvas', snapshot: {}, assetIds: [], embeds: 'deny', remoteAssets: 'deny' },
        { ...base, kind: 'canvas', snapshot: {}, assetIds: ['asset-1'], embeds: 'deny', remoteAssets: 'deny' },
      ],
    ] as const;

    for (const [before, after] of cases) {
      const result = compareArtifactContent(before, after);
      expect(result.totalChanges, before.kind).toBeGreaterThan(0);
      expect(result.entries, before.kind).not.toHaveLength(0);
    }
  });

  it('stops inspection and retained details at hard safety limits', () => {
    const before = { ...base, kind: 'canvas' as const, snapshot: {}, assetIds: [], embeds: 'deny', remoteAssets: 'deny' };
    const snapshot = Object.fromEntries(Array.from(
      { length: MAX_ARTIFACT_DIFF_INSPECTED_ITEMS + 1_000 },
      (_, index) => [`key-${String(index).padStart(5, '0')}`, index],
    ));

    const result = compareArtifactContent(before, { ...before, snapshot });

    expect(result.inspectedItems).toBeLessThanOrEqual(MAX_ARTIFACT_DIFF_INSPECTED_ITEMS);
    expect(result.entries).toHaveLength(MAX_ARTIFACT_DIFF_ENTRIES);
    expect(result).toMatchObject({ truncated: true, totalChangesIsLowerBound: true });
  });

  it('reports spreadsheet and slide reordering by stable ID', () => {
    const sheet = (id: string) => ({ id, name: id, cells: {}, columns: [] });
    const slide = (id: string) => ({ id, elements: [] });
    const spreadsheetBefore = { ...base, kind: 'spreadsheet' as const, calculationMode: 'disabled', sheets: ['a', 'b', 'c'].map(sheet) };
    const spreadsheetAfter = { ...spreadsheetBefore, sheets: ['b', 'a', 'c'].map(sheet) };
    const slidesBefore = { ...base, kind: 'slides' as const, theme: {}, slides: ['a', 'b', 'c'].map(slide) };
    const slidesAfter = { ...slidesBefore, slides: ['b', 'a', 'c'].map(slide) };

    expect(compareArtifactContent(spreadsheetBefore, spreadsheetAfter).entries).toContainEqual(
      expect.objectContaining({ scope: 'object', key: 'sheet:b', change: 'moved' }),
    );
    expect(compareArtifactContent(slidesBefore, slidesAfter).entries).toContainEqual(
      expect.objectContaining({ scope: 'slide', key: 'b', change: 'moved' }),
    );
  });

  it('uses locale-independent code-unit ordering', () => {
    const before = { ...base, kind: 'canvas' as const, snapshot: {}, assetIds: [], embeds: 'deny', remoteAssets: 'deny' };
    const result = compareArtifactContent(before, { ...before, snapshot: { ä: 1, z: 1 } });

    expect(result.entries.map((entry) => entry.key)).toEqual(['/z', '/ä']);
  });

  it('fails closed on non-JSON values, sparse arrays, and excessive object depth', () => {
    const canvas = (snapshot: Record<string, unknown>) => ({
      ...base, kind: 'canvas' as const, snapshot, assetIds: [], embeds: 'deny', remoteAssets: 'deny',
    });
    expect(() => compareArtifactContent(canvas({ x: Number.NaN }), canvas({ x: null })))
      .toThrow('Artifact content is not serializable.');
    expect(() => compareArtifactContent(canvas({ x: Array(1) }), canvas({ x: [] })))
      .toThrow('Artifact content is not serializable.');
    let deep: Record<string, unknown> = { value: 1 };
    for (let index = 0; index < 13; index += 1) deep = { child: deep };
    expect(() => compareArtifactContent(canvas(deep), canvas(structuredClone(deep))))
      .toThrow('Artifact diff object depth exceeded.');
    expect(() => compareArtifactContent(canvas({}), canvas({ added: Number.NaN })))
      .toThrow('Artifact content is not serializable.');
  });

  it('treats Object prototype names as ordinary own JSON keys', () => {
    const canvas = (snapshot: Record<string, unknown>) => ({
      ...base, kind: 'canvas' as const, snapshot, assetIds: [], embeds: 'deny', remoteAssets: 'deny',
    });

    expect(compareArtifactContent(canvas({ toString: 1 }), canvas({})).entries).toContainEqual(
      expect.objectContaining({ scope: 'object', key: '/toString', change: 'removed' }),
    );
  });

  it('rejects duplicate stable IDs for keyed kinds', () => {
    expect(() => compareArtifactContent(
      { ...base, kind: 'flow', nodes: [{ id: 'same' }, { id: 'same' }], edges: [], viewport: {} },
      { ...base, kind: 'flow', nodes: [], edges: [], viewport: {} },
    )).toThrow('Artifact diff item IDs must be unique.');
    expect(() => compareArtifactContent(
      { ...base, kind: 'spreadsheet', calculationMode: 'disabled', sheets: [{ id: 'same', cells: {} }, { id: 'same', cells: {} }] },
      { ...base, kind: 'spreadsheet', calculationMode: 'disabled', sheets: [] },
    )).toThrow('Spreadsheet sheets require unique IDs.');
    expect(() => compareArtifactContent(
      { ...base, kind: 'slides', theme: {}, slides: [{ id: 'same' }, { id: 'same' }] },
      { ...base, kind: 'slides', theme: {}, slides: [] },
    )).toThrow('Artifact diff item IDs must be unique.');
  });

  it('fails closed on one-sided invalid JSON in every specialized keyed kind', () => {
    const block = (props: Record<string, unknown>) => ({ id: 'bad', type: 'paragraph', props, content: [], children: [] });
    const cases = [
      [
        { ...base, kind: 'document', language: 'en', pageMode: 'document', blocks: [] },
        { ...base, kind: 'document', language: 'en', pageMode: 'document', blocks: [block({ x: Number.NaN })] },
      ],
      [
        { ...base, kind: 'flow', nodes: [], edges: [], viewport: {} },
        { ...base, kind: 'flow', nodes: [{ id: 'bad', data: { x: Number.NaN } }], edges: [], viewport: {} },
      ],
      [
        { ...base, kind: 'spreadsheet', calculationMode: 'disabled', sheets: [{ id: 's', name: 'S', columns: [], cells: {} }] },
        { ...base, kind: 'spreadsheet', calculationMode: 'disabled', sheets: [{ id: 's', name: 'S', columns: [], cells: { A1: { value: Number.NaN } } }] },
      ],
      [
        { ...base, kind: 'slides', theme: {}, slides: [] },
        { ...base, kind: 'slides', theme: {}, slides: [{ id: 'bad', value: Number.NaN }] },
      ],
    ] as const;

    for (const [before, after] of cases) {
      expect(() => compareArtifactContent(before, after), before.kind)
        .toThrow('Artifact content is not serializable.');
    }
  });
});
