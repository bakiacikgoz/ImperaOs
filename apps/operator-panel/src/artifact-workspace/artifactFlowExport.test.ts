import { describe, expect, it, vi } from 'vitest';

import type { ArtifactBridge } from './artifactBridge';
import { exportFlowArtifact, serializeFlowSvg } from './artifactFlowExport';
import type { ArtifactDescriptor, ArtifactRevision, FlowArtifactContent } from './artifactContracts';

const artifact = {
  artifactId: 'artifact-flow-1', workspaceId: 'workspace-1', kind: 'flow', title: 'Approval flow', status: 'active',
  schemaVersion: 2, dataClass: 'internal', currentRevisionId: 'revision-flow-2', currentRevisionNumber: 2,
  sourceSessionId: null, sourceTurnId: null, createdByType: 'user', createdById: 'user-1', updatedById: 'user-1',
  createdAtUtc: '2026-07-16T08:00:00Z', updatedAtUtc: '2026-07-16T08:01:00Z', archivedAtUtc: null,
  etag: 'etag-flow-2', metadata: {},
} satisfies ArtifactDescriptor;
const revision = {
  revisionId: 'revision-flow-2', artifactId: artifact.artifactId, parentRevisionId: 'revision-flow-1', baseRevisionId: null,
  revisionNumber: 2, schemaVersion: 2, mutationType: 'replace_content', contentRelpath: 'content/flow.json', contentSha256: 'a'.repeat(64),
  contentSizeBytes: 256, contentEncoding: 'json', changeSummary: 'Moved node', authorType: 'user', authorId: 'user-1',
  idempotencyKey: 'save-flow-2', createdAtUtc: '2026-07-16T08:01:00Z',
} satisfies ArtifactRevision;
const content = {
  kind: 'flow', schemaVersion: 2,
  nodes: [
    { id: 'start', type: 'input', position: { x: 0, y: 0 }, data: { label: '<script>alert(1)</script>' } },
    { id: 'end', type: 'output', position: { x: 200, y: 0 }, data: { label: 'End' } },
  ],
  edges: [{ id: 'edge-1', source: 'start', target: 'end', label: 'safe & local' }],
  viewport: { x: 0, y: 0, zoom: 1 },
} satisfies FlowArtifactContent;

function bridge(maxBytes = 1_000_000) {
  const commitExport = vi.fn().mockResolvedValue({ basename: 'flow.svg', sha256: 'b'.repeat(64), sizeBytes: 10 });
  const cancelExport = vi.fn().mockResolvedValue(undefined);
  return {
    beginExport: vi.fn().mockResolvedValue({ cancelled: false, ticket: 'ticket-1', expiresInMs: 60_000, maxBytes }),
    commitExport,
    cancelExport,
  } as unknown as ArtifactBridge & { commitExport: typeof commitExport; cancelExport: typeof cancelExport };
}

describe('flow artifact export', () => {
  it('emits deterministic strict JSON and sanitized generated SVG', async () => {
    const jsonBridge = bridge();
    await exportFlowArtifact({ artifact, revision, content, format: 'json', bridge: jsonBridge });
    const jsonBytes = jsonBridge.commitExport.mock.calls[0][1] as Uint8Array;
    expect(new TextDecoder().decode(jsonBytes)).toBe(`${JSON.stringify(content, null, 2)}\n`);

    const svg = serializeFlowSvg(content).text;
    expect(svg).toContain('&lt;script&gt;alert(1)&lt;/script&gt;');
    expect(svg).toContain('safe &amp; local');
    expect(svg).not.toMatch(/<script|onload=|(?:href|src)=["']https?:\/\//i);
  });

  it('uses a bounded local PNG renderer and cancels oversized output', async () => {
    const pngBridge = bridge(2);
    const renderPng = vi.fn().mockResolvedValue(Uint8Array.of(137, 80, 78));
    await expect(exportFlowArtifact({
      artifact, revision, content, format: 'png', bridge: pngBridge, renderPng,
    })).rejects.toThrow(/size limit/i);
    expect(renderPng).toHaveBeenCalledOnce();
    expect(pngBridge.cancelExport).toHaveBeenCalledWith('ticket-1');
    expect(pngBridge.commitExport).not.toHaveBeenCalled();
  });
});
