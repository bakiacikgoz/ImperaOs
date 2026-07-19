import { describe, expect, it } from 'vitest';

import codeParityFixture from '../../../../contracts/artifacts/fixtures/code-content-parity.v1.json';

import {
  ArtifactContentSchema,
  ArtifactFormSubmissionResultSchema,
  ArtifactLicenseCapabilitySchema,
  ArtifactReadResultSchema,
  CanvasArtifactContentSchema,
  SpreadsheetArtifactContentSchema,
  SlidesArtifactContentSchema,
} from './artifactContracts';

const valid = {
  artifact: {
    artifactId: 'artifact-1', workspaceId: 'workspace-1', kind: 'document', title: 'Plan', status: 'active',
    schemaVersion: 1, dataClass: 'internal', currentRevisionId: 'revision-1', currentRevisionNumber: 1,
    sourceSessionId: null, sourceTurnId: null, createdByType: 'user', createdById: 'user-1', updatedById: 'user-1',
    createdAtUtc: '2026-07-16T08:00:00Z', updatedAtUtc: '2026-07-16T08:00:00Z', archivedAtUtc: null,
    etag: 'etag-1', metadata: {},
  },
  revision: {
    revisionId: 'revision-1', artifactId: 'artifact-1', parentRevisionId: null, baseRevisionId: null,
    revisionNumber: 1, schemaVersion: 1, mutationType: 'create', contentRelpath: 'workspace-1/artifact-1/revision-1.json',
    contentSha256: 'a'.repeat(64), contentSizeBytes: 32, contentEncoding: 'json', changeSummary: 'Created',
    authorType: 'user', authorId: 'user-1', idempotencyKey: 'create-1', createdAtUtc: '2026-07-16T08:00:00Z',
  },
  content: { kind: 'document', schemaVersion: 1, language: 'en', pageMode: 'document', blocks: [] },
};

describe('artifact read result contract', () => {
  it.each([
    ['revision identity', { ...valid, revision: { ...valid.revision, artifactId: 'artifact-2' } }],
    ['content kind', { ...valid, content: { kind: 'code', schemaVersion: 1 } }],
    ['content schema', { ...valid, content: { ...valid.content, schemaVersion: 2 } }],
  ])('rejects cross-boundary %s mismatches', (_label, payload) => {
    expect(ArtifactReadResultSchema.safeParse(payload).success).toBe(false);
  });
});

describe('artifact license capability contract', () => {
  it('binds the enabled state to the stable enabled reason', () => {
    expect(ArtifactLicenseCapabilitySchema.safeParse({
      contractVersion: 'artifact-license-capability/v1', kind: 'canvas', enabled: true,
      reasonCode: 'ARTIFACT_LICENSE_ENABLED',
    }).success).toBe(true);
    expect(ArtifactLicenseCapabilitySchema.safeParse({
      contractVersion: 'artifact-license-capability/v1', kind: 'canvas', enabled: true,
      reasonCode: 'ARTIFACT_LICENSE_EVIDENCE_MISSING',
    }).success).toBe(false);
  });
});

describe('artifact form submission contract', () => {
  const result = {
    submissionId: 'submission-1',
    artifactId: 'artifact-1',
    schemaRevisionId: 'revision-1',
    status: 'accepted',
    responseSha256: 'b'.repeat(64),
    continuationAction: 'none',
    approvalId: null,
    reasonCode: 'FORM_CONTINUATION_NOT_REQUIRED',
    actionHash: null,
    disposition: 'created',
  };

  it('accepts the bounded result and rejects unknown or unsafe fields', () => {
    expect(ArtifactFormSubmissionResultSchema.safeParse(result).success).toBe(true);
    expect(ArtifactFormSubmissionResultSchema.safeParse({ ...result, rawResponse: { secret: true } }).success).toBe(false);
    expect(ArtifactFormSubmissionResultSchema.safeParse({ ...result, status: 'executed' }).success).toBe(false);
  });
});

describe('code artifact content contract', () => {
  it.each(codeParityFixture.cases)('$id', ({ content, expectedValid }) => {
    expect(ArtifactContentSchema.safeParse(content).success).toBe(expectedValid);
  });
});

describe('spreadsheet v2 content contract', () => {
  const workbook = {
    kind: 'spreadsheet' as const,
    schemaVersion: 2 as const,
    calculationMode: 'disabled' as const,
    sheets: [{
      id: 'sheet-1', name: 'Sheet 1',
      cells: { XFD1048576: { value: 'last' }, A1: { value: 1.5 } },
      columns: [{ index: 1, width: 120, hidden: false }],
    }],
  };

  it('accepts scalar cells and rejects formulas, objects, unknown fields, and out-of-range addresses', () => {
    expect(SpreadsheetArtifactContentSchema.safeParse(workbook).success).toBe(true);
    expect(SpreadsheetArtifactContentSchema.safeParse({
      ...workbook, sheets: [{ ...workbook.sheets[0], cells: { XFE1: { value: 1 } } }],
    }).success).toBe(false);
    expect(SpreadsheetArtifactContentSchema.safeParse({
      ...workbook, sheets: [{ ...workbook.sheets[0], cells: { A1: { value: { formula: '=1+1' } } } }],
    }).success).toBe(false);
    expect(SpreadsheetArtifactContentSchema.safeParse({
      ...workbook, sheets: [{ ...workbook.sheets[0], cells: { A1: { value: 1, formula: '=1+1' } } }],
    }).success).toBe(false);
  });
});

describe('canvas v2 content contract', () => {
  const canvas = {
    kind: 'canvas' as const, schemaVersion: 2 as const,
    snapshot: { objects: [
      { id: 'shape-1', type: 'rectangle', x: 0, y: 0, width: 100, height: 80, text: 'Local' },
      { id: 'image-1', type: 'image', x: 10, y: 10, width: 40, height: 40, assetId: 'asset-1' },
    ] },
    assetIds: ['asset-1'], embeds: 'deny' as const, remoteAssets: 'deny' as const,
  };

  it('accepts local bounded objects and rejects remote, duplicate, and dangling content', () => {
    expect(CanvasArtifactContentSchema.safeParse(canvas).success).toBe(true);
    expect(CanvasArtifactContentSchema.safeParse({
      ...canvas, snapshot: { objects: [canvas.snapshot.objects[0], canvas.snapshot.objects[0]] },
    }).success).toBe(false);
    expect(CanvasArtifactContentSchema.safeParse({
      ...canvas, snapshot: { objects: [{ ...canvas.snapshot.objects[1], assetId: 'missing' }] },
    }).success).toBe(false);
    expect(CanvasArtifactContentSchema.safeParse({
      ...canvas, snapshot: { objects: [{ ...canvas.snapshot.objects[0], src: 'https://example.com/x' }] },
    }).success).toBe(false);
  });
});

describe('slides v2 content contract', () => {
  const deck = {
    kind: 'slides' as const, schemaVersion: 2 as const,
    theme: { name: 'ImperaOS', backgroundColor: 'FFFFFF', foregroundColor: '172033', accentColor: '6E57FF' },
    slides: [{ id: 'slide-1', title: 'Overview', elements: [
      { id: 'title-1', type: 'text' as const, x: 0.5, y: 0.5, width: 8, height: 1, text: 'Governed', fontSize: 30 },
      { id: 'image-1', type: 'image' as const, x: 9, y: 0.5, width: 3, height: 2, assetId: 'asset-1', altText: 'Local image' },
    ] }],
    assetIds: ['asset-1'],
  };

  it('accepts supported elements and rejects duplicates, dangling assets, and unknown fields', () => {
    expect(SlidesArtifactContentSchema.safeParse(deck).success).toBe(true);
    expect(SlidesArtifactContentSchema.safeParse({ ...deck, slides: [deck.slides[0], deck.slides[0]] }).success).toBe(false);
    expect(SlidesArtifactContentSchema.safeParse({
      ...deck, slides: [{ ...deck.slides[0], elements: [{ ...deck.slides[0].elements[1], assetId: 'missing' }] }],
    }).success).toBe(false);
    expect(SlidesArtifactContentSchema.safeParse({ ...deck, externalUrl: 'https://example.com' }).success).toBe(false);
  });
});
