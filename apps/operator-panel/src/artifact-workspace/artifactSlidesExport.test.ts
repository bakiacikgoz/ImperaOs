import { describe, expect, it, vi } from 'vitest';

import type { ArtifactBridge } from './artifactBridge';
import { exportSlidesArtifact } from './artifactSlidesExport';
import type { ArtifactDescriptor, ArtifactRevision, SlidesArtifactContent } from './artifactContracts';
import { serializeSlidesPptx } from './slidesPptxSerializer';

const content = {
  kind: 'slides', schemaVersion: 2,
  theme: { name: 'ImperaOS', backgroundColor: 'FFFFFF', foregroundColor: '172033', accentColor: '6E57FF' },
  slides: [{ id: 'slide-1', title: 'Overview', elements: [
    { id: 'text-1', type: 'text', x: 0.5, y: 0.5, width: 5, height: 1, text: 'Governed', fontSize: 28, bold: true, color: null },
    { id: 'shape-1', type: 'shape', x: 0.5, y: 2, width: 2, height: 1, shape: 'rectangle', fillColor: '6E57FF', lineColor: '172033' },
    { id: 'table-1', type: 'table', x: 3, y: 2, width: 4, height: 2, rows: [['Name', 'Value'], ['Safe', 1]] },
    { id: 'chart-1', type: 'chart', x: 7.5, y: 2, width: 5, height: 3, chartType: 'bar', categories: ['A', 'B'], series: [{ name: 'Count', values: [1, 2] }] },
  ] }], assetIds: [],
} satisfies SlidesArtifactContent;
const artifact = {
  artifactId: 'slides-1', workspaceId: 'workspace-1', kind: 'slides', title: 'Deck', status: 'active',
  schemaVersion: 2, dataClass: 'internal', currentRevisionId: 'revision-2', currentRevisionNumber: 2,
  sourceSessionId: null, sourceTurnId: null, createdByType: 'user', createdById: 'user-1', updatedById: 'user-1',
  createdAtUtc: '2026-07-16T08:00:00Z', updatedAtUtc: '2026-07-16T08:01:00Z', archivedAtUtc: null,
  etag: 'etag', metadata: {},
} satisfies ArtifactDescriptor;
const revision = {
  revisionId: 'revision-2', artifactId: artifact.artifactId, parentRevisionId: 'revision-1', baseRevisionId: null,
  revisionNumber: 2, schemaVersion: 2, mutationType: 'replace_content', contentRelpath: 'slides.json',
  contentSha256: 'a'.repeat(64), contentSizeBytes: 100, contentEncoding: 'json', changeSummary: 'Slides',
  authorType: 'user', authorId: 'user-1', idempotencyKey: 'save-2', createdAtUtc: '2026-07-16T08:01:00Z',
} satisfies ArtifactRevision;

describe('slides PPTX export', () => {
  it('creates a local PPTX zip without macro, OLE, or external relationships', async () => {
    const withImage = {
      ...content,
      slides: [{ ...content.slides[0], elements: [
        ...content.slides[0].elements,
        { id: 'image-1', type: 'image', x: 0.5, y: 5.5, width: 1, height: 1, assetId: 'asset-1', altText: 'Local image' },
      ] }],
      assetIds: ['asset-1'],
    } satisfies SlidesArtifactContent;
    const bytes = await serializeSlidesPptx(withImage, {
      'asset-1': {
        dataUrl: 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=',
        sha256: 'a'.repeat(64),
      },
    });
    expect([...bytes.slice(0, 2)]).toEqual([0x50, 0x4b]);
    const raw = new TextDecoder('latin1').decode(bytes);
    expect(raw).toContain('ppt/slides/slide1.xml');
    expect(raw).toContain('ppt/media/image');
    expect(raw).not.toMatch(/vbaProject|oleObject|TargetMode="External"/i);
  });

  it('uses the exact revision ticket and cancels oversized bytes', async () => {
    const bridge = {
      beginExport: vi.fn().mockResolvedValue({ cancelled: false, ticket: 'ticket-1', maxBytes: 2 }),
      commitExport: vi.fn(), cancelExport: vi.fn().mockResolvedValue(undefined),
    } as unknown as ArtifactBridge;
    await expect(exportSlidesArtifact({
      artifact, revision, content, bridge,
      serialize: vi.fn().mockResolvedValue(Uint8Array.of(1, 2, 3)),
    })).rejects.toThrow(/size limit/i);
    expect(bridge.beginExport).toHaveBeenCalledWith(expect.objectContaining({
      artifactId: artifact.artifactId, revisionId: revision.revisionId, format: 'pptx',
    }));
    expect(bridge.cancelExport).toHaveBeenCalledWith('ticket-1');
  });

  it('resolves only referenced assets sequentially and caps them before serialization', async () => {
    const withImage = {
      ...content,
      slides: [{ ...content.slides[0], elements: [
        ...content.slides[0].elements,
        { id: 'image-1', type: 'image', x: 0.5, y: 5.5, width: 1, height: 1, assetId: 'asset-used', altText: 'Used' },
      ] }],
      assetIds: ['asset-used', 'asset-unused'],
    } satisfies SlidesArtifactContent;
    const serialize = vi.fn();
    const bridge = {
      beginExport: vi.fn().mockResolvedValue({ cancelled: false, ticket: 'ticket-2', maxBytes: 9 }),
      getAsset: vi.fn().mockResolvedValue({
        asset: { assetId: 'asset-used', sizeBytes: 10 }, contentBase64: 'AA==',
      }),
      commitExport: vi.fn(), cancelExport: vi.fn().mockResolvedValue(undefined),
    } as unknown as ArtifactBridge;

    await expect(exportSlidesArtifact({ artifact, revision, content: withImage, bridge, serialize }))
      .rejects.toThrow(/assets exceed/i);
    expect(bridge.getAsset).toHaveBeenCalledTimes(1);
    expect(bridge.getAsset).not.toHaveBeenCalledWith('asset-unused');
    expect(serialize).not.toHaveBeenCalled();
    expect(bridge.cancelExport).toHaveBeenCalledWith('ticket-2');
  });
});
