import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

import { ProductRouter } from './router/ProductRouter';
import { AppShell } from './shell/AppShell';
import { useProductShellStore } from './state/productShellStore';

vi.mock('./legacy/LegacyOperatorApp', () => ({
  LegacyOperatorApp: () => <div data-testid="legacy-route">Legacy system route</div>,
}));
vi.mock('./pages/NewWorkPage', () => ({
  NewWorkPage: () => <div data-testid="product-route">Product route</div>,
}));

describe('Product Shell UI Lab theme contract', () => {
  beforeEach(() => {
    localStorage.clear();
    useProductShellStore.setState({
      sidebarCollapsed: false,
      sidebarWidth: 260,
      theme: 'dark',
    });
  });

  afterEach(() => {
    cleanup();
    window.location.hash = '';
    delete document.documentElement.dataset.theme;
  });

  it('mounts the frozen UI Lab theme only with the source shell hierarchy', () => {
    render(
      <MemoryRouter>
        <AppShell>
          <div>Product content</div>
        </AppShell>
      </MemoryRouter>,
    );

    expect(document.querySelector('style[data-ui-lab-theme]')).not.toBeNull();
    expect(document.querySelector('.imperaos-product-shell-v2.app-shell')).not.toBeNull();
    expect(document.querySelector('.app-frame')).not.toBeNull();
    expect(document.querySelector('.sidebar.codex-sidebar')).not.toBeNull();
    expect(document.documentElement.dataset.theme).toBe('dark');
  });

  it('removes every product theme and adapter rule when routing into legacy system pages', async () => {
    window.location.hash = '#/';
    render(<ProductRouter />);

    expect(screen.getByTestId('product-route')).toBeInTheDocument();
    expect(document.querySelector('style[data-ui-lab-theme]')).not.toBeNull();
    expect(document.querySelector('style[data-product-shell-adapters]')).not.toBeNull();

    window.location.hash = '#/system/settings';
    window.dispatchEvent(new HashChangeEvent('hashchange'));

    await waitFor(() => expect(screen.getByTestId('legacy-route')).toBeInTheDocument());
    expect(document.querySelector('style[data-ui-lab-theme]')).toBeNull();
    expect(document.querySelector('style[data-product-shell-adapters]')).toBeNull();
    expect(document.querySelector('.imperaos-product-shell-v2')).toBeNull();
  });
});
