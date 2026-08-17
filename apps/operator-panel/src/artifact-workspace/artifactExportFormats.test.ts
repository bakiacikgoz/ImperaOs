import { describe, expect, it } from 'vitest';

import { ARTIFACT_EXPORT_FORMATS, suggestedArtifactExportFilename } from './artifactExportFormats';

describe('artifact export format matrix', () => {
  it('declares the exact seven-kind release matrix', () => {
    expect(Object.fromEntries(Object.entries(ARTIFACT_EXPORT_FORMATS).map(([kind, formats]) => [kind, formats.map(({ value }) => value)]))).toEqual({
      document: ['json', 'markdown', 'html'],
      form: ['json', 'submission-json', 'csv'],
      code: ['source', 'txt'],
      flow: ['json', 'svg', 'png'],
      spreadsheet: ['csv', 'xlsx'],
      canvas: ['json', 'svg', 'png'],
      slides: ['pptx', 'json'],
    });
    expect(suggestedArtifactExportFilename('Quarter / Plan', 'submission-json')).toBe('Quarter _ Plan.submission.json');
  });
});
