import { artifactBridge as defaultBridge, type ArtifactBridge } from './artifactBridge';
import type { ArtifactContent, ArtifactDescriptor, ArtifactRevision } from './artifactContracts';

export type StructuredArtifactExportFormat = 'json' | 'submission-json' | 'csv';

function csvCell(value: unknown): string {
  let text = value === null || value === undefined
    ? ''
    : typeof value === 'object' ? JSON.stringify(value) : String(value);
  if (typeof value === 'string' && /^[\t\r\n ]*[=+\-@]/.test(text)) text = `'${text}`;
  return `"${text.replaceAll('"', '""')}"`;
}

function serialize(format: StructuredArtifactExportFormat, content: ArtifactContent, submission?: Record<string, unknown>): string {
  if (format === 'json') return `${JSON.stringify(content, null, 2)}\n`;
  const response = submission ?? {};
  if (format === 'submission-json') return `${JSON.stringify(response, null, 2)}\n`;
  const keys = Object.keys(response).sort();
  return `${keys.map(csvCell).join(',')}\r\n${keys.map((key) => csvCell(response[key])).join(',')}\r\n`;
}

export async function exportStructuredArtifact({
  artifact, revision, content, format, submission, bridge = defaultBridge,
}: {
  artifact: ArtifactDescriptor;
  revision: ArtifactRevision;
  content: ArtifactContent;
  format: StructuredArtifactExportFormat;
  submission?: Record<string, unknown>;
  bridge?: ArtifactBridge;
}): Promise<{ status: 'cancelled' } | { status: 'exported'; basename: string; sha256: string; sizeBytes: number; exportId?: string }> {
  if ((format === 'submission-json' || format === 'csv') && artifact.kind !== 'form') {
    throw new Error('Submission exports are only available for form artifacts.');
  }
  const bytes = new TextEncoder().encode(serialize(format, content, submission));
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
    throw new Error('Structured export exceeds the native size limit.');
  }
  return { status: 'exported', ...await bridge.commitExport(begin.ticket, bytes), ...(begin.exportId ? { exportId: begin.exportId } : {}) };
}
