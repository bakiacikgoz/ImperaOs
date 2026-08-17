import { screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { ArtifactDescriptor, ArtifactRevision } from '../artifactContracts';
import type { ArtifactWorkspaceState } from '../workspaceController';
import { renderOperatorPanel } from '../../test/render';
import { ArtifactWorkspacePanel } from './ArtifactWorkspacePanel';

const descriptor: ArtifactDescriptor = {
  artifactId: 'artifact-document', workspaceId: 'workspace-1', kind: 'document', title: 'Launch plan',
  status: 'archived', schemaVersion: 1, dataClass: 'confidential', currentRevisionId: 'revision-2',
  currentRevisionNumber: 2, sourceSessionId: null, sourceTurnId: null, createdByType: 'assistant',
  createdById: 'assistant-1', updatedById: 'user-1', createdAtUtc: '2026-07-16T08:00:00Z',
  updatedAtUtc: '2026-07-16T09:00:00Z', archivedAtUtc: '2026-07-17T09:00:00Z', etag: 'etag-2',
  metadata: { policyStatus: 'governed', licenseStatus: 'built-in' },
};

const revision: ArtifactRevision = {
  revisionId: 'revision-2', artifactId: descriptor.artifactId, parentRevisionId: 'revision-1', baseRevisionId: 'revision-1',
  revisionNumber: 2, schemaVersion: 1, mutationType: 'replace_content', contentRelpath: 'revision-2.json',
  contentSha256: 'a'.repeat(64), contentSizeBytes: 64, contentEncoding: 'json', changeSummary: 'Updated plan',
  authorType: 'user', authorId: 'user-1', idempotencyKey: 'save-2', createdAtUtc: '2026-07-16T09:00:00Z',
};

const workspaceState: ArtifactWorkspaceState = {
  activeArtifactId: descriptor.artifactId,
  closeGuard: null,
  tabs: [{
    artifact: descriptor,
    revision,
    persistedContent: { kind: 'document', schemaVersion: 1, language: 'en', pageMode: 'document', blocks: [] },
    draftContent: { kind: 'document', schemaVersion: 1, language: 'en', pageMode: 'document', blocks: [] },
    dirty: true,
    saveState: 'error',
    saveError: 'Autosave is offline.',
    conflict: null,
  }],
};

describe('ArtifactWorkspacePanel', () => {
  it('filters the navigator, exposes archived metadata, and retries a failed draft save', async () => {
    const onOpenArtifact = vi.fn();
    const onRetrySave = vi.fn();
    const { user } = renderOperatorPanel(
      <ArtifactWorkspacePanel
        workspaceState={workspaceState}
        catalog={[descriptor, { ...descriptor, artifactId: 'artifact-code', title: 'Policy code', kind: 'code', status: 'active', archivedAtUtc: null }]}
        history={[revision, { ...revision, revisionId: 'revision-1', revisionNumber: 1 }]}
        onOpenArtifact={onOpenArtifact}
        onRetrySave={onRetrySave}
        onRenderEditor={() => <div>Editor slot</div>}
      />,
    );

    await user.type(screen.getByRole('searchbox', { name: 'Search artifacts' }), 'policy');
    await user.click(screen.getByRole('button', { name: /Policy code/ }));
    expect(onOpenArtifact).toHaveBeenCalledWith('artifact-code');
    expect(within(screen.getByLabelText('Artifact status')).getByText('Archived 2026-07-17')).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('Autosave is offline.');
    await user.click(screen.getByRole('button', { name: 'Retry save' }));
    expect(onRetrySave).toHaveBeenCalledWith('artifact-document');
    expect(screen.getByRole('button', { name: 'Restore revision 1' })).toBeDisabled();
  });

  it('opens the common export dialog only for a clean, writable artifact', async () => {
    const onExportArtifact = vi.fn();
    const writableState: ArtifactWorkspaceState = {
      ...workspaceState,
      tabs: [{ ...workspaceState.tabs[0], artifact: { ...descriptor, status: 'active', archivedAtUtc: null }, dirty: false, saveState: 'saved', saveError: null }],
    };
    const { user } = renderOperatorPanel(
      <ArtifactWorkspacePanel
        workspaceState={writableState}
        catalog={[writableState.tabs[0].artifact]}
        onExportArtifact={onExportArtifact}
        onRenderEditor={() => <div>Editor slot</div>}
      />,
    );

    await user.click(screen.getByRole('button', { name: 'Export' }));
    await user.selectOptions(screen.getByLabelText('Export format'), 'html');
    await user.click(screen.getByRole('button', { name: 'Choose destination and export' }));
    expect(onExportArtifact).toHaveBeenCalledWith('artifact-document', 'html');
  });
});
