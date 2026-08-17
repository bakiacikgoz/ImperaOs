import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import type { ArtifactDescriptor, ArtifactRevision } from '../../artifactContracts';
import { FormArtifactEditor } from './FormArtifactEditor';
import { FormSessionRuntime } from './formSessionRuntime';

const artifact = {
  artifactId: 'artifact-form-1', workspaceId: 'workspace-1', kind: 'form', title: 'Kimlik formu', status: 'active',
  schemaVersion: 1, dataClass: 'internal', currentRevisionId: 'revision-form-1', currentRevisionNumber: 1,
  sourceSessionId: null, sourceTurnId: null, createdByType: 'user', createdById: 'user-1', updatedById: 'user-1',
  createdAtUtc: '2026-07-16T08:00:00Z', updatedAtUtc: '2026-07-16T08:00:00Z', archivedAtUtc: null,
  etag: 'etag-1', metadata: {},
} satisfies ArtifactDescriptor;

const revision = {
  revisionId: 'revision-form-1', artifactId: artifact.artifactId, parentRevisionId: null, baseRevisionId: null,
  revisionNumber: 1, schemaVersion: 1, mutationType: 'create', contentRelpath: 'content/form.json', contentSha256: 'a'.repeat(64),
  contentSizeBytes: 100, contentEncoding: 'json', changeSummary: 'Created', authorType: 'user', authorId: 'user-1',
  idempotencyKey: 'create-form-1', createdAtUtc: '2026-07-16T08:00:00Z',
} satisfies ArtifactRevision;

const content = {
  kind: 'form', schemaVersion: 1,
  schema: {
    type: 'object', title: 'Kimlik',
    properties: { name: { type: 'string', title: 'Ad', minLength: 2 } },
    required: ['name'], additionalProperties: false,
  },
  uiSchema: {},
  behavior: { submitMode: 'explicit', externalContinuation: 'deny' },
  sensitivePaths: ['/name'],
};

describe('FormArtifactEditor', () => {
  it('shares controlled data, masks sensitive fields, and has no implicit submit', async () => {
    const user = userEvent.setup();
    const runtime = new FormSessionRuntime();
    render(
      <>
        <FormArtifactEditor artifact={artifact} revision={revision} content={content} mode="edit" runtime={runtime} />
        <FormArtifactEditor artifact={artifact} revision={revision} content={content} mode="edit" runtime={runtime} />
      </>,
    );

    const fields = screen.getAllByLabelText(/Ad/);
    expect(fields).toHaveLength(2);
    expect(fields[0]).toHaveAttribute('type', 'password');
    await user.type(fields[0], 'Ada');
    expect(fields[1]).toHaveValue('Ada');
    expect(screen.queryByRole('button', { name: /submit|gönder/i })).not.toBeInTheDocument();
  });

  it('shows a bounded accessible error summary', async () => {
    const user = userEvent.setup();
    const runtime = new FormSessionRuntime();
    render(<FormArtifactEditor artifact={artifact} revision={revision} content={content} mode="edit" runtime={runtime} />);
    const field = screen.getByLabelText(/Ad/);
    await user.type(field, 'A');
    await user.tab();
    expect(await screen.findByRole('alert')).toHaveTextContent(/invalid|required|minimum/i);
    expect(screen.getByRole('alert').textContent?.length).toBeLessThan(1000);
  });

  it('submits explicitly with a stable retry key and never renders the response', async () => {
    const secret = 'private-submit-response';
    const user = userEvent.setup();
    const runtime = new FormSessionRuntime();
    const onSubmit = vi.fn()
      .mockRejectedValueOnce(new Error(secret))
      .mockResolvedValueOnce({ status: 'accepted', disposition: 'idempotent_replay' });
    render(
      <FormArtifactEditor
        artifact={artifact}
        revision={revision}
        content={content}
        mode="edit"
        runtime={runtime}
        onSubmit={onSubmit}
      />,
    );
    await user.type(screen.getByLabelText(/Ad/), 'Ada');
    await user.click(screen.getByRole('button', { name: /submit form/i }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not be submitted/i);
    await user.click(screen.getByRole('button', { name: /retry form submission/i }));
    expect(await screen.findByRole('status')).toHaveTextContent(/submitted/i);
    expect(onSubmit).toHaveBeenCalledTimes(2);
    expect(onSubmit.mock.calls[0][0]).toEqual({ name: 'Ada' });
    expect(onSubmit.mock.calls[0][1]).toBe(onSubmit.mock.calls[1][1]);
    expect(document.body.textContent).not.toContain(secret);
  });

  it('masks nested sensitive paths and focuses the error summary on invalid submit', async () => {
    const user = userEvent.setup();
    const nestedContent = {
      ...content,
      schema: {
        type: 'object',
        properties: {
          contact: {
            type: 'object',
            properties: { email: { type: 'string', title: 'Email', minLength: 3 } },
            required: ['email'],
          },
        },
        required: ['contact'],
      },
      sensitivePaths: ['/contact/email'],
    };
    render(
      <FormArtifactEditor
        artifact={artifact}
        revision={revision}
        content={nestedContent}
        mode="edit"
        runtime={new FormSessionRuntime()}
        onSubmit={vi.fn()}
      />,
    );
    expect(screen.getByLabelText(/Email/)).toHaveAttribute('type', 'password');
    await user.click(screen.getByRole('button', { name: /submit form/i }));
    expect(await screen.findByRole('alert')).toHaveFocus();
    expect(screen.getByRole('alert').querySelector('a')).toHaveAttribute('href', expect.stringMatching(/^#/));
  });

  it('retains retry identity through remount and blocks duplicate terminal submit', async () => {
    const user = userEvent.setup();
    const runtime = new FormSessionRuntime();
    const onSubmit = vi.fn()
      .mockRejectedValueOnce(new Error('controlled'))
      .mockResolvedValueOnce({ status: 'pending_continuation', disposition: 'idempotent_replay' });
    const first = render(
      <FormArtifactEditor artifact={artifact} revision={revision} content={content} mode="edit" runtime={runtime} onSubmit={onSubmit} />,
    );
    await user.type(screen.getByLabelText(/Ad/), 'Ada');
    await user.click(screen.getByRole('button', { name: /submit form/i }));
    expect(await screen.findByRole('alert')).toBeVisible();
    first.unmount();
    render(<FormArtifactEditor artifact={artifact} revision={revision} content={content} mode="edit" runtime={runtime} onSubmit={onSubmit} />);
    await user.click(screen.getByRole('button', { name: /retry form submission/i }));
    expect(await screen.findByRole('status')).toHaveTextContent(/awaiting approval/i);
    await user.click(screen.getByRole('button', { name: /submit form/i }));
    expect(onSubmit).toHaveBeenCalledTimes(2);
    expect(onSubmit.mock.calls[0][1]).toBe(onSubmit.mock.calls[1][1]);
  });

  it('renders the explicit submission action in Turkish', () => {
    render(
      <FormArtifactEditor
        artifact={artifact}
        revision={revision}
        content={content}
        mode="edit"
        runtime={new FormSessionRuntime()}
        locale="tr"
        onSubmit={vi.fn()}
      />,
    );
    expect(screen.getByRole('button', { name: 'Formu gönder' })).toBeVisible();
  });
});
