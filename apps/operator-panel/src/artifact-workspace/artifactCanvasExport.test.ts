import { describe, expect, it, vi } from 'vitest';

import type { ArtifactBridge } from './artifactBridge';
import { exportCanvasArtifact, serializeCanvasJson, serializeCanvasSvg } from './artifactCanvasExport';
import type { ArtifactDescriptor, ArtifactRevision, CanvasArtifactContent } from './artifactContracts';

const content = {
  kind: 'canvas', schemaVersion: 2,
  snapshot: { objects: [{
    id: 'note-1', type: 'note', x: 1, y: 2, width: 200, height: 100,
    text: '<script>local text only</script>',
  }] },
  assetIds: [], embeds: 'deny', remoteAssets: 'deny',
} satisfies CanvasArtifactContent;
const artifact = {
  artifactId: 'canvas-1', workspaceId: 'workspace-1', kind: 'canvas', title: 'Board',
  status: 'active', schemaVersion: 2, dataClass: 'internal', currentRevisionId: 'revision-2',
  currentRevisionNumber: 2, sourceSessionId: null, sourceTurnId: null, createdByType: 'user',
  createdById: 'user-1', updatedById: 'user-1', createdAtUtc: '2026-07-16T08:00:00Z',
  updatedAtUtc: '2026-07-16T08:01:00Z', archivedAtUtc: null, etag: 'etag', metadata: {},
} satisfies ArtifactDescriptor;
const revision = {
  revisionId: 'revision-2', artifactId: artifact.artifactId, parentRevisionId: 'revision-1',
  baseRevisionId: null, revisionNumber: 2, schemaVersion: 2, mutationType: 'replace_content',
  contentRelpath: 'content/canvas.json', contentSha256: 'a'.repeat(64), contentSizeBytes: 100,
  contentEncoding: 'json', changeSummary: 'Board', authorType: 'user', authorId: 'user-1',
  idempotencyKey: 'save-1', createdAtUtc: '2026-07-16T08:01:00Z',
} satisfies ArtifactRevision;

describe('canvas fallback export', () => {
  it('serializes only the strict local canvas.v2 contract', () => {
    expect(new TextDecoder().decode(serializeCanvasJson(content))).toBe(`${JSON.stringify(content, null, 2)}\n`);
    expect(() => serializeCanvasJson({ ...content, remoteAssets: 'allow' })).toThrow();
    expect(() => serializeCanvasJson({ ...content, snapshot: { objects: [{ ...content.snapshot.objects[0], src: 'https://example.com' }] } })).toThrow();
    expect(() => serializeCanvasJson({
      kind: 'canvas', schemaVersion: 1, snapshot: { store: {} }, assetIds: [],
      embeds: 'deny', remoteAssets: 'deny', unexpected: true,
    })).toThrow();
  });

  it('keeps the legacy read-only JSON fallback exportable', async () => {
    const bridge = {
      beginExport: vi.fn().mockResolvedValue({ cancelled: true }),
    } as unknown as ArtifactBridge;
    await expect(exportCanvasArtifact({
      artifact: { ...artifact, schemaVersion: 1 },
      revision: { ...revision, schemaVersion: 1 },
      content: {
        kind: 'canvas', schemaVersion: 1, snapshot: { store: {} }, assetIds: [],
        embeds: 'deny', remoteAssets: 'deny',
      },
      bridge,
    })).resolves.toEqual({ status: 'cancelled' });
  });

  it.each(['json', 'svg', 'png'] as const)('stops before canvas %s serialization when the native ticket is cancelled', async (format) => {
    const renderPng = vi.fn().mockRejectedValue(new Error('PNG renderer must not run'));
    const bridge = {
      beginExport: vi.fn().mockResolvedValue({ cancelled: true }),
      cancelExport: vi.fn(),
      commitExport: vi.fn(),
    } as unknown as ArtifactBridge;

    await expect(exportCanvasArtifact({
      artifact,
      revision,
      content: { invalid: true } as never,
      format,
      bridge,
      renderPng,
    })).resolves.toEqual({ status: 'cancelled' });
    expect(bridge.beginExport).toHaveBeenCalledOnce();
    expect(renderPng).not.toHaveBeenCalled();
    expect(bridge.cancelExport).not.toHaveBeenCalled();
    expect(bridge.commitExport).not.toHaveBeenCalled();
  });

  it('serializes bounded SVG without interpreting canvas text as markup', () => {
    const svg = serializeCanvasSvg(content);
    expect(svg.text).toContain('&lt;script&gt;local text only&lt;/script&gt;');
    expect(svg.text).not.toContain('<script>');
    expect(svg.width).toBeGreaterThan(0);
    expect(svg.height).toBeGreaterThan(0);
  });

  it('resolves governed local images into SVG export data', async () => {
    const imageContent = {
      ...content,
      snapshot: { objects: [{ id: 'image-1', type: 'image' as const, x: 0, y: 0, width: 40, height: 30, assetId: 'asset-1' }] },
      assetIds: ['asset-1'],
    };
    const commitExport = vi.fn().mockResolvedValue({ basename: 'board.svg', sha256: 'a'.repeat(64), sizeBytes: 100 });
    const bridge = {
      beginExport: vi.fn().mockResolvedValue({ cancelled: false, ticket: 'ticket-1', maxBytes: 1_000_000 }),
      getAsset: vi.fn().mockResolvedValue({
        asset: { assetId: 'asset-1', workspaceId: 'workspace-1', sha256: 'b'.repeat(64), mediaType: 'image/png', sizeBytes: 4, relativePath: 'assets/a.png', width: 1, height: 1, originalName: 'a.png', dataClass: 'internal', createdById: 'user-1', createdAtUtc: '2026-07-16T08:00:00Z' },
        contentBase64: 'iVBORw0KGgo=',
      }),
      commitExport,
      cancelExport: vi.fn(),
    } as unknown as ArtifactBridge;

    await exportCanvasArtifact({ artifact, revision, content: imageContent, format: 'svg', bridge });
    const svg = new TextDecoder().decode(commitExport.mock.calls[0][1]);
    expect(svg).toContain('<image');
    expect(svg).toContain('data:image/png;base64,iVBORw0KGgo=');
    expect(bridge.getAsset).toHaveBeenCalledWith('asset-1');
  });

  it.each(['svg', 'png'] as const)('routes canvas %s through the canvas export ticket', async (format) => {
    const bytes = new TextEncoder().encode('png');
    const bridge = {
      beginExport: vi.fn().mockResolvedValue({ cancelled: false, ticket: 'ticket-1', maxBytes: 1_000_000 }),
      commitExport: vi.fn().mockResolvedValue({ basename: `board.${format}`, sha256: 'a'.repeat(64), sizeBytes: 3 }),
      cancelExport: vi.fn(),
    } as unknown as ArtifactBridge;

    await expect(exportCanvasArtifact({
      artifact,
      revision,
      content,
      format,
      bridge,
      renderPng: async () => bytes,
    })).resolves.toMatchObject({ status: 'exported' });
    expect(bridge.beginExport).toHaveBeenCalledWith(expect.objectContaining({ format }));
  });

  it('uses the canvas revision ticket and cancels oversized output', async () => {
    const bridge = {
      beginExport: vi.fn().mockResolvedValue({ cancelled: false, ticket: 'ticket-1', maxBytes: 2 }),
      commitExport: vi.fn(),
      cancelExport: vi.fn().mockResolvedValue(undefined),
    } as unknown as ArtifactBridge;
    await expect(exportCanvasArtifact({ artifact, revision, content, bridge })).rejects.toThrow(/size limit/i);
    expect(bridge.beginExport).toHaveBeenCalledWith(expect.objectContaining({
      artifactId: artifact.artifactId, revisionId: revision.revisionId, format: 'json',
    }));
    expect(bridge.cancelExport).toHaveBeenCalledWith('ticket-1');
  });

  it.each(['json', 'svg'] as const)('cancels the native ticket when canvas %s serialization fails', async (format) => {
    const bridge = {
      beginExport: vi.fn().mockResolvedValue({ cancelled: false, ticket: 'ticket-1', maxBytes: 1_000_000 }),
      commitExport: vi.fn(),
      cancelExport: vi.fn().mockResolvedValue(undefined),
    } as unknown as ArtifactBridge;

    await expect(exportCanvasArtifact({
      artifact,
      revision,
      content: { invalid: true } as never,
      format,
      bridge,
    })).rejects.toThrow();
    expect(bridge.cancelExport).toHaveBeenCalledWith('ticket-1');
    expect(bridge.commitExport).not.toHaveBeenCalled();
  });

  it('cancels the native ticket when PNG rendering fails', async () => {
    const bridge = {
      beginExport: vi.fn().mockResolvedValue({ cancelled: false, ticket: 'ticket-1', maxBytes: 1_000_000 }),
      commitExport: vi.fn(),
      cancelExport: vi.fn().mockResolvedValue(undefined),
    } as unknown as ArtifactBridge;

    await expect(exportCanvasArtifact({
      artifact,
      revision,
      content,
      format: 'png',
      bridge,
      renderPng: vi.fn().mockRejectedValue(new Error('render failed')),
    })).rejects.toThrow('render failed');
    expect(bridge.cancelExport).toHaveBeenCalledWith('ticket-1');
    expect(bridge.commitExport).not.toHaveBeenCalled();
  });

  it('enforces the ticket bound before allocating the PNG raster', async () => {
    const renderPng = vi.fn().mockResolvedValue(new Uint8Array([1]));
    const bridge = {
      beginExport: vi.fn().mockResolvedValue({ cancelled: false, ticket: 'ticket-1', maxBytes: 2 }),
      commitExport: vi.fn(),
      cancelExport: vi.fn().mockResolvedValue(undefined),
    } as unknown as ArtifactBridge;

    await expect(exportCanvasArtifact({
      artifact,
      revision,
      content,
      format: 'png',
      bridge,
      renderPng,
    })).rejects.toThrow(/size limit/i);
    expect(renderPng).not.toHaveBeenCalled();
    expect(bridge.cancelExport).toHaveBeenCalledWith('ticket-1');
    expect(bridge.commitExport).not.toHaveBeenCalled();
  });
});
