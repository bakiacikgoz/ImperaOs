import { screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { renderOperatorPanel } from '../../test/render';
import { ArtifactDiffView } from './ArtifactDiffView';

describe('ArtifactDiffView', () => {
  it('renders a bounded read-only comparison with non-color labels and closes', async () => {
    const onClose = vi.fn();
    const { user } = renderOperatorPanel(
      <ArtifactDiffView
        beforeRevisionNumber={1}
        afterRevisionNumber={2}
        dirtyDraftExcluded
        result={{
          kind: 'document',
          entries: [
            { scope: 'block', key: 'block-1', change: 'moved' },
            { scope: 'block', key: 'block-2', change: 'changed', fields: ['content'] },
          ],
          inspectedItems: 4,
          totalChanges: 7,
          totalChangesIsLowerBound: false,
          omittedChanges: 5,
          truncated: true,
        }}
        onClose={onClose}
      />,
    );

    expect(screen.getByRole('region', { name: 'Revision comparison' })).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('7 changes');
    expect(screen.getByText('Unsaved draft is preserved and excluded from comparison.')).toBeInTheDocument();
    expect(screen.getByText('Moved')).toBeInTheDocument();
    expect(screen.getByText('Changed')).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('5 change details omitted');

    await user.click(screen.getByRole('button', { name: 'Close comparison' }));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('does not claim there are no changes when inspection was truncated', () => {
    renderOperatorPanel(
      <ArtifactDiffView
        beforeRevisionNumber={1}
        afterRevisionNumber={2}
        dirtyDraftExcluded={false}
        result={{
          kind: 'canvas', entries: [], inspectedItems: 20_000, totalChanges: 0,
          totalChangesIsLowerBound: true, omittedChanges: 0, truncated: true,
        }}
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByText('No changes found in the inspected subset; uninspected content remains.')).toBeInTheDocument();
    expect(screen.queryByText('No persisted revision changes.')).not.toBeInTheDocument();
  });
});
