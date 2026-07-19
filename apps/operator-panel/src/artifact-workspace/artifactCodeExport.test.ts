import { describe, expect, it, vi } from 'vitest';

import type { ArtifactBridge } from './artifactBridge';
import { exportCodeArtifact } from './artifactCodeExport';

const artifact = {
  artifactId: 'artifact-code', workspaceId: 'workspace-1', kind: 'code' as const, title: 'Source', status: 'active' as const,
  schemaVersion: 2, dataClass: 'internal' as const, currentRevisionId: 'revision-code-2', currentRevisionNumber: 2,
  sourceSessionId: null, sourceTurnId: null, createdByType: 'user' as const, createdById: 'user-1', updatedById: 'user-1',
  createdAtUtc: '2026-07-16T08:00:00Z', updatedAtUtc: '2026-07-16T08:00:00Z', archivedAtUtc: null,
  etag: 'etag-code-2', metadata: {},
};
const revision = {
  revisionId: 'revision-code-2', artifactId: artifact.artifactId, parentRevisionId: 'revision-code-1', baseRevisionId: null,
  revisionNumber: 2, schemaVersion: 2, mutationType: 'replace_content' as const, contentRelpath: 'content/code.json', contentSha256: 'a'.repeat(64),
  contentSizeBytes: 100, contentEncoding: 'json' as const, changeSummary: 'Updated', authorType: 'user' as const,
  authorId: 'user-1', idempotencyKey: 'update-code-2', createdAtUtc: '2026-07-16T08:00:00Z',
};

describe('code artifact native export', () => {
  it('commits exact stored CRLF bytes through a source ticket', async () => {
    const beginExport = vi.fn().mockResolvedValue({
      cancelled: false, ticket: 'ticket-code', expiresInMs: 60_000, maxBytes: 1024,
    });
    const commitExport = vi.fn().mockResolvedValue({
      basename: 'main.py', sha256: 'b'.repeat(64), sizeBytes: 9,
    });
    const bridge = { beginExport, commitExport, cancelExport: vi.fn() } as unknown as ArtifactBridge;
    const content = {
      kind: 'code' as const, schemaVersion: 2 as const, filename: 'main.py', language: 'python' as const,
      text: 'one\r\ntwo\r\n', lineEnding: 'crlf' as const, executionPolicy: 'deny' as const,
    };

    const result = await exportCodeArtifact({ artifact, revision, content, bridge });

    expect(beginExport).toHaveBeenCalledWith({
      artifactId: artifact.artifactId,
      revisionId: revision.revisionId,
      format: 'source',
      idempotencyKey: expect.stringMatching(/^export-/),
    });
    expect(new TextDecoder().decode(commitExport.mock.calls[0][1])).toBe(content.text);
    expect(result).toEqual({ status: 'exported', basename: 'main.py', sha256: 'b'.repeat(64), sizeBytes: 9 });
  });

  it('cancels the ticket on oversize without committing', async () => {
    const cancelExport = vi.fn().mockResolvedValue(undefined);
    const bridge = {
      beginExport: vi.fn().mockResolvedValue({ cancelled: false, ticket: 'ticket-small', expiresInMs: 60_000, maxBytes: 1 }),
      commitExport: vi.fn(),
      cancelExport,
    } as unknown as ArtifactBridge;
    await expect(exportCodeArtifact({
      artifact,
      revision,
      content: {
        kind: 'code', schemaVersion: 2, filename: 'main.py', language: 'python', text: 'ok',
        lineEnding: 'lf', executionPolicy: 'deny',
      },
      bridge,
    })).rejects.toThrow('Code export exceeds');
    expect(cancelExport).toHaveBeenCalledWith('ticket-small');
    expect(bridge.commitExport).not.toHaveBeenCalled();
  });
});
