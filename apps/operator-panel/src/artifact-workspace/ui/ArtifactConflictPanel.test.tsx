import { screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { ArtifactReadResult } from '../artifactContracts';
import type { ArtifactConflict } from '../workspaceController';
import { renderOperatorPanel } from '../../test/render';
import { ArtifactConflictPanel } from './ArtifactConflictPanel';

const conflict: ArtifactConflict = {
  status: 'ready',
  baseRevisionNumber: 1,
  baseRevisionId: 'revision-1',
  remote: {
    artifact: { artifactId: 'artifact-1', currentRevisionNumber: 2 },
    revision: { revisionId: 'revision-2', revisionNumber: 2 },
    content: { kind: 'document', schemaVersion: 1 },
  } as ArtifactReadResult,
  error: null,
  detectedAtUtc: '2026-07-16T09:00:00Z',
};

describe('ArtifactConflictPanel', () => {
  it('offers compare/fork and requires explicit confirmation before reload', async () => {
    const onReload = vi.fn();
    const onCompare = vi.fn();
    const onFork = vi.fn();
    const { user } = renderOperatorPanel(
      <ArtifactConflictPanel
        conflict={conflict}
        resolvingAction={null}
        onRefresh={vi.fn()}
        onCompare={onCompare}
        onReload={onReload}
        onFork={onFork}
        comparisonOpen={false}
      />,
    );

    expect(screen.getByRole('region', { name: 'Revision conflict' })).toHaveTextContent('local draft is preserved');
    await user.click(screen.getByRole('button', { name: 'Compare' }));
    await user.click(screen.getByRole('button', { name: 'Fork local draft' }));
    expect(onCompare).toHaveBeenCalledOnce();
    expect(onFork).toHaveBeenCalledOnce();

    await user.click(screen.getByRole('button', { name: 'Reload latest remote' }));
    expect(onReload).not.toHaveBeenCalled();
    const dialog = screen.getByRole('alertdialog', { name: 'Discard local draft?' });
    expect(dialog).toBeInTheDocument();
    expect(dialog.tagName).toBe('DIALOG');
    expect(dialog).toHaveAttribute('aria-describedby', 'artifact-conflict-confirm-description');
    expect(screen.getByRole('button', { name: 'Compare' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Fork local draft' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Reload latest remote' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Cancel' })).toHaveFocus();
    await user.tab({ shift: true });
    expect(screen.getByRole('button', { name: 'Discard draft and reload' })).toHaveFocus();
    await user.tab();
    expect(screen.getByRole('button', { name: 'Cancel' })).toHaveFocus();
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Reload latest remote' })).toHaveFocus();
    expect(screen.getByRole('button', { name: 'Compare' })).toBeEnabled();
    await user.click(screen.getByRole('button', { name: 'Reload latest remote' }));
    await user.click(screen.getByRole('button', { name: 'Discard draft and reload' }));
    expect(onReload).toHaveBeenCalledOnce();
  });

  it('keeps a safe focus target while reload is pending and restores Reload after failure', async () => {
    const onReload = vi.fn();
    const props = {
      conflict,
      comparisonOpen: false,
      onRefresh: vi.fn(),
      onCompare: vi.fn(),
      onReload,
      onFork: vi.fn(),
    } as const;
    const { user, rerender } = renderOperatorPanel(
      <ArtifactConflictPanel {...props} resolvingAction={null} />,
    );

    await user.click(screen.getByRole('button', { name: 'Reload latest remote' }));
    await user.click(screen.getByRole('button', { name: 'Discard draft and reload' }));
    rerender(<ArtifactConflictPanel {...props} resolvingAction="reload" />);

    expect(onReload).toHaveBeenCalledOnce();
    expect(screen.getByRole('alertdialog', { name: 'Discard local draft?' })).toBeInTheDocument();
    expect(document.activeElement).not.toBe(document.body);

    rerender(<ArtifactConflictPanel {...props} resolvingAction={null} />);

    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Reload latest remote' })).toHaveFocus();
    });
  });

  it('keeps only remote retry available when snapshot loading failed', async () => {
    const onRefresh = vi.fn();
    const { user } = renderOperatorPanel(
      <ArtifactConflictPanel
        conflict={{ ...conflict, status: 'error', remote: null, error: 'Remote unavailable.' }}
        resolvingAction={null}
        onRefresh={onRefresh}
        onCompare={vi.fn()}
        onReload={vi.fn()}
        onFork={vi.fn()}
        comparisonOpen={false}
      />,
    );

    expect(screen.getByText('Remote unavailable.')).toHaveAttribute('role', 'alert');
    expect(screen.queryByRole('button', { name: 'Compare' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Retry loading latest' }));
    expect(onRefresh).toHaveBeenCalledOnce();
  });

  it('does not steal focus when an asynchronous conflict appears', () => {
    renderOperatorPanel(
      <>
        <input aria-label="Active editor" autoFocus />
        <ArtifactConflictPanel
          conflict={conflict}
          resolvingAction={null}
          comparisonOpen={false}
          onRefresh={vi.fn()}
          onCompare={vi.fn()}
          onReload={vi.fn()}
          onFork={vi.fn()}
        />
      </>,
    );

    expect(screen.getByRole('textbox', { name: 'Active editor' })).toHaveFocus();
    expect(screen.getByRole('alert')).toHaveTextContent('local draft is preserved');
  });

  it('returns focus to Compare when the comparison closes', () => {
    const props = {
      conflict,
      resolvingAction: null,
      onRefresh: vi.fn(),
      onCompare: vi.fn(),
      onReload: vi.fn(),
      onFork: vi.fn(),
    } as const;
    const { rerender } = renderOperatorPanel(
      <ArtifactConflictPanel {...props} comparisonOpen />,
    );

    rerender(<ArtifactConflictPanel {...props} comparisonOpen={false} />);

    expect(screen.getByRole('button', { name: 'Compare' })).toHaveFocus();
  });
});
