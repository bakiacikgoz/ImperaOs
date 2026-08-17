import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ArtifactSelectionChip } from './ArtifactSelectionChip';

describe('ArtifactSelectionChip', () => {
  it('renders coordinate-only selection labels and never raw selected content', () => {
    render(
      <ArtifactSelectionChip
        selection={{
          kind: 'code',
          startLineNumber: 4,
          startColumn: 2,
          endLineNumber: 8,
          endColumn: 7,
        }}
      />,
    );

    expect(screen.getByRole('status', { name: 'Artifact selection' })).toHaveTextContent('Code lines 4–8');
    expect(screen.queryByText(/selected source text/i)).not.toBeInTheDocument();
  });
});
