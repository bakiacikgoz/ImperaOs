import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ProductShellErrorBoundary } from './ProductShellErrorBoundary';

function BrokenRoute(): never {
  throw new Error('private-token=do-not-render');
}

describe('ProductShellErrorBoundary', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('shows a safe recovery alert when a product route crashes', () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined);

    render(
      <ProductShellErrorBoundary>
        <BrokenRoute />
      </ProductShellErrorBoundary>,
    );

    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent('The product shell could not be displayed.');
    expect(alert).not.toHaveTextContent('private-token=do-not-render');
    expect(screen.getByRole('button', { name: 'Reload product shell' })).toBeInTheDocument();
  });

  it('renders a healthy product route unchanged', () => {
    render(
      <ProductShellErrorBoundary>
        <main>Healthy product route</main>
      </ProductShellErrorBoundary>,
    );

    expect(screen.getByRole('main')).toHaveTextContent('Healthy product route');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});
