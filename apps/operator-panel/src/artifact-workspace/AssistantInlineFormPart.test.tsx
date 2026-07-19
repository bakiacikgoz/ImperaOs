import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type { ArtifactWorkspaceTab } from './workspaceController';
import { AssistantInlineFormPart } from './AssistantInlineFormPart';
import { FormSessionRuntime } from './editors/form/formSessionRuntime';

const tab = {
  artifact: {
    artifactId: 'artifact-form', workspaceId: 'workspace-1', kind: 'form', title: 'Inline intake', status: 'active',
    schemaVersion: 1, dataClass: 'internal', currentRevisionId: 'revision-1', currentRevisionNumber: 1,
    sourceSessionId: null, sourceTurnId: null, createdByType: 'assistant', createdById: 'assistant-1',
    updatedById: 'assistant-1', createdAtUtc: '2026-07-16T08:00:00Z', updatedAtUtc: '2026-07-16T08:00:00Z',
    archivedAtUtc: null, etag: 'etag-1', metadata: {},
  },
  revision: {
    revisionId: 'revision-1', artifactId: 'artifact-form', parentRevisionId: null, baseRevisionId: null,
    revisionNumber: 1, schemaVersion: 1, mutationType: 'create', contentRelpath: 'form.json', contentSha256: 'a'.repeat(64),
    contentSizeBytes: 100, contentEncoding: 'json', changeSummary: '', authorType: 'assistant',
    authorId: 'assistant-1', idempotencyKey: 'create-form', createdAtUtc: '2026-07-16T08:00:00Z',
  },
  persistedContent: {
    kind: 'form', schemaVersion: 1, schema: { type: 'object', properties: {} },
  },
  draftContent: {
    kind: 'form', schemaVersion: 1, schema: { type: 'object', properties: {} },
  },
  dirty: false, saveState: 'idle', saveError: null, conflict: null,
} satisfies ArtifactWorkspaceTab;

describe('AssistantInlineFormPart', () => {
  it('loads the governed artifact without expanding and exposes an explicit expand action', async () => {
    const onLoad = vi.fn();
    const onExpand = vi.fn();
    const props = {
      artifactId: 'artifact-form', loading: false, locale: 'en' as const,
      formRuntime: new FormSessionRuntime(), onLoad, onExpand, onSubmit: vi.fn(),
    };
    const view = render(<AssistantInlineFormPart {...props} tab={null} />);
    await waitFor(() => expect(onLoad).toHaveBeenCalledWith('artifact-form'));
    expect(screen.getByRole('status')).toHaveTextContent(/loading governed form/i);
    view.rerender(<AssistantInlineFormPart {...props} tab={null} />);
    expect(onLoad).toHaveBeenCalledTimes(1);

    view.rerender(<AssistantInlineFormPart {...props} tab={tab} />);
    expect(screen.getByText('Validated form')).toBeInTheDocument();
    expect(screen.getByText(/answers are checked before submission/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: /expand in workbench/i }));
    expect(onExpand).toHaveBeenCalledWith('artifact-form');
  });
});
