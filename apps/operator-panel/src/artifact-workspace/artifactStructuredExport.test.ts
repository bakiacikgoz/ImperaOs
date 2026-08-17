import { describe, expect, it, vi } from 'vitest';

import type { ArtifactBridge } from './artifactBridge';
import type { ArtifactDescriptor, ArtifactRevision } from './artifactContracts';
import { exportStructuredArtifact } from './artifactStructuredExport';

const artifact = {
  artifactId: 'form-1', workspaceId: 'workspace-1', kind: 'form', title: 'Intake', status: 'active', schemaVersion: 1,
  dataClass: 'internal', currentRevisionId: 'revision-1', currentRevisionNumber: 1, sourceSessionId: null,
  sourceTurnId: null, createdByType: 'user', createdById: 'user-1', updatedById: 'user-1',
  createdAtUtc: '2026-07-16T08:00:00Z', updatedAtUtc: '2026-07-16T08:00:00Z', archivedAtUtc: null, etag: 'etag', metadata: {},
} satisfies ArtifactDescriptor;
const revision = {
  revisionId: 'revision-1', artifactId: artifact.artifactId, parentRevisionId: null, baseRevisionId: null,
  revisionNumber: 1, schemaVersion: 1, mutationType: 'create', contentRelpath: 'form.json', contentSha256: 'a'.repeat(64),
  contentSizeBytes: 1, contentEncoding: 'json', changeSummary: 'Created', authorType: 'user', authorId: 'user-1',
  idempotencyKey: 'create-1', createdAtUtc: '2026-07-16T08:00:00Z',
} satisfies ArtifactRevision;

describe('exportStructuredArtifact', () => {
  it('exports the exact in-memory form submission as deterministic CSV', async () => {
    const commitExport = vi.fn().mockResolvedValue({ basename: 'Intake.csv', sha256: 'b'.repeat(64), sizeBytes: 20 });
    const bridge = {
      beginExport: vi.fn().mockResolvedValue({ cancelled: false, ticket: 'ticket-1', maxBytes: 1024 }),
      commitExport,
      cancelExport: vi.fn(),
    } as unknown as ArtifactBridge;
    await exportStructuredArtifact({
      artifact, revision,
      content: { kind: 'form', schemaVersion: 1, schema: { type: 'object' }, uiSchema: {}, submissionPolicy: { persistence: 'none' } },
      format: 'csv', submission: { name: 'Ada', note: 'a,b' }, bridge,
    });
    expect(bridge.beginExport).toHaveBeenCalledWith(expect.objectContaining({ format: 'csv' }));
    expect(new TextDecoder().decode(commitExport.mock.calls[0][1])).toBe('"name","note"\r\n"Ada","a,b"\r\n');
  });

  it('neutralizes every spreadsheet formula prefix in form CSV values', async () => {
    const commitExport = vi.fn().mockResolvedValue({ basename: 'Intake.csv', sha256: 'b'.repeat(64), sizeBytes: 20 });
    const bridge = {
      beginExport: vi.fn().mockResolvedValue({ cancelled: false, ticket: 'ticket-1', maxBytes: 4096 }),
      commitExport,
      cancelExport: vi.fn(),
    } as unknown as ArtifactBridge;
    await exportStructuredArtifact({
      artifact, revision,
      content: { kind: 'form', schemaVersion: 1, schema: { type: 'object' }, uiSchema: {}, submissionPolicy: { persistence: 'none' } },
      format: 'csv',
      submission: { at: '@SUM(A1:A2)', equals: '=1+1', minus: '-2+3', plus: '+cmd', whitespace: ' \n=HYPERLINK("x")' },
      bridge,
    });

    const csv = new TextDecoder().decode(commitExport.mock.calls[0][1]);
    expect(csv).toContain('"\'@SUM(A1:A2)"');
    expect(csv).toContain('"\'=1+1"');
    expect(csv).toContain('"\'-2+3"');
    expect(csv).toContain('"\'+cmd"');
    expect(csv).toContain('"\' \n=HYPERLINK(""x"")"');
  });
});
