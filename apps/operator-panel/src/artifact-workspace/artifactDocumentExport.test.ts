import { describe, expect, it, vi } from 'vitest';

import type { ArtifactBridge } from './artifactBridge';
import type { ArtifactDescriptor, ArtifactRevision } from './artifactContracts';
import { exportDocumentArtifact } from './artifactDocumentExport';
import { parseDocumentArtifactContent } from './editors/document/documentAdapter';

const artifact = {
  artifactId: 'artifact-document',
  kind: 'document',
  title: 'Launch plan',
} as ArtifactDescriptor;
const revision = {
  revisionId: 'revision-2',
} as ArtifactRevision;
const content = parseDocumentArtifactContent({
  kind: 'document',
  schemaVersion: 1,
  language: 'en',
  pageMode: 'document',
  blocks: [
    {
      id: 'heading-1',
      type: 'heading',
      props: { level: 1 },
      content: [{ type: 'text', text: 'Launch plan', styles: {} }],
      children: [],
    },
  ],
});

describe('document artifact native export', () => {
  it('serializes Markdown and commits bytes through the native ticket boundary', async () => {
    const beginExport = vi.fn().mockResolvedValue({
      cancelled: false,
      ticket: 'ticket-1',
      expiresInMs: 60_000,
      maxBytes: 1024,
    });
    const commitExport = vi.fn().mockResolvedValue({
      basename: 'launch-plan.md',
      sha256: 'a'.repeat(64),
      sizeBytes: 14,
    });
    const bridge = { beginExport, commitExport, cancelExport: vi.fn() } as unknown as ArtifactBridge;

    const result = await exportDocumentArtifact({ artifact, revision, content, format: 'markdown', bridge });

    expect(beginExport).toHaveBeenCalledWith({
      artifactId: 'artifact-document',
      revisionId: 'revision-2',
      format: 'markdown',
      idempotencyKey: expect.stringMatching(/^export-/),
    });
    expect(new TextDecoder().decode(commitExport.mock.calls[0][1])).toBe('# Launch plan\n');
    expect(result).toEqual({
      status: 'exported',
      basename: 'launch-plan.md',
      sha256: 'a'.repeat(64),
      sizeBytes: 14,
    });
  });

  it('stops without renderer-side file access when the native dialog is cancelled', async () => {
    const commitExport = vi.fn();
    const bridge = {
      beginExport: vi.fn().mockResolvedValue({ cancelled: true, ticket: null, expiresInMs: null, maxBytes: 1024 }),
      commitExport,
      cancelExport: vi.fn(),
    } as unknown as ArtifactBridge;

    await expect(
      exportDocumentArtifact({ artifact, revision, content, format: 'html', bridge }),
    ).resolves.toEqual({ status: 'cancelled' });
    expect(commitExport).not.toHaveBeenCalled();
  });

  it('cancels an oversized ticket and preserves the bounded size failure', async () => {
    const cancelExport = vi.fn().mockRejectedValue(new Error('cancel transport failed'));
    const bridge = {
      beginExport: vi.fn().mockResolvedValue({ cancelled: false, ticket: 'ticket-small', expiresInMs: 60_000, maxBytes: 1 }),
      commitExport: vi.fn(),
      cancelExport,
    } as unknown as ArtifactBridge;

    await expect(
      exportDocumentArtifact({ artifact, revision, content, format: 'markdown', bridge }),
    ).rejects.toThrow('Document export exceeds the native size limit.');
    expect(cancelExport).toHaveBeenCalledWith('ticket-small');
    expect(bridge.commitExport).not.toHaveBeenCalled();
  });

  it('retains the ticket for terminal reconciliation after a commit failure', async () => {
    const commitFailure = new Error('native commit failed');
    const cancelExport = vi.fn().mockResolvedValue(undefined);
    const bridge = {
      beginExport: vi.fn().mockResolvedValue({ cancelled: false, ticket: 'ticket-fail', expiresInMs: 60_000, maxBytes: 1024 }),
      commitExport: vi.fn().mockRejectedValue(commitFailure),
      cancelExport,
    } as unknown as ArtifactBridge;

    await expect(
      exportDocumentArtifact({ artifact, revision, content, format: 'html', bridge }),
    ).rejects.toBe(commitFailure);
    expect(cancelExport).not.toHaveBeenCalled();
  });
});
