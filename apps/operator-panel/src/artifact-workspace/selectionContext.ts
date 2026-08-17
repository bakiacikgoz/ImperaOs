import { z } from 'zod';

const boundedId = z.string().regex(/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/);

const DocumentSelectionSchema = z.object({
  kind: z.literal('document'),
  blockIds: z.array(boundedId).min(1).max(100),
}).strict();

const FormSelectionSchema = z.object({
  kind: z.literal('form'),
  fieldPaths: z.array(z.string().regex(/^\/(?:[^/~]|~[01])+(?:\/(?:[^/~]|~[01])+)*/)).min(1).max(100),
}).strict();

const CodeSelectionSchema = z.object({
  kind: z.literal('code'),
  startLineNumber: z.number().int().min(1).max(5_000_000),
  startColumn: z.number().int().min(1).max(1_000_000),
  endLineNumber: z.number().int().min(1).max(5_000_000),
  endColumn: z.number().int().min(1).max(1_000_000),
}).strict().refine((selection) => (
  selection.endLineNumber > selection.startLineNumber
  || (selection.endLineNumber === selection.startLineNumber && selection.endColumn >= selection.startColumn)
), { message: 'Code selection end precedes start.' });

const FlowSelectionSchema = z.object({
  kind: z.literal('flow'),
  nodeIds: z.array(boundedId).max(500),
  edgeIds: z.array(boundedId).max(1_000),
}).strict().refine((selection) => selection.nodeIds.length + selection.edgeIds.length > 0);

function columnNumber(value: string): number {
  return [...value].reduce((total, character) => total * 26 + character.charCodeAt(0) - 64, 0);
}

function isBoundedCellRange(value: string): boolean {
  const match = /^([A-Z]{1,3})([1-9][0-9]{0,6})(?::([A-Z]{1,3})([1-9][0-9]{0,6}))?$/.exec(value);
  if (!match) return false;
  const startColumn = columnNumber(match[1]);
  const startRow = Number(match[2]);
  const endColumn = columnNumber(match[3] ?? match[1]);
  const endRow = Number(match[4] ?? match[2]);
  return startColumn <= endColumn && endColumn <= 16_384 && startRow <= endRow && endRow <= 1_048_576;
}

const SpreadsheetSelectionSchema = z.object({
  kind: z.literal('spreadsheet'),
  sheetId: boundedId,
  ranges: z.array(z.string().refine(isBoundedCellRange)).min(1).max(100),
}).strict();

const CanvasSelectionSchema = z.object({
  kind: z.literal('canvas'),
  objectIds: z.array(boundedId).min(1).max(500),
}).strict();

const SlidesSelectionSchema = z.object({
  kind: z.literal('slides'),
  slideId: boundedId,
  elementId: boundedId.nullable(),
}).strict();

export const ArtifactContextSelectionSchema = z.discriminatedUnion('kind', [
  DocumentSelectionSchema,
  FormSelectionSchema,
  CodeSelectionSchema,
  FlowSelectionSchema,
  SpreadsheetSelectionSchema,
  CanvasSelectionSchema,
  SlidesSelectionSchema,
]);

export type ArtifactContextSelection = z.infer<typeof ArtifactContextSelectionSchema>;

export function contextSelectionLabel(selection: ArtifactContextSelection | null): string {
  if (!selection) return 'No editor selection';
  switch (selection.kind) {
    case 'document': return `${selection.blockIds.length} document blocks selected`;
    case 'form': return `${selection.fieldPaths.length} form fields selected`;
    case 'code': return selection.startLineNumber === selection.endLineNumber
      ? `Code line ${selection.startLineNumber}`
      : `Code lines ${selection.startLineNumber}–${selection.endLineNumber}`;
    case 'flow': return `${selection.nodeIds.length} flow nodes, ${selection.edgeIds.length} flow edges selected`;
    case 'spreadsheet': return `${selection.ranges.length} ranges selected on ${selection.sheetId}`;
    case 'canvas': return `${selection.objectIds.length} canvas objects selected`;
    case 'slides': return selection.elementId
      ? `Slide ${selection.slideId}, element ${selection.elementId} selected`
      : `Slide ${selection.slideId} selected`;
  }
}
