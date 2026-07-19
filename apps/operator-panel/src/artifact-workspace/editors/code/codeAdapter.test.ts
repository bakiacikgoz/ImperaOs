import { describe, expect, it } from 'vitest';

import {
  codeModelUri,
  codeSelectionFromMonaco,
  parseCodeArtifactContent,
  serializeCodeArtifactText,
} from './codeAdapter';

const content = {
  kind: 'code' as const,
  schemaVersion: 2 as const,
  filename: 'örnek.ts',
  language: 'typescript' as const,
  text: 'export const safe = true;\r\n',
  lineEnding: 'crlf' as const,
  executionPolicy: 'deny' as const,
};

describe('code artifact adapter', () => {
  it('parses strict content and serializes exact stored text', () => {
    expect(parseCodeArtifactContent(content)).toEqual(content);
    expect(serializeCodeArtifactText(content)).toBe(content.text);
    expect(() => parseCodeArtifactContent({ ...content, language: 'tsx' })).toThrow();
  });

  it('opens compatible legacy v1 content through a fail-closed v2 projection', () => {
    expect(parseCodeArtifactContent({ ...content, schemaVersion: 1 })).toEqual(content);
    expect(() => parseCodeArtifactContent({
      ...content,
      schemaVersion: 1,
      language: 'tsx',
    })).toThrow();
  });

  it('converts only bounded Monaco coordinates', () => {
    expect(codeSelectionFromMonaco({
      startLineNumber: 2,
      startColumn: 3,
      endLineNumber: 4,
      endColumn: 5,
    })).toEqual({
      kind: 'code',
      startLineNumber: 2,
      startColumn: 3,
      endLineNumber: 4,
      endColumn: 5,
    });
    expect(codeSelectionFromMonaco(null)).toBeNull();
    expect(codeSelectionFromMonaco({
      startLineNumber: 0,
      startColumn: 1,
      endLineNumber: 1,
      endColumn: 1,
    })).toBeNull();
  });

  it('builds a stable non-file model URI', () => {
    expect(codeModelUri('artifact-1', content.filename)).toBe(
      'imperaos-artifact://code/artifact-1/%C3%B6rnek.ts',
    );
  });
});
