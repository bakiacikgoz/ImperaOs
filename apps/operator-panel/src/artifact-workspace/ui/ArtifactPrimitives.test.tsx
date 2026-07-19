import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ArtifactBadge, ArtifactButton, ArtifactPanel } from './ArtifactPrimitives';

describe('artifact workspace scoped UI primitives', () => {
  it('renders source-controlled primitives with artifact-only classes', () => {
    render(
      <div className="artifact-workspace">
        <ArtifactPanel aria-label="Document panel">
          <ArtifactBadge tone="warning">Unsaved</ArtifactBadge>
          <ArtifactButton variant="primary">Save</ArtifactButton>
        </ArtifactPanel>
      </div>,
    );

    expect(screen.getByRole('region', { name: 'Document panel' })).toHaveClass('aw-panel');
    expect(screen.getByText('Unsaved')).toHaveClass('aw-badge--warning');
    expect(screen.getByRole('button', { name: 'Save' })).toHaveClass('aw-button--primary');
  });
});
