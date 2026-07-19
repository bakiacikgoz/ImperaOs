import { act, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { getAssistantFixture } from '../../assistant/assistantFixtures';
import type { ArtifactDescriptor, ArtifactRevision } from '../../artifact-workspace/artifactContracts';
import type { ArtifactWorkspaceState } from '../../artifact-workspace/workspaceController';
import { renderOperatorPanel } from '../../test/render';
import { AssistantWorkbench } from './AssistantWorkbench';

describe('AssistantWorkbench', () => {
  it('renders active assistant output and artifact previews', async () => {
    const onSelectArtifact = vi.fn();
    const { user } = renderOperatorPanel(
      <AssistantWorkbench
        state={getAssistantFixture('running')}
        artifacts={[
          { name: 'status.json', summary: 'blocked', value: { status: 'blocked', job_id: 'job-1' } },
          { name: 'tasks.json', summary: '2 tasks', value: { tasks: [{ id: 'task-1' }] } },
        ]}
        selectedArtifactName="status.json"
        onSelectArtifact={onSelectArtifact}
        onViewRuns={vi.fn()}
      />,
    );

    expect(screen.getByText('Workbench')).toBeInTheDocument();
    expect(screen.getByText('The selected run is blocked by an approval gate.')).toBeInTheDocument();
    expect(screen.getByText((content) => content.includes('"status": "blocked"'))).toBeInTheDocument();

    await user.click(screen.getByRole('tab', { name: 'tasks.json' }));

    expect(onSelectArtifact).toHaveBeenCalledWith('tasks.json');
  });

  it('renders searchable navigation, real tabs, history, and governance status chrome', async () => {
    const descriptor: ArtifactDescriptor = {
      artifactId: 'artifact-document',
      workspaceId: 'workspace-1',
      kind: 'document',
      title: 'Launch plan',
      status: 'active',
      schemaVersion: 1,
      dataClass: 'confidential',
      currentRevisionId: 'revision-2',
      currentRevisionNumber: 2,
      sourceSessionId: null,
      sourceTurnId: null,
      createdByType: 'assistant',
      createdById: 'assistant-1',
      updatedById: 'user-1',
      createdAtUtc: '2026-07-16T08:00:00Z',
      updatedAtUtc: '2026-07-16T09:00:00Z',
      archivedAtUtc: null,
      etag: 'etag-2',
      metadata: { policyStatus: 'governed' },
    };
    const revision: ArtifactRevision = {
      revisionId: 'revision-2',
      artifactId: descriptor.artifactId,
      parentRevisionId: 'revision-1',
      baseRevisionId: 'revision-1',
      revisionNumber: 2,
      schemaVersion: 1,
      mutationType: 'replace_content',
      contentRelpath: 'workspace-1/artifact-document/revision-2.json',
      contentSha256: 'a'.repeat(64),
      contentSizeBytes: 64,
      contentEncoding: 'json',
      changeSummary: 'Updated title',
      authorType: 'user',
      authorId: 'user-1',
      idempotencyKey: 'save-2',
      createdAtUtc: '2026-07-16T09:00:00Z',
    };
    const codeArtifact = { ...descriptor, artifactId: 'artifact-code', kind: 'code' as const, title: 'Policy code' };
    const workspaceState: ArtifactWorkspaceState = {
      activeArtifactId: descriptor.artifactId,
      closeGuard: null,
      tabs: [
        {
          artifact: descriptor,
          revision,
          persistedContent: {
            kind: 'document',
            schemaVersion: 1,
            language: 'en',
            pageMode: 'document',
            blocks: [],
          },
          draftContent: {
            kind: 'document',
            schemaVersion: 1,
            language: 'en',
            pageMode: 'document',
            blocks: [
              {
                id: 'block-1',
                type: 'paragraph',
                props: {},
                content: [{ type: 'text', text: 'Launch', styles: {} }],
                children: [],
              },
            ],
          },
          dirty: false,
          saveState: 'saved',
          saveError: null,
          conflict: null,
        },
      ],
    };
    const onOpenArtifact = vi.fn();
    const onRequestClose = vi.fn();
    const onLoadMore = vi.fn();
    const onLoadMoreHistory = vi.fn();
    const onRestoreArtifact = vi.fn();
    const onCompareRevision = vi.fn();
    const onExportArtifact = vi.fn();
    const previousRevision: ArtifactRevision = {
      ...revision,
      revisionId: 'revision-1',
      revisionNumber: 1,
      parentRevisionId: null,
      changeSummary: 'Initial draft',
    };
    const { user } = renderOperatorPanel(
      <AssistantWorkbench
        state={getAssistantFixture('running')}
        artifacts={[]}
        selectedArtifactName=""
        onSelectArtifact={vi.fn()}
        onViewRuns={vi.fn()}
        workspaceState={workspaceState}
        catalog={[descriptor, codeArtifact]}
        catalogNextCursor="cursor-2"
        history={[revision, previousRevision]}
        historyNextCursor="history-cursor-2"
        workspaceError={{ code: 'ARTIFACT_EXPORT_FAILED', message: 'Export failed safely.', retryable: true }}
        operationNotice="Previous export completed."
        onOpenArtifact={onOpenArtifact}
        onActivateArtifact={vi.fn()}
        onRequestClose={onRequestClose}
        onLoadCatalog={vi.fn()}
        onLoadMoreCatalog={onLoadMore}
        onLoadHistory={vi.fn()}
        onLoadMoreHistory={onLoadMoreHistory}
        onRestoreArtifact={onRestoreArtifact}
        onCompareRevision={onCompareRevision}
        onExportArtifact={onExportArtifact}
      />,
    );

    expect(screen.getByRole('tab', { name: /Launch plan/ })).toHaveAttribute('aria-selected', 'true');
    expect(within(screen.getByLabelText('Artifact status')).getByText('Revision 2')).toBeInTheDocument();
    expect(screen.getByText('confidential')).toBeInTheDocument();
    expect(screen.getByText('governed')).toBeInTheDocument();
    expect(screen.getByText('Updated title')).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('Export failed safely.');
    expect(screen.getByRole('status', { name: 'Artifact operation status' })).toHaveTextContent('Previous export completed.');
    expect(screen.queryByRole('status', { name: 'Artifact selection' })).not.toBeInTheDocument();

    await user.type(screen.getByRole('searchbox', { name: 'Search artifacts' }), 'Policy');
    await user.click(screen.getByRole('button', { name: /Policy code/ }));
    expect(onOpenArtifact).toHaveBeenCalledWith('artifact-code');

    await user.click(screen.getByRole('button', { name: 'Close Launch plan' }));
    expect(onRequestClose).toHaveBeenCalledWith('artifact-document');
    await user.click(screen.getByRole('button', { name: 'Load more artifacts' }));
    expect(onLoadMore).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole('button', { name: 'Restore revision 1' }));
    expect(onRestoreArtifact).toHaveBeenCalledWith('artifact-document', 'revision-1');
    await user.click(screen.getByRole('button', { name: 'Compare revision 1' }));
    expect(onCompareRevision).toHaveBeenCalledWith('artifact-document', 'revision-1');
    await user.click(screen.getByRole('button', { name: 'Load more history' }));
    expect(onLoadMoreHistory).toHaveBeenCalledWith('artifact-document');

    await user.click(screen.getByRole('button', { name: 'Export' }));
    await user.selectOptions(screen.getByLabelText('Export format'), 'markdown');
    await user.click(screen.getByRole('button', { name: 'Choose destination and export' }));
    await user.click(screen.getByRole('button', { name: 'Export' }));
    await user.selectOptions(screen.getByLabelText('Export format'), 'html');
    await user.click(screen.getByRole('button', { name: 'Choose destination and export' }));
    expect(onExportArtifact).toHaveBeenNthCalledWith(1, 'artifact-document', 'markdown');
    expect(onExportArtifact).toHaveBeenNthCalledWith(2, 'artifact-document', 'html');
  });

  it('does not steal newer focus when an asynchronous conflict resolution completes', async () => {
    const descriptor: ArtifactDescriptor = {
      artifactId: 'artifact-document',
      workspaceId: 'workspace-1',
      kind: 'document',
      title: 'Launch plan',
      status: 'active',
      schemaVersion: 1,
      dataClass: 'confidential',
      currentRevisionId: 'revision-2',
      currentRevisionNumber: 2,
      sourceSessionId: null,
      sourceTurnId: null,
      createdByType: 'assistant',
      createdById: 'assistant-1',
      updatedById: 'user-1',
      createdAtUtc: '2026-07-16T08:00:00Z',
      updatedAtUtc: '2026-07-16T09:00:00Z',
      archivedAtUtc: null,
      etag: 'etag-2',
      metadata: {},
    };
    const revision: ArtifactRevision = {
      revisionId: 'revision-2',
      artifactId: descriptor.artifactId,
      parentRevisionId: 'revision-1',
      baseRevisionId: 'revision-1',
      revisionNumber: 2,
      schemaVersion: 1,
      mutationType: 'replace_content',
      contentRelpath: 'workspace-1/artifact-document/revision-2.json',
      contentSha256: 'a'.repeat(64),
      contentSizeBytes: 64,
      contentEncoding: 'json',
      changeSummary: 'Updated title',
      authorType: 'user',
      authorId: 'user-1',
      idempotencyKey: 'save-2',
      createdAtUtc: '2026-07-16T09:00:00Z',
    };
    const content = {
      kind: 'document' as const,
      schemaVersion: 1 as const,
      language: 'en',
      pageMode: 'document' as const,
      blocks: [{
        id: 'block-1',
        type: 'paragraph',
        props: {},
        content: [],
        children: [],
      }],
    };
    const conflictingState: ArtifactWorkspaceState = {
      activeArtifactId: descriptor.artifactId,
      closeGuard: null,
      tabs: [{
        artifact: descriptor,
        revision,
        persistedContent: content,
        draftContent: content,
        dirty: true,
        saveState: 'conflict',
        saveError: null,
        conflict: {
          status: 'ready',
          baseRevisionNumber: 1,
          baseRevisionId: 'revision-1',
          remote: { artifact: descriptor, revision, content },
          error: null,
          detectedAtUtc: '2026-07-16T09:00:00Z',
        },
      }],
    };
    const props = {
      state: getAssistantFixture('running'),
      artifacts: [],
      selectedArtifactName: '',
      onSelectArtifact: vi.fn(),
      onViewRuns: vi.fn(),
    };
    const { rerender } = renderOperatorPanel(
      <>
        <button type="button">Stable workbench control</button>
        <AssistantWorkbench {...props} workspaceState={conflictingState} />
      </>,
    );
    expect(
      within(await screen.findByRole('region', { name: 'Document editor: Launch plan' }))
        .getByRole('textbox'),
    ).toHaveAttribute('contenteditable', 'true');

    screen.getByRole('button', { name: 'Stable workbench control' }).focus();
    const resolvedState = {
      ...conflictingState,
      tabs: conflictingState.tabs.map((tab) => ({ ...tab, conflict: null })),
    };
    rerender(
      <>
        <button type="button">Stable workbench control</button>
        <AssistantWorkbench {...props} workspaceState={resolvedState} />
      </>,
    );

    await act(async () => Promise.resolve());
    expect(screen.getByRole('button', { name: 'Stable workbench control' })).toHaveFocus();
  });

  it('announces save failure, retries by keyboard, and restores the active tab after success', async () => {
    const descriptor: ArtifactDescriptor = {
      artifactId: 'artifact-document', workspaceId: 'workspace-1', kind: 'document', title: 'Launch plan',
      status: 'active', schemaVersion: 1, dataClass: 'internal', currentRevisionId: 'revision-1',
      currentRevisionNumber: 1, sourceSessionId: null, sourceTurnId: null, createdByType: 'user',
      createdById: 'user-1', updatedById: 'user-1', createdAtUtc: '2026-07-16T08:00:00Z',
      updatedAtUtc: '2026-07-16T08:00:00Z', archivedAtUtc: null, etag: 'etag-1', metadata: {},
    };
    const revision: ArtifactRevision = {
      revisionId: 'revision-1', artifactId: descriptor.artifactId, parentRevisionId: null,
      baseRevisionId: null, revisionNumber: 1, schemaVersion: 1, mutationType: 'create', contentRelpath: 'revision-1.json',
      contentSha256: 'a'.repeat(64), contentSizeBytes: 64, contentEncoding: 'json',
      changeSummary: 'Created', authorType: 'user', authorId: 'user-1', idempotencyKey: 'create-1',
      createdAtUtc: '2026-07-16T08:00:00Z',
    };
    const content = {
      kind: 'document' as const, schemaVersion: 1 as const, language: 'en', pageMode: 'document' as const,
      blocks: [{ id: 'block-1', type: 'paragraph', props: {}, content: [], children: [] }],
    };
    const savedState: ArtifactWorkspaceState = {
      activeArtifactId: descriptor.artifactId, closeGuard: null,
      tabs: [{ artifact: descriptor, revision, persistedContent: content, draftContent: content, dirty: false, saveState: 'saved', saveError: null, conflict: null }],
    };
    const failedState: ArtifactWorkspaceState = {
      ...savedState,
      tabs: [{ ...savedState.tabs[0], dirty: true, saveState: 'error', saveError: 'Autosave is offline.' }],
    };
    const retry = vi.fn();
    const props = {
      state: getAssistantFixture('running'), artifacts: [], selectedArtifactName: '',
      onSelectArtifact: vi.fn(), onViewRuns: vi.fn(), onRetrySave: retry,
    };
    const { rerender, user } = renderOperatorPanel(
      <>
        <button type="button">Stable workbench control</button>
        <AssistantWorkbench {...props} workspaceState={savedState} />
      </>,
    );
    screen.getByRole('button', { name: 'Stable workbench control' }).focus();

    rerender(
      <>
        <button type="button">Stable workbench control</button>
        <AssistantWorkbench {...props} workspaceState={failedState} />
      </>,
    );
    expect(screen.getByRole('button', { name: 'Stable workbench control' })).toHaveFocus();
    expect(screen.getByRole('alert')).toHaveTextContent('Autosave is offline.');
    const retryButton = screen.getByRole('button', { name: 'Retry save' });
    retryButton.focus();
    await user.keyboard('{Enter}');
    expect(retry).toHaveBeenCalledWith('artifact-document');

    rerender(
      <>
        <button type="button">Stable workbench control</button>
        <AssistantWorkbench {...props} workspaceState={savedState} />
      </>,
    );
    await act(async () => Promise.resolve());
    expect(screen.getByRole('tab', { name: 'Launch plan' })).toHaveFocus();
  });
});
