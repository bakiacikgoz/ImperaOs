import { useMemo, useState, type MouseEvent } from 'react';

import {
  SpreadsheetArtifactContentSchema,
  type SpreadsheetArtifactContent,
} from '../../artifactContracts';
import type { ArtifactEditorProps } from '../ArtifactEditorHost';

const DEFAULT_COLUMNS = 12;
const DEFAULT_ROWS = 30;
const MAX_ROWS = 1_048_576;
const VISIBLE_ROW_COUNT = 40;
const ROW_HEIGHT_PX = 32;
const MAX_SELECTION_OPERATION_CELLS = 10_000;

function columnLabel(index: number): string {
  let value = index;
  let label = '';
  while (value > 0) {
    value -= 1;
    label = String.fromCharCode(65 + (value % 26)) + label;
    value = Math.floor(value / 26);
  }
  return label;
}

function usedBounds(content: SpreadsheetArtifactContent, sheetIndex: number): { rows: number; columns: number } {
  const sheet = content.sheets[sheetIndex];
  const cells = Object.keys(sheet?.cells ?? {});
  const coordinates = cells.map((address) => {
    const match = /^([A-Z]+)(\d+)$/.exec(address);
    const column = match ? [...match[1]].reduce((sum, letter) => sum * 26 + letter.charCodeAt(0) - 64, 0) : 0;
    return { column, row: match ? Number(match[2]) : 0 };
  });
  return {
    rows: Math.max(DEFAULT_ROWS, ...coordinates.map((item) => item.row)),
    columns: Math.max(DEFAULT_COLUMNS, ...coordinates.map((item) => item.column)),
  };
}

function normalizeValue(raw: string): string | number | boolean | null {
  if (raw === '') return null;
  if (raw === 'true') return true;
  if (raw === 'false') return false;
  const number = Number(raw);
  return Number.isFinite(number) && raw.trim() !== '' ? number : raw;
}

function addressParts(address: string): { column: number; row: number } {
  const match = /^([A-Z]+)(\d+)$/.exec(address);
  if (!match) return { column: 1, row: 1 };
  return {
    column: [...match[1]].reduce((sum, letter) => sum * 26 + letter.charCodeAt(0) - 64, 0),
    row: Number(match[2]),
  };
}

function rangeBetween(start: string, end: string): string {
  const left = addressParts(start);
  const right = addressParts(end);
  const first = `${columnLabel(Math.min(left.column, right.column))}${Math.min(left.row, right.row)}`;
  const last = `${columnLabel(Math.max(left.column, right.column))}${Math.max(left.row, right.row)}`;
  return first === last ? first : `${first}:${last}`;
}

function rangeBounds(range: string): { first: { column: number; row: number }; last: { column: number; row: number } } {
  const [start, end = start] = range.split(':');
  const first = addressParts(start);
  const last = addressParts(end);
  return { first, last };
}

export function SpreadsheetArtifactEditor(props: ArtifactEditorProps) {
  const content = useMemo(() => SpreadsheetArtifactContentSchema.parse(props.content), [props.content]);
  const [activeSheetIndex, setActiveSheetIndex] = useState(0);
  const [selectedAddress, setSelectedAddress] = useState('A1');
  const [selectionAnchor, setSelectionAnchor] = useState('A1');
  const [extraRows, setExtraRows] = useState(0);
  const [extraColumns, setExtraColumns] = useState(0);
  const [visibleRowStart, setVisibleRowStart] = useState(1);
  const activeSheet = content.sheets[activeSheetIndex] ?? content.sheets[0];
  const bounds = usedBounds(content, activeSheetIndex);
  const rows = Math.min(MAX_ROWS, bounds.rows + extraRows);
  const columns = Math.min(100, bounds.columns + extraColumns);
  const editable = props.mode !== 'view' && props.artifact.status !== 'archived';
  const selectedRange = rangeBetween(selectionAnchor, selectedAddress);
  const selectedBounds = rangeBounds(selectedRange);
  const selectedCellCount = (selectedBounds.last.row - selectedBounds.first.row + 1)
    * (selectedBounds.last.column - selectedBounds.first.column + 1);
  const selectionOperationBlocked = selectedCellCount > MAX_SELECTION_OPERATION_CELLS;
  const visibleRows = Array.from(
    { length: Math.min(VISIBLE_ROW_COUNT, rows - visibleRowStart + 1) },
    (_, index) => visibleRowStart + index,
  );

  const update = (next: SpreadsheetArtifactContent, range = selectedRange) => {
    const parsed = SpreadsheetArtifactContentSchema.parse(next);
    props.onChange(parsed, { kind: 'spreadsheet', sheetId: parsed.sheets[activeSheetIndex].id, ranges: [range] });
  };
  const selectAddress = (address: string, extend: boolean) => {
    const anchor = extend ? selectionAnchor : address;
    setSelectionAnchor(anchor);
    setSelectedAddress(address);
    props.onSelectionChange({ kind: 'spreadsheet', sheetId: activeSheet.id, ranges: [rangeBetween(anchor, address)] });
  };
  const copySelection = async () => {
    if (selectionOperationBlocked || !navigator.clipboard?.writeText) return;
    const text = Array.from({ length: selectedBounds.last.row - selectedBounds.first.row + 1 }, (_, rowOffset) =>
      Array.from({ length: selectedBounds.last.column - selectedBounds.first.column + 1 }, (_, columnOffset) => {
        const address = `${columnLabel(selectedBounds.first.column + columnOffset)}${selectedBounds.first.row + rowOffset}`;
        const value = activeSheet.cells[address]?.value;
        return value === undefined || value === null ? '' : String(value);
      }).join('\t'),
    ).join('\n');
    await navigator.clipboard.writeText(text);
  };
  const clearSelection = () => {
    if (!editable || selectionOperationBlocked) return;
    const cells = Object.fromEntries(Object.entries(activeSheet.cells).filter(([address]) => {
      const cell = addressParts(address);
      return cell.row < selectedBounds.first.row || cell.row > selectedBounds.last.row
        || cell.column < selectedBounds.first.column || cell.column > selectedBounds.last.column;
    }));
    update({ ...content, sheets: content.sheets.map((sheet, index) => index === activeSheetIndex ? { ...sheet, cells } : sheet) });
  };
  const updateCell = (address: string, raw: string) => {
    if (!editable) return;
    const value = normalizeValue(raw);
    const sheets = content.sheets.map((sheet, index) => index === activeSheetIndex ? {
      ...sheet,
      cells: value === null
        ? Object.fromEntries(Object.entries(sheet.cells).filter(([key]) => key !== address))
        : { ...sheet.cells, [address]: { value } },
    } : sheet);
    update({ ...content, sheets }, address);
  };
  const addSheet = () => {
    if (!editable) return;
    const index = content.sheets.length + 1;
    const id = `sheet-${index}`;
    update({ ...content, sheets: [...content.sheets, { id, name: `Sheet ${index}`, cells: {}, columns: [] }] });
    setActiveSheetIndex(content.sheets.length);
    setSelectedAddress('A1');
  };
  const renameSheet = () => {
    if (!editable) return;
    const proposed = globalThis.prompt('Sheet name', activeSheet.name)?.trim();
    if (!proposed) return;
    update({ ...content, sheets: content.sheets.map((sheet, index) => index === activeSheetIndex ? { ...sheet, name: proposed.slice(0, 100) } : sheet) });
  };
  const pasteSelection = async () => {
    if (!editable || !navigator.clipboard?.readText) return;
    const text = await navigator.clipboard.readText();
    const start = /^([A-Z]+)(\d+)$/.exec(selectedAddress);
    if (!start) return;
    const startColumn = [...start[1]].reduce((sum, letter) => sum * 26 + letter.charCodeAt(0) - 64, 0);
    const startRow = Number(start[2]);
    const nextCells = { ...activeSheet.cells };
    text.replaceAll('\r\n', '\n').split('\n').slice(0, 100).forEach((line, rowOffset) => {
      line.split('\t').slice(0, 100).forEach((cell, columnOffset) => {
        const address = `${columnLabel(startColumn + columnOffset)}${startRow + rowOffset}`;
        const value = normalizeValue(cell);
        if (value === null) delete nextCells[address];
        else nextCells[address] = { value };
      });
    });
    update({ ...content, sheets: content.sheets.map((sheet, index) => index === activeSheetIndex ? { ...sheet, cells: nextCells } : sheet) });
  };

  return <section className="spreadsheet-artifact-editor" aria-label={`Spreadsheet editor: ${props.artifact.title}`}>
    <header>
      <strong>{props.artifact.title}</strong>
      <span role="status">{props.saveState === 'saving' ? 'Saving spreadsheet…' : editable ? 'Formula evaluation is disabled.' : 'Read-only spreadsheet'}</span>
    </header>
    <div role="toolbar" aria-label="Spreadsheet tools">
      <button type="button" disabled={!editable} onClick={addSheet}>Add sheet</button>
      <button type="button" disabled={!editable} onClick={renameSheet}>Rename sheet</button>
      <button type="button" disabled={!editable || !navigator.clipboard?.readText} data-disabled-reason={!editable ? 'Spreadsheet is read-only.' : !navigator.clipboard?.readText ? 'Clipboard access is unavailable.' : undefined} onClick={() => void pasteSelection()}>Paste cells</button>
      <button type="button" disabled={selectionOperationBlocked || !navigator.clipboard?.writeText} onClick={() => void copySelection()}>Copy cells</button>
      <button type="button" disabled={!editable || selectionOperationBlocked} onClick={clearSelection}>Clear cells</button>
      <button type="button" disabled={selectionOperationBlocked} onClick={() => props.onSelectionChange({ kind: 'spreadsheet', sheetId: activeSheet.id, ranges: [selectedRange] })}>Edit selected cells with AI</button>
      <button type="button" disabled={!editable} onClick={() => setExtraRows((value) => value + 20)}>Add rows</button>
      <button type="button" disabled={!editable} onClick={() => setExtraColumns((value) => value + 4)}>Add columns</button>
      <button type="button" onClick={() => props.onRequestExport('csv')}>Export CSV</button>
      <button type="button" onClick={() => props.onRequestExport('xlsx')}>Export XLSX</button>
    </div>
    <div className="spreadsheet-sheet-tabs" role="tablist" aria-label="Spreadsheet sheets">
      {content.sheets.map((sheet, index) => <button key={sheet.id} type="button" role="tab" aria-selected={index === activeSheetIndex} onClick={() => { setActiveSheetIndex(index); setSelectedAddress('A1'); }}>{sheet.name}</button>)}
    </div>
    <div className="spreadsheet-grid" role="grid" aria-label={`${activeSheet.name} cells`} onScroll={(event) => {
      const next = Math.min(Math.max(1, Math.floor(event.currentTarget.scrollTop / ROW_HEIGHT_PX) + 1), Math.max(1, rows - VISIBLE_ROW_COUNT + 1));
      setVisibleRowStart(next);
    }}>
      <div className="spreadsheet-grid-row spreadsheet-grid-header" role="row"><span role="columnheader">#</span>{Array.from({ length: columns }, (_, index) => <span key={index} role="columnheader">{columnLabel(index + 1)}</span>)}</div>
      <span className="sr-only" aria-live="polite">Visible rows {visibleRowStart}–{Math.min(rows, visibleRowStart + VISIBLE_ROW_COUNT - 1)} of {rows}</span>
      {visibleRowStart > 1 ? <div aria-hidden="true" style={{ height: (visibleRowStart - 1) * ROW_HEIGHT_PX }} /> : null}
      {visibleRows.map((row) => {
        return <div key={row} className="spreadsheet-grid-row" role="row"><span role="rowheader">{row}</span>{Array.from({ length: columns }, (_, columnIndex) => {
          const address = `${columnLabel(columnIndex + 1)}${row}`;
          const value = activeSheet.cells[address]?.value;
          return <input key={address} aria-label={address} role="gridcell" readOnly={!editable} value={value === undefined || value === null ? '' : String(value)} onFocus={() => selectAddress(address, false)} onClick={(event: MouseEvent<HTMLInputElement>) => selectAddress(address, event.shiftKey)} onChange={(event) => updateCell(address, event.target.value)} />;
        })}</div>;
      })}
      {visibleRowStart + visibleRows.length <= rows ? <div aria-hidden="true" style={{ height: (rows - visibleRowStart - visibleRows.length + 1) * ROW_HEIGHT_PX }} /> : null}
    </div>
    {selectionOperationBlocked ? <p role="alert">Selection operations are limited to 10,000 cells. Select a smaller range.</p> : null}
    <footer>Sheet: {activeSheet.name} · Selection: {selectedRange} · {Object.keys(activeSheet.cells).length} filled cells · Revision {props.revision.revisionNumber} · {editable ? 'Edit' : 'Read-only'} · Formula disabled</footer>
  </section>;
}
