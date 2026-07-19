import {
  CodeArtifactContentSchema,
  LegacyCodeArtifactContentSchema,
  type CodeArtifactContent,
} from '../../artifactContracts';

const BOUNDED_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;
const MAX_COORDINATE = 10_000_000;

export type CodeArtifactSelection = {
  kind: 'code';
  startLineNumber: number;
  startColumn: number;
  endLineNumber: number;
  endColumn: number;
};

export type MonacoSelectionLike = Omit<CodeArtifactSelection, 'kind'>;

export function parseCodeArtifactContent(value: unknown): CodeArtifactContent {
  const current = CodeArtifactContentSchema.safeParse(value);
  if (current.success) return current.data;
  const legacy = LegacyCodeArtifactContentSchema.parse(value);
  return CodeArtifactContentSchema.parse({ ...legacy, schemaVersion: 2 });
}

export function serializeCodeArtifactText(value: unknown): string {
  return parseCodeArtifactContent(value).text;
}

export function codeSelectionFromMonaco(
  selection: MonacoSelectionLike | null | undefined,
): CodeArtifactSelection | null {
  if (!selection) return null;
  const coordinates = [
    selection.startLineNumber,
    selection.startColumn,
    selection.endLineNumber,
    selection.endColumn,
  ];
  if (coordinates.some((coordinate) => (
    !Number.isSafeInteger(coordinate) || coordinate < 1 || coordinate > MAX_COORDINATE
  ))) return null;
  if (
    selection.endLineNumber < selection.startLineNumber
    || (
      selection.endLineNumber === selection.startLineNumber
      && selection.endColumn < selection.startColumn
    )
  ) return null;
  return { kind: 'code', ...selection };
}

export function codeModelUri(artifactId: string, filename: string): string {
  if (!BOUNDED_ID.test(artifactId)) throw new Error('Artifact ID is invalid.');
  const parsed = parseCodeArtifactContent({
    kind: 'code',
    schemaVersion: 2,
    filename,
    language: 'plaintext',
    text: '',
    lineEnding: 'lf',
    executionPolicy: 'deny',
  });
  return `imperaos-artifact://code/${encodeURIComponent(artifactId)}/${encodeURIComponent(parsed.filename)}`;
}
