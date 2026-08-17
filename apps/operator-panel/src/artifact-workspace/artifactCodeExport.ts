import { artifactBridge as defaultBridge, type ArtifactBridge } from './artifactBridge';
import type { ArtifactContent, ArtifactDescriptor, ArtifactRevision } from './artifactContracts';
import { parseCodeArtifactContent, serializeCodeArtifactText } from './editors/code/codeAdapter';

export type CodeArtifactExportOutcome =
  | { status: 'cancelled' }
  | { status: 'exported'; basename: string; sha256: string; sizeBytes: number; exportId?: string };
export type CodeArtifactExportFormat = 'source' | 'txt';

export async function exportCodeArtifact({
  artifact,
  revision,
  content,
  format = 'source',
  bridge = defaultBridge,
}: {
  artifact: ArtifactDescriptor;
  revision: ArtifactRevision;
  content: ArtifactContent;
  format?: CodeArtifactExportFormat;
  bridge?: ArtifactBridge;
}): Promise<CodeArtifactExportOutcome> {
  if (artifact.kind !== 'code') throw new Error('Only code artifacts may use source export.');
  const parsed = parseCodeArtifactContent(content);
  const bytes = new TextEncoder().encode(serializeCodeArtifactText(parsed));
  const begin = await bridge.beginExport({
    artifactId: artifact.artifactId,
    revisionId: revision.revisionId,
    format,
    idempotencyKey: `export-${artifact.artifactId.slice(0, 48)}-${revision.revisionId.slice(0, 48)}-${globalThis.crypto.randomUUID()}`,
  });
  if (begin.cancelled) return { status: 'cancelled' };
  if (!begin.ticket) throw new Error('Native export did not return a ticket.');
  if (bytes.byteLength > begin.maxBytes) {
    await bridge.cancelExport(begin.ticket).catch(() => undefined);
    throw new Error('Code export exceeds the native size limit.');
  }
  const result = await bridge.commitExport(begin.ticket, bytes);
  return { status: 'exported', ...result, ...(begin.exportId ? { exportId: begin.exportId } : {}) };
}
