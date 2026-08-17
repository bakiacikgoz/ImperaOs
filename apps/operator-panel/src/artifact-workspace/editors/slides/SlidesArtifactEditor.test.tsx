import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type { ArtifactDescriptor, ArtifactRevision } from '../../artifactContracts';
import { SlidesArtifactEditor } from './SlidesArtifactEditor';

const artifact = {
  artifactId: 'slides-1', workspaceId: 'workspace-1', kind: 'slides', title: 'Deck', status: 'active',
  schemaVersion: 2, dataClass: 'internal', currentRevisionId: 'revision-1', currentRevisionNumber: 1,
  sourceSessionId: null, sourceTurnId: null, createdByType: 'user', createdById: 'user-1',
  updatedById: 'user-1', createdAtUtc: '2026-07-16T08:00:00Z', updatedAtUtc: '2026-07-16T08:00:00Z',
  archivedAtUtc: null, etag: 'etag', metadata: {},
} satisfies ArtifactDescriptor;
const revision = {
  revisionId: 'revision-1', artifactId: artifact.artifactId, parentRevisionId: null, baseRevisionId: null,
  revisionNumber: 1, schemaVersion: 2, mutationType: 'create', contentRelpath: 'slides.json',
  contentSha256: 'a'.repeat(64), contentSizeBytes: 100, contentEncoding: 'json', changeSummary: 'Created',
  authorType: 'user', authorId: 'user-1', idempotencyKey: 'create-1', createdAtUtc: '2026-07-16T08:00:00Z',
} satisfies ArtifactRevision;
const content = {
  kind: 'slides' as const, schemaVersion: 2 as const,
  theme: { name: 'ImperaOS', backgroundColor: 'FFFFFF', foregroundColor: '172033', accentColor: '6E57FF' },
  slides: [{ id: 'slide-1', title: 'Overview', elements: [
    {
      id: 'text-1', type: 'text' as const, x: 1, y: 1, width: 5, height: 1,
      text: 'Hello', fontSize: 18, bold: false, color: null,
    },
  ] }], assetIds: [],
};

describe('SlidesArtifactEditor', () => {
  it('offers an accessible navigator, selection, inspector edit, deterministic add, and PPTX export', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const onSelectionChange = vi.fn();
    const onRequestExport = vi.fn();
    const onImportAsset = vi.fn().mockResolvedValue({
      assetId: 'asset-1', workspaceId: 'workspace-1', sha256: 'b'.repeat(64), mediaType: 'image/png',
      sizeBytes: 68, relativePath: 'assets/workspace-1/asset-1', width: 1, height: 1,
      originalName: 'local.png', dataClass: 'internal', createdById: 'user-1', createdAtUtc: '2026-07-16T08:00:00Z',
    });
    render(<SlidesArtifactEditor
      artifact={artifact} revision={revision} content={content} mode="edit" saveState="idle"
      onChange={onChange} onSelectionChange={onSelectionChange} onRequestExport={onRequestExport}
      onImportAsset={onImportAsset}
    />);
    expect(screen.getByRole('navigation', { name: 'Slide navigator' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'text element text-1' }));
    await user.clear(screen.getByLabelText('Text'));
    await user.type(screen.getByLabelText('Text'), 'Updated');
    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ kind: 'slides' }),
      { kind: 'slides', slideId: 'slide-1', elementId: 'text-1' },
    );
    await user.click(screen.getByRole('button', { name: 'Add slide' }));
    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ slides: expect.arrayContaining([expect.objectContaining({ id: 'slide-2' })]) }),
      { kind: 'slides', slideId: 'slide-2', elementId: null },
    );
    await user.click(screen.getByRole('button', { name: 'Export PPTX' }));
    expect(onRequestExport).toHaveBeenCalledWith('pptx');
    await user.click(screen.getByRole('button', { name: 'Import local image' }));
    expect(onImportAsset).toHaveBeenCalledOnce();
    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({
        assetIds: ['asset-1'],
        slides: expect.arrayContaining([
          expect.objectContaining({
            elements: expect.arrayContaining([expect.objectContaining({ type: 'image', assetId: 'asset-1' })]),
          }),
        ]),
      }),
      expect.objectContaining({ kind: 'slides', elementId: 'image-1' }),
    );
  });
});
