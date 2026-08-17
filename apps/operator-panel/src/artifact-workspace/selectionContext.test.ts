import { describe, expect, it } from 'vitest';

import { ArtifactContextSelectionSchema, contextSelectionLabel } from './selectionContext';

describe('artifact context selection', () => {
  it('parses all seven coordinate-only selection shapes', () => {
    const fixtures = [
      { kind: 'document', blockIds: ['block-1'] },
      { kind: 'form', fieldPaths: ['/name'] },
      { kind: 'code', startLineNumber: 1, startColumn: 1, endLineNumber: 2, endColumn: 4 },
      { kind: 'flow', nodeIds: ['node-1'], edgeIds: [] },
      { kind: 'spreadsheet', sheetId: 'sheet-1', ranges: ['A1:B2'] },
      { kind: 'canvas', objectIds: ['object-1'] },
      { kind: 'slides', slideId: 'slide-1', elementId: null },
    ];

    fixtures.forEach((fixture) => expect(ArtifactContextSelectionSchema.parse(fixture)).toEqual(fixture));
  });

  it('rejects raw selected content and unsafe spreadsheet ranges', () => {
    expect(ArtifactContextSelectionSchema.safeParse({
      kind: 'document', blockIds: ['block-1'], rawText: 'must not cross the boundary',
    }).success).toBe(false);
    expect(ArtifactContextSelectionSchema.safeParse({
      kind: 'spreadsheet', sheetId: 'sheet-1', ranges: ['A1:XFE1'],
    }).success).toBe(false);
  });

  it('provides a bounded human label without selected content', () => {
    expect(contextSelectionLabel({ kind: 'code', startLineNumber: 4, startColumn: 2, endLineNumber: 8, endColumn: 7 }))
      .toBe('Code lines 4–8');
  });
});
