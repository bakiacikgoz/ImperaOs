import { screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const invoke = vi.hoisted(() => vi.fn());

vi.mock('@tauri-apps/api/core', () => ({ invoke }));

import { renderOperatorPanel } from '../../test/render';
import { BrowserSurface } from './BrowserSurface';

describe('BrowserSurface', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    invoke.mockImplementation(async (command: string) => {
      if (command === 'browser_open') return 'imperaos-browser-user';
      if (command === 'browser_history_state') return { canBack: true, canForward: false };
      return undefined;
    });
  });

  it('sends history navigation back through the native governed session', async () => {
    const { user, container } = renderOperatorPanel(<BrowserSurface onClose={vi.fn()} />);

    expect(container.querySelector('.browser-surface .browser-toolbar .browser-address-bar')).toBeInTheDocument();
    expect(container.querySelector('.browser-page.native-browser-viewport')).toBeInTheDocument();
    await user.clear(screen.getByRole('textbox', { name: 'Browser address' }));
    await user.type(screen.getByRole('textbox', { name: 'Browser address' }), 'https://imperaos.dev/docs');
    await user.click(screen.getByRole('button', { name: 'Open HTTPS' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Back' })).toBeEnabled());
    await user.click(screen.getByRole('button', { name: 'Back' }));

    expect(invoke).toHaveBeenCalledWith('browser_back', {
      request: { label: 'imperaos-browser-user' },
    });
  });

  it('synchronizes the native child webview to the reserved viewport', async () => {
    const bounds = vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({
      x: 120, y: 180, width: 740, height: 420, top: 180, right: 860, bottom: 600, left: 120,
      toJSON: () => ({}),
    });
    const { user } = renderOperatorPanel(<BrowserSurface onClose={vi.fn()} />);

    await user.click(screen.getByRole('button', { name: 'Open HTTPS' }));

    await waitFor(() => expect(invoke).toHaveBeenCalledWith('browser_set_bounds', {
      request: { label: 'imperaos-browser-user', x: 120, y: 180, width: 740, height: 420 },
    }));
    bounds.mockRestore();
  });

  it('shows the exact native policy denial returned as a Tauri string error', async () => {
    invoke.mockRejectedValueOnce('BROWSER_POLICY_DENIED: user mode requires an explicit HTTPS URL');
    const { user } = renderOperatorPanel(<BrowserSurface onClose={vi.fn()} />);

    await user.click(screen.getByRole('button', { name: 'Open HTTPS' }));

    expect(await screen.findByRole('status')).toHaveTextContent(
      'BROWSER_POLICY_DENIED: user mode requires an explicit HTTPS URL',
    );
  });

  it('closes a native browser session that finishes opening after the tab unmounts', async () => {
    let resolveOpen: ((label: string) => void) | undefined;
    invoke.mockImplementation((command: string) => {
      if (command === 'browser_open') {
        return new Promise((resolve) => { resolveOpen = resolve; });
      }
      return Promise.resolve(undefined);
    });
    const { user, unmount } = renderOperatorPanel(<BrowserSurface onClose={vi.fn()} />);

    await user.click(screen.getByRole('button', { name: 'Open HTTPS' }));
    unmount();
    resolveOpen?.('imperaos-browser-late');

    await waitFor(() => expect(invoke).toHaveBeenCalledWith('browser_close', {
      request: { label: 'imperaos-browser-late' },
    }));
  });

  it('does not create duplicate native sessions while an open is pending', async () => {
    let resolveOpen: ((label: string) => void) | undefined;
    invoke.mockImplementation((command: string) => {
      if (command === 'browser_open') {
        return new Promise((resolve) => { resolveOpen = resolve; });
      }
      return Promise.resolve(undefined);
    });
    const { user } = renderOperatorPanel(<BrowserSurface onClose={vi.fn()} />);
    const openButton = screen.getByRole('button', { name: 'Open HTTPS' });

    await user.click(openButton);
    await user.click(openButton);

    expect(invoke.mock.calls.filter(([command]) => command === 'browser_open')).toHaveLength(1);
    resolveOpen?.('imperaos-browser-one');
  });

  it('closes an already-open native session when the owning workspace tab unmounts', async () => {
    const { user, unmount } = renderOperatorPanel(<BrowserSurface onClose={vi.fn()} />);
    await user.click(screen.getByRole('button', { name: 'Open HTTPS' }));
    await waitFor(() => expect(screen.getByText(/Opened native browser/)).toBeInTheDocument());

    unmount();

    await waitFor(() => expect(invoke).toHaveBeenCalledWith('browser_close', {
      request: { label: 'imperaos-browser-user' },
    }));
  });
});
