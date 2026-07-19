import { artifactBridge as defaultBridge, type ArtifactBridge } from './artifactBridge';
import type { ArtifactContent, ArtifactDescriptor, ArtifactRevision } from './artifactContracts';
import {
  parseDocumentArtifactContent,
  serializeDocumentToHtml,
  serializeDocumentToMarkdown,
  type DocumentArtifactContent,
} from './editors/document/documentAdapter';

export type DocumentArtifactExportFormat = 'markdown' | 'html';

export type DocumentArtifactExportOutcome =
  | { status: 'cancelled' }
  | { status: 'exported'; basename: string; sha256: string; sizeBytes: number; exportId?: string };

export async function exportDocumentArtifact({
  artifact,
  revision,
  content,
  format,
  bridge = defaultBridge,
}: {
  artifact: ArtifactDescriptor;
  revision: ArtifactRevision;
  content: ArtifactContent | DocumentArtifactContent;
  format: DocumentArtifactExportFormat;
  bridge?: ArtifactBridge;
}): Promise<DocumentArtifactExportOutcome> {
  if (artifact.kind !== 'document') throw new Error('Only document artifacts may use document export.');
  const parsed = parseDocumentArtifactContent(content);
  const serialized = format === 'markdown'
    ? serializeDocumentToMarkdown(parsed)
    : serializeDocumentToHtml(parsed);
  const bytes = new TextEncoder().encode(serialized);
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
    throw new Error('Document export exceeds the native size limit.');
  }
  const result = await bridge.commitExport(begin.ticket, bytes);
  return { status: 'exported', ...result, ...(begin.exportId ? { exportId: begin.exportId } : {}) };
}
