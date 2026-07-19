import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type { ArtifactDescriptor, ArtifactRevision } from '../../artifactContracts';
import { CanvasArtifactEditor } from './CanvasArtifactEditor';

const artifact = {
  artifactId: 'canvas-1', workspaceId: 'workspace-1', kind: 'canvas', title: 'Board', status: 'active',
  schemaVersion: 2, dataClass: 'internal', currentRevisionId: 'revision-1', currentRevisionNumber: 1,
  sourceSessionId: null, sourceTurnId: null, createdByType: 'user', createdById: 'user-1',
  updatedById: 'user-1', createdAtUtc: '2026-07-16T08:00:00Z', updatedAtUtc: '2026-07-16T08:00:00Z',
  archivedAtUtc: null, etag: 'etag', metadata: {},
} satisfies ArtifactDescriptor;
const revision = {
  revisionId: 'revision-1', artifactId: artifact.artifactId, parentRevisionId: null, baseRevisionId: null,
  revisionNumber: 1, schemaVersion: 2, mutationType: 'create', contentRelpath: 'canvas.json',
  contentSha256: 'a'.repeat(64), contentSizeBytes: 100, contentEncoding: 'json', changeSummary: 'Created',
  authorType: 'user', authorId: 'user-1', idempotencyKey: 'create-1', createdAtUtc: '2026-07-16T08:00:00Z',
} satisfies ArtifactRevision;
const content = {
  kind: 'canvas' as const, schemaVersion: 2 as const,
  snapshot: { objects: [{ id: 'note-1', type: 'note' as const, x: 10, y: 20, width: 200, height: 100, text: 'Local note' }] },
  assetIds: [], embeds: 'deny' as const, remoteAssets: 'deny' as const,
};

describe('CanvasArtifactEditor', () => {
  it('provides local-only shape editing, multiselection, history, outline, and safe exports', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const onSelectionChange = vi.fn();
    const onRequestExport = vi.fn();
    const onImportAsset = vi.fn().mockResolvedValue({ assetId: 'asset-1' });
    render(<CanvasArtifactEditor
      artifact={artifact} revision={revision} content={content} mode="edit" saveState="idle"
      onChange={onChange} onSelectionChange={onSelectionChange} onRequestExport={onRequestExport}
      onImportAsset={onImportAsset}
    />);

    expect(screen.getByRole('navigation', { name: 'Canvas outline' })).toHaveTextContent('Local note');
    await user.click(screen.getByRole('button', { name: 'Add rectangle' }));
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({
      snapshot: { objects: expect.arrayContaining([expect.objectContaining({ type: 'rectangle' })]) },
    }), expect.objectContaining({ kind: 'canvas' }));
    await user.click(screen.getByRole('button', { name: 'Free draw' }));
    fireEvent.pointerDown(screen.getByLabelText('Canvas stage'), { clientX: 80, clientY: 90 });
    fireEvent.pointerMove(screen.getByLabelText('Canvas stage'), { clientX: 100, clientY: 110 });
    fireEvent.pointerMove(screen.getByLabelText('Canvas stage'), { clientX: 130, clientY: 125 });
    fireEvent.pointerUp(screen.getByLabelText('Canvas stage'));
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({
      snapshot: { objects: expect.arrayContaining([expect.objectContaining({ type: 'line' })]) },
    }), expect.objectContaining({ kind: 'canvas' }));
    await user.click(screen.getByRole('button', { name: 'Import local image' }));
    expect(onImportAsset).toHaveBeenCalledOnce();
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({
      assetIds: ['asset-1'],
      snapshot: { objects: expect.arrayContaining([expect.objectContaining({ type: 'image', assetId: 'asset-1' })]) },
    }), expect.anything());

    await user.click(screen.getByRole('button', { name: 'Select note-1 from outline' }));
    fireEvent.click(screen.getByRole('button', { name: 'Select rectangle-1 from outline' }), { shiftKey: true });
    expect(onSelectionChange).toHaveBeenLastCalledWith({ kind: 'canvas', objectIds: ['note-1', 'rectangle-1'] });
    await user.click(screen.getByRole('button', { name: 'Undo' }));
    await user.click(screen.getByRole('button', { name: 'Redo' }));
    await user.click(screen.getByRole('button', { name: 'Export SVG' }));
    expect(onRequestExport).toHaveBeenCalledWith('svg');
    await user.click(screen.getByRole('button', { name: 'Export PNG' }));
    expect(onRequestExport).toHaveBeenCalledWith('png');
    expect(screen.queryByText(/https?:\/\//i)).not.toBeInTheDocument();

    fireEvent.pointerDown(within(screen.getByLabelText('Canvas stage')).getByLabelText('note note-1'), { clientX: 10, clientY: 20 });
    fireEvent.pointerMove(screen.getByLabelText('Canvas stage'), { clientX: 40, clientY: 50 });
    fireEvent.pointerUp(screen.getByLabelText('Canvas stage'));
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({
      snapshot: { objects: expect.arrayContaining([expect.objectContaining({ id: 'note-1', x: 40, y: 50 })]) },
    }), expect.anything());
    await user.click(screen.getByRole('button', { name: 'Delete selection' }));
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({
      snapshot: { objects: expect.not.arrayContaining([expect.objectContaining({ id: 'note-1' })]) },
    }), undefined);
  });

  it('disables mutations for view and archived artifacts while retaining outline and export access', () => {
    render(<CanvasArtifactEditor
      artifact={{ ...artifact, status: 'archived' }} revision={revision} content={content} mode="view" saveState="idle"
      onChange={vi.fn()} onSelectionChange={vi.fn()} onRequestExport={vi.fn()}
    />);
    expect(screen.getByRole('button', { name: 'Add rectangle' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Undo' })).toBeDisabled();
    expect(screen.getByRole('navigation', { name: 'Canvas outline' })).toHaveTextContent('Local note');
    expect(screen.getByRole('button', { name: 'Export JSON' })).toBeEnabled();
  });

  it('renders a resolved governed local image instead of an asset-id placeholder', async () => {
    const onResolveAsset = vi.fn().mockResolvedValueOnce({
      asset: { assetId: 'asset-1', workspaceId: artifact.workspaceId, sha256: 'b'.repeat(64), mediaType: 'image/png', sizeBytes: 4, relativePath: 'assets/a.png', width: 1, height: 1, originalName: 'a.png', dataClass: 'internal', createdById: 'user-1', createdAtUtc: '2026-07-16T08:00:00Z' },
      contentBase64: 'iVBORw0KGgo=',
    });
    const imageContent = { ...content, snapshot: { objects: [{ id: 'image-1', type: 'image' as const, x: 0, y: 0, width: 40, height: 30, assetId: 'asset-1' }] }, assetIds: ['asset-1'] };
    const view = render(<CanvasArtifactEditor
      artifact={artifact} revision={revision} mode="view" saveState="idle"
      content={imageContent}
      onChange={vi.fn()} onSelectionChange={vi.fn()} onRequestExport={vi.fn()} onResolveAsset={onResolveAsset}
    />);

    expect(await screen.findByRole('img', { name: 'Local asset asset-1' })).toHaveAttribute('src', 'data:image/png;base64,iVBORw0KGgo=');
    expect(onResolveAsset).toHaveBeenCalledWith('asset-1');

    onResolveAsset.mockResolvedValueOnce({
      asset: { assetId: 'asset-1', workspaceId: 'workspace-2', sha256: 'c'.repeat(64), mediaType: 'image/png', sizeBytes: 4, relativePath: 'assets/b.png', width: 1, height: 1, originalName: 'b.png', dataClass: 'internal', createdById: 'user-1', createdAtUtc: '2026-07-16T08:00:00Z' },
      contentBase64: 'd29ya3NwYWNlLTI=',
    });
    view.rerender(<CanvasArtifactEditor
      artifact={{ ...artifact, workspaceId: 'workspace-2' }} revision={revision} mode="view" saveState="idle"
      content={imageContent}
      onChange={vi.fn()} onSelectionChange={vi.fn()} onRequestExport={vi.fn()} onResolveAsset={onResolveAsset}
    />);
    expect(screen.queryByRole('img', { name: 'Local asset asset-1' })).not.toBeInTheDocument();
    expect(await screen.findByRole('img', { name: 'Local asset asset-1' })).toHaveAttribute('src', 'data:image/png;base64,d29ya3NwYWNlLTI=');
  });

  it('bounds visible image loading concurrency, count, and repeat resolution', async () => {
    let activeLoads = 0;
    let maximumActiveLoads = 0;
    const onResolveAsset = vi.fn().mockImplementation(async (assetId: string) => {
      activeLoads += 1;
      maximumActiveLoads = Math.max(maximumActiveLoads, activeLoads);
      await new Promise((resolve) => setTimeout(resolve, 1));
      activeLoads -= 1;
      return {
        asset: { assetId, workspaceId: artifact.workspaceId, sha256: 'b'.repeat(64), mediaType: 'image/png', sizeBytes: 4, relativePath: `assets/${assetId}.png`, width: 1, height: 1, originalName: `${assetId}.png`, dataClass: 'internal', createdById: 'user-1', createdAtUtc: '2026-07-16T08:00:00Z' },
        contentBase64: 'iVBORw0KGgo=',
      };
    });
    const assetIds = Array.from({ length: 40 }, (_, index) => `asset-${index + 1}`);
    const imageContent = {
      ...content,
      snapshot: { objects: assetIds.map((assetId, index) => ({
        id: `image-${index + 1}`, type: 'image' as const, x: 10, y: 10,
        width: 40, height: 30, assetId,
      })) },
      assetIds,
    };
    const view = render(<CanvasArtifactEditor
      artifact={artifact} revision={revision} mode="view" saveState="idle" content={imageContent}
      onChange={vi.fn()} onSelectionChange={vi.fn()} onRequestExport={vi.fn()} onResolveAsset={onResolveAsset}
    />);

    expect(await screen.findByText('8 visible image(s) were deferred to keep local display memory bounded.')).toBeVisible();
    await waitFor(() => expect(onResolveAsset).toHaveBeenCalledTimes(32));
    expect(maximumActiveLoads).toBeLessThanOrEqual(4);

    view.rerender(<CanvasArtifactEditor
      artifact={artifact} revision={revision} mode="view" saveState="idle"
      content={{ ...imageContent, snapshot: { objects: imageContent.snapshot.objects.map((object) => ({ ...object, width: 41 })) } }}
      onChange={vi.fn()} onSelectionChange={vi.fn()} onRequestExport={vi.fn()} onResolveAsset={onResolveAsset}
    />);
    await waitFor(() => expect(screen.getAllByRole('img')).toHaveLength(32));
    expect(onResolveAsset).toHaveBeenCalledTimes(32);
  });
});
