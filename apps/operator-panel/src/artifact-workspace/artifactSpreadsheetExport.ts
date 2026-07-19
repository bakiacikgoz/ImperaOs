import SpreadsheetExportWorker from './spreadsheetExport.worker?worker';
import { artifactBridge as defaultBridge, type ArtifactBridge } from './artifactBridge';
import { SpreadsheetArtifactContentSchema, type ArtifactContent, type ArtifactDescriptor, type ArtifactRevision } from './artifactContracts';
import type { SpreadsheetSerializeRequest } from './spreadsheetSerializer';

export type SpreadsheetExportFormat = 'csv' | 'xlsx';
type Outcome = { status: 'cancelled' } | { status: 'exported'; basename: string; sha256: string; sizeBytes: number; exportId?: string };

export function serializeSpreadsheetInWorker(request: SpreadsheetSerializeRequest): Promise<Uint8Array> {
  return new Promise((resolve, reject) => {
    const worker = new SpreadsheetExportWorker();
    worker.onmessage = (event: MessageEvent<{ ok: boolean; bytes?: Uint8Array; error?: string }>) => {
      worker.terminate();
      if (event.data.ok && event.data.bytes) resolve(new Uint8Array(event.data.bytes));
      else reject(new Error(event.data.error ?? 'Spreadsheet serialization failed safely.'));
    };
    worker.onerror = () => {
      worker.terminate();
      reject(new Error('Spreadsheet export worker failed safely.'));
    };
    worker.postMessage(request);
  });
}

export async function exportSpreadsheetArtifact({
  artifact, revision, content, format, sheetId, bridge = defaultBridge,
  serialize = serializeSpreadsheetInWorker,
}: {
  artifact: ArtifactDescriptor;
  revision: ArtifactRevision;
  content: ArtifactContent;
  format: SpreadsheetExportFormat;
  sheetId?: string;
  bridge?: ArtifactBridge;
  serialize?: (request: SpreadsheetSerializeRequest) => Promise<Uint8Array>;
}): Promise<Outcome> {
  if (artifact.kind !== 'spreadsheet' || artifact.schemaVersion !== 2 || revision.schemaVersion !== 2) {
    throw new Error('Spreadsheet export requires an exact spreadsheet.v2 revision.');
  }
  const parsed = SpreadsheetArtifactContentSchema.parse(content);
  if (format === 'csv' && !sheetId) throw new Error('CSV export requires an explicit sheet selection.');
  const bytes = await serialize({ content: parsed, format, sheetId });
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
    throw new Error('Spreadsheet export exceeds the native size limit.');
  }
  const result = await bridge.commitExport(begin.ticket, bytes);
  return { status: 'exported', ...result, ...(begin.exportId ? { exportId: begin.exportId } : {}) };
}
