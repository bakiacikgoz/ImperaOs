import ExcelJS from 'exceljs';
import { describe, expect, it, vi } from 'vitest';

import type { ArtifactBridge } from './artifactBridge';
import { exportSpreadsheetArtifact } from './artifactSpreadsheetExport';
import type { ArtifactDescriptor, ArtifactRevision, SpreadsheetArtifactContent } from './artifactContracts';
import { serializeSpreadsheetCsv, serializeSpreadsheetXlsx } from './spreadsheetSerializer';

const content = {
  kind: 'spreadsheet', schemaVersion: 2, calculationMode: 'disabled',
  sheets: [{
    id: 'sheet-1', name: 'Unsafe/Name', columns: [],
    cells: {
      A1: { value: '=1+1' }, B1: { value: '+cmd' }, C1: { value: 42 }, D1: { value: true },
      A2: { value: 'comma,value' },
    },
  }],
} satisfies SpreadsheetArtifactContent;
const artifact = {
  artifactId: 'spreadsheet-1', workspaceId: 'workspace-1', kind: 'spreadsheet', title: 'Budget',
  status: 'active', schemaVersion: 2, dataClass: 'internal', currentRevisionId: 'revision-2',
  currentRevisionNumber: 2, sourceSessionId: null, sourceTurnId: null, createdByType: 'user',
  createdById: 'user-1', updatedById: 'user-1', createdAtUtc: '2026-07-16T08:00:00Z',
  updatedAtUtc: '2026-07-16T08:01:00Z', archivedAtUtc: null, etag: 'etag', metadata: {},
} satisfies ArtifactDescriptor;
const revision = {
  revisionId: 'revision-2', artifactId: artifact.artifactId, parentRevisionId: 'revision-1',
  baseRevisionId: null, revisionNumber: 2, schemaVersion: 2, mutationType: 'cell_patch',
  contentRelpath: 'content/sheet.json', contentSha256: 'a'.repeat(64), contentSizeBytes: 100,
  contentEncoding: 'json', changeSummary: 'Patch', authorType: 'user', authorId: 'user-1',
  idempotencyKey: 'patch-1', createdAtUtc: '2026-07-16T08:01:00Z',
} satisfies ArtifactRevision;

describe('spreadsheet export', () => {
  it('serializes RFC4180 CSV with formula-prefix defense', () => {
    expect(new TextDecoder().decode(serializeSpreadsheetCsv(content, 'sheet-1'))).toBe(
      "'=1+1,'+cmd,42,true\r\n\"comma,value\",,,\r\n",
    );
    const guarded = {
      ...content,
      sheets: [{ ...content.sheets[0], cells: {
        A1: { value: '\t=1+1' }, B1: { value: '\r@SUM(A1)' }, C1: { value: '  +cmd' },
      } }],
    };
    expect(new TextDecoder().decode(serializeSpreadsheetCsv(guarded, 'sheet-1'))).toBe(
      "'\t=1+1,\"'\r@SUM(A1)\",'  +cmd\r\n",
    );
    expect(() => serializeSpreadsheetCsv({
      ...content,
      sheets: [{ ...content.sheets[0], cells: { XFD1048576: { value: 'sparse' } } }],
    }, 'sheet-1')).toThrow(/bounded export limit/i);
  });

  it('writes XLSX scalar strings without formula cells and sanitizes sheet names', async () => {
    const bytes = await serializeSpreadsheetXlsx(content);
    const workbook = new ExcelJS.Workbook();
    await workbook.xlsx.load(bytes as never);
    const sheet = workbook.worksheets[0];
    expect(sheet.name).toBe('Unsafe_Name');
    expect(sheet.getCell('A1').value).toBe('=1+1');
    expect(sheet.getCell('A1').formula).toBeUndefined();
    expect(sheet.getCell('C1').value).toBe(42);
    expect(sheet.getCell('D1').value).toBe(true);
  });

  it('uses exact revision native ticket and cancels oversized output', async () => {
    const bridge = {
      beginExport: vi.fn().mockResolvedValue({ cancelled: false, ticket: 'ticket-1', maxBytes: 2 }),
      commitExport: vi.fn(),
      cancelExport: vi.fn().mockResolvedValue(undefined),
    } as unknown as ArtifactBridge;
    await expect(exportSpreadsheetArtifact({
      artifact, revision, content, format: 'csv', sheetId: 'sheet-1', bridge,
      serialize: vi.fn().mockResolvedValue(Uint8Array.of(1, 2, 3)),
    })).rejects.toThrow(/size limit/i);
    expect(bridge.beginExport).toHaveBeenCalledWith(expect.objectContaining({
      artifactId: artifact.artifactId, revisionId: revision.revisionId, format: 'csv',
    }));
    expect(bridge.cancelExport).toHaveBeenCalledWith('ticket-1');
  });
});
