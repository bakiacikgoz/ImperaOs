import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type { ArtifactDescriptor, ArtifactRevision } from '../../artifactContracts';
import { SpreadsheetArtifactEditor } from './SpreadsheetArtifactEditor';

const artifact = {
  artifactId: 'sheet-1', workspaceId: 'workspace-1', kind: 'spreadsheet', title: 'Budget', status: 'active',
  schemaVersion: 1, dataClass: 'internal', currentRevisionId: 'revision-1', currentRevisionNumber: 1,
  sourceSessionId: null, sourceTurnId: null, createdByType: 'user', createdById: 'user-1', updatedById: 'user-1',
  createdAtUtc: '2026-07-16T08:00:00Z', updatedAtUtc: '2026-07-16T08:00:00Z', archivedAtUtc: null, etag: 'etag', metadata: {},
} satisfies ArtifactDescriptor;
const revision = {
  revisionId: 'revision-1', artifactId: artifact.artifactId, parentRevisionId: null, baseRevisionId: null,
  revisionNumber: 1, schemaVersion: 1, mutationType: 'create', contentRelpath: 'sheet.json', contentSha256: 'a'.repeat(64),
  contentSizeBytes: 100, contentEncoding: 'json', changeSummary: 'Created', authorType: 'user', authorId: 'user-1',
  idempotencyKey: 'create-1', createdAtUtc: '2026-07-16T08:00:00Z',
} satisfies ArtifactRevision;

describe('SpreadsheetArtifactEditor', () => {
  it('selects ranges, copies and clears them, and reports the range to the assistant', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const onSelectionChange = vi.fn();
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { readText: vi.fn(), writeText: vi.fn() } });
    render(<SpreadsheetArtifactEditor artifact={artifact} revision={revision} mode="edit" saveState="idle"
      content={{ kind: 'spreadsheet', schemaVersion: 2, calculationMode: 'disabled', sheets: [{ id: 'sheet-a', name: 'Sheet A', cells: { A1: { value: 'a' }, B1: { value: 'b' }, A2: { value: 'c' }, B2: { value: 'd' } }, columns: [] }] }}
      onChange={onChange} onSelectionChange={onSelectionChange} onRequestExport={vi.fn()} />);

    await user.click(screen.getByLabelText('A1'));
    fireEvent.click(screen.getByLabelText('B2'), { shiftKey: true });
    expect(onSelectionChange).toHaveBeenLastCalledWith({ kind: 'spreadsheet', sheetId: 'sheet-a', ranges: ['A1:B2'] });
    await user.click(screen.getByRole('button', { name: 'Copy cells' }));
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('a\tb\nc\td');
    await user.click(screen.getByRole('button', { name: 'Clear cells' }));
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ sheets: [expect.objectContaining({ cells: {} })] }), expect.objectContaining({ ranges: ['A1:B2'] }));
  });

  it('virtualizes large sheets while keeping the final used row reachable', () => {
    const cells = Object.fromEntries(Array.from({ length: 10_000 }, (_, index) => [
      `A${index + 1}`,
      { value: index + 1 },
    ]));
    render(<SpreadsheetArtifactEditor artifact={artifact} revision={revision} mode="edit" saveState="idle"
      content={{ kind: 'spreadsheet', schemaVersion: 2, calculationMode: 'disabled', sheets: [{ id: 'sheet-a', name: 'Sheet A', cells, columns: [] }] }}
      onChange={vi.fn()} onSelectionChange={vi.fn()} onRequestExport={vi.fn()} />);

    const grid = screen.getByRole('grid', { name: 'Sheet A cells' });
    expect(screen.getAllByRole('gridcell')).toHaveLength(40 * 12);
    fireEvent.scroll(grid, { target: { scrollTop: 9_999 * 32 } });
    expect(screen.getByLabelText('A10000')).toHaveValue('10000');
    expect(screen.getAllByRole('gridcell')).toHaveLength(40 * 12);
    fireEvent.click(screen.getByLabelText('L10000'), { shiftKey: true });
    expect(screen.getByRole('button', { name: 'Clear cells' })).toBeDisabled();
    expect(screen.getByRole('alert')).toHaveTextContent('10,000 cells');
  });
});
