/// <reference lib="webworker" />

import { serializeSpreadsheetCsv, serializeSpreadsheetXlsx, type SpreadsheetSerializeRequest } from './spreadsheetSerializer';

self.onmessage = async (event: MessageEvent<SpreadsheetSerializeRequest>) => {
  try {
    const { content, format, sheetId } = event.data;
    const bytes = format === 'csv'
      ? serializeSpreadsheetCsv(content, sheetId ?? '')
      : await serializeSpreadsheetXlsx(content);
    self.postMessage({ ok: true, bytes }, { transfer: [bytes.buffer] });
  } catch {
    self.postMessage({ ok: false, error: 'Spreadsheet serialization failed safely.' });
  }
};
