import type { ArtifactDescriptor } from './artifactContracts';
import type { ArtifactExportChoice } from './ui/ArtifactExportDialog';

export type ArtifactExportFormat =
  | 'source' | 'txt' | 'json' | 'submission-json' | 'markdown' | 'html'
  | 'svg' | 'png' | 'csv' | 'xlsx' | 'pptx';

export const ARTIFACT_EXPORT_FORMATS: Record<ArtifactDescriptor['kind'], ArtifactExportChoice[]> = {
  document: [
    { value: 'json', label: 'JSON' },
    { value: 'markdown', label: 'Markdown' },
    { value: 'html', label: 'HTML' },
  ],
  form: [
    { value: 'json', label: 'Schema JSON' },
    { value: 'submission-json', label: 'Submission JSON' },
    { value: 'csv', label: 'Submission CSV' },
  ],
  code: [{ value: 'source', label: 'Source' }, { value: 'txt', label: 'TXT' }],
  flow: [{ value: 'json', label: 'JSON' }, { value: 'svg', label: 'SVG' }, { value: 'png', label: 'PNG' }],
  spreadsheet: [{ value: 'csv', label: 'CSV' }, { value: 'xlsx', label: 'Excel workbook' }],
  canvas: [{ value: 'json', label: 'JSON' }, { value: 'svg', label: 'SVG' }, { value: 'png', label: 'PNG' }],
  slides: [{ value: 'pptx', label: 'PowerPoint' }, { value: 'json', label: 'JSON' }],
};

const EXTENSIONS: Record<ArtifactExportFormat, string> = {
  source: 'txt', txt: 'txt', json: 'json', 'submission-json': 'submission.json', markdown: 'md', html: 'html',
  svg: 'svg', png: 'png', csv: 'csv', xlsx: 'xlsx', pptx: 'pptx',
};

export function suggestedArtifactExportFilename(title: string, format: ArtifactExportFormat): string {
  const base = title.replace(/[^\p{L}\p{N} ._-]+/gu, '_').trim().slice(0, 120) || 'artifact';
  return `${base}.${EXTENSIONS[format]}`;
}
