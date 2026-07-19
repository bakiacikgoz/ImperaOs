import ExcelJS from 'exceljs';

import { SpreadsheetArtifactContentSchema, type SpreadsheetArtifactContent } from './artifactContracts';

const CSV_MAX_RECTANGLE_CELLS = 1_000_000;

function csvCell(value: string | number | boolean | null): string {
  if (value === null) return '';
  let text = typeof value === 'boolean' ? (value ? 'true' : 'false') : String(value);
  if (typeof value === 'string' && /^[\t\r\n ]*[=+\-@]/.test(text)) text = `'${text}`;
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

function addressParts(address: string): { column: number; row: number } {
  const match = /^([A-Z]+)([1-9][0-9]*)$/.exec(address);
  if (!match) throw new Error('Invalid spreadsheet address.');
  return {
    column: [...match[1]].reduce((value, character) => value * 26 + character.charCodeAt(0) - 64, 0),
    row: Number(match[2]),
  };
}

function cellAddress(column: number, row: number): string {
  let current = column;
  let letters = '';
  while (current > 0) {
    current -= 1;
    letters = String.fromCharCode(65 + (current % 26)) + letters;
    current = Math.floor(current / 26);
  }
  return `${letters}${row}`;
}

export function serializeSpreadsheetCsv(value: unknown, sheetId: string): Uint8Array {
  const workbook = SpreadsheetArtifactContentSchema.parse(value);
  const sheet = workbook.sheets.find((item) => item.id === sheetId);
  if (!sheet) throw new Error('Selected spreadsheet sheet does not exist.');
  const coordinates = Object.keys(sheet.cells).map(addressParts);
  const maxRow = Math.max(0, ...coordinates.map((item) => item.row));
  const maxColumn = Math.max(0, ...coordinates.map((item) => item.column));
  if (maxRow > 0 && maxColumn > Math.floor(CSV_MAX_RECTANGLE_CELLS / maxRow)) {
    throw new Error('CSV used range exceeds the bounded export limit.');
  }
  const rows = Array.from({ length: maxRow }, (_, rowIndex) => (
    Array.from({ length: maxColumn }, (_, columnIndex) => {
      const cell = sheet.cells[cellAddress(columnIndex + 1, rowIndex + 1)];
      return csvCell(cell?.value ?? null);
    }).join(',')
  ));
  return new TextEncoder().encode(`${rows.join('\r\n')}${rows.length ? '\r\n' : ''}`);
}

function safeSheetName(name: string, used: Set<string>): string {
  const base = name
    .replaceAll('[', '_')
    .replaceAll(']', '_')
    .replace(/[:*?/\\]/g, '_')
    .replace(/^'+|'+$/g, '')
    .trim()
    .slice(0, 31) || 'Sheet';
  let candidate = base;
  let suffix = 2;
  while (used.has(candidate.toLocaleLowerCase('en-US'))) {
    const marker = ` (${suffix})`;
    candidate = `${base.slice(0, 31 - marker.length)}${marker}`;
    suffix += 1;
  }
  used.add(candidate.toLocaleLowerCase('en-US'));
  return candidate;
}

export async function serializeSpreadsheetXlsx(value: unknown): Promise<Uint8Array> {
  const content = SpreadsheetArtifactContentSchema.parse(value);
  const workbook = new ExcelJS.Workbook();
  workbook.creator = 'ImperaOS';
  workbook.created = new Date('2000-01-01T00:00:00Z');
  workbook.modified = new Date('2000-01-01T00:00:00Z');
  workbook.calcProperties.fullCalcOnLoad = false;
  const usedNames = new Set<string>();
  content.sheets.forEach((source) => {
    const sheet = workbook.addWorksheet(safeSheetName(source.name, usedNames));
    source.columns.forEach((column) => {
      sheet.getColumn(column.index).width = column.width / 8;
      sheet.getColumn(column.index).hidden = column.hidden;
    });
    Object.entries(source.cells).forEach(([address, cell]) => {
      sheet.getCell(address).value = cell.value;
    });
  });
  const buffer = await workbook.xlsx.writeBuffer({ useStyles: false, useSharedStrings: true });
  return new Uint8Array(buffer);
}

export type SpreadsheetSerializeRequest = {
  content: SpreadsheetArtifactContent;
  format: 'csv' | 'xlsx';
  sheetId?: string;
};
