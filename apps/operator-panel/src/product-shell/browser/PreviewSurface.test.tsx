import { screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const invoke = vi.hoisted(() => vi.fn());

vi.mock('@tauri-apps/api/core', () => ({ invoke }));

import { renderOperatorPanel } from '../../test/render';
import { PreviewSurface } from './PreviewSurface';

describe('PreviewSurface', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('owns and closes its registered native preview session', async () => {
    invoke.mockImplementation(async (command: string) => {
      if (command === 'browser_list_preview_origins') return ['http://localhost:5173'];
      if (command === 'browser_open') return 'imperaos-browser-preview';
      if (command === 'browser_history_state') return { canBack: false, canForward: false };
      return undefined;
    });
    const onClose = vi.fn();
    const { user, container } = renderOperatorPanel(<PreviewSurface taskId="task-1" onClose={onClose} />);

    expect(container.querySelector('.preview-surface .preview-browser')).toBeInTheDocument();
    expect(container.querySelector('.preview-hero.native-preview-viewport')).toBeInTheDocument();
    await screen.findByRole('option', { name: 'http://localhost:5173' });
    await user.click(screen.getByRole('button', { name: 'Open preview' }));
    await user.click(screen.getByRole('button', { name: 'Close' }));

    expect(invoke).toHaveBeenCalledWith('browser_open', {
      request: { mode: 'preview', url: 'http://localhost:5173', taskId: 'task-1' },
    });
    expect(invoke).toHaveBeenCalledWith('browser_close', {
      request: { label: 'imperaos-browser-preview' },
    });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('shows the exact native registry error returned as a Tauri string error', async () => {
    invoke.mockRejectedValueOnce('BROWSER_POLICY_DENIED: preview registry unavailable');

    renderOperatorPanel(<PreviewSurface taskId="task-1" onClose={vi.fn()} />);

    expect(await screen.findByRole('status')).toHaveTextContent(
      'BROWSER_POLICY_DENIED: preview registry unavailable',
    );
  });

  it('does not expose renderer-driven preview registration', async () => {
    invoke.mockImplementation(async (command: string) => {
      if (command === 'browser_list_preview_origins') return [];
      return undefined;
    });
    renderOperatorPanel(
      <PreviewSurface taskId="task-1" onClose={vi.fn()} />,
    );

    expect(screen.queryByRole('textbox', { name: 'Local preview origin' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Verify runtime' })).not.toBeInTheDocument();
    expect(invoke).not.toHaveBeenCalledWith('browser_register_preview_origin', expect.anything());
    expect(screen.getByText(/Only ImperaOS runtime-owned/)).toBeInTheDocument();
  });

  it('closes a native preview session that finishes opening after the tab unmounts', async () => {
    let resolveOpen: ((label: string) => void) | undefined;
    invoke.mockImplementation((command: string) => {
      if (command === 'browser_list_preview_origins') return Promise.resolve(['http://localhost:4173']);
      if (command === 'browser_open') {
        return new Promise((resolve) => { resolveOpen = resolve; });
      }
      return Promise.resolve(undefined);
    });
    const { user, unmount } = renderOperatorPanel(<PreviewSurface taskId="task-1" onClose={vi.fn()} />);
    await screen.findByRole('option', { name: 'http://localhost:4173' });

    await user.click(screen.getByRole('button', { name: 'Open preview' }));
    unmount();
    resolveOpen?.('imperaos-preview-late');

    await waitFor(() => expect(invoke).toHaveBeenCalledWith('browser_close', {
      request: { label: 'imperaos-preview-late' },
    }));
  });

  it('does not create duplicate native preview sessions while an open is pending', async () => {
    let resolveOpen: ((label: string) => void) | undefined;
    invoke.mockImplementation((command: string) => {
      if (command === 'browser_list_preview_origins') return Promise.resolve(['http://localhost:4173']);
      if (command === 'browser_open') {
        return new Promise((resolve) => { resolveOpen = resolve; });
      }
      return Promise.resolve(undefined);
    });
    const { user } = renderOperatorPanel(<PreviewSurface taskId="task-1" onClose={vi.fn()} />);
    const openButton = await screen.findByRole('button', { name: 'Open preview' });

    await user.click(openButton);
    await user.click(openButton);

    expect(invoke.mock.calls.filter(([command]) => command === 'browser_open')).toHaveLength(1);
    resolveOpen?.('imperaos-preview-one');
  });

  it('closes an already-open native session when the owning workspace tab unmounts', async () => {
    invoke.mockImplementation(async (command: string) => {
      if (command === 'browser_list_preview_origins') return ['http://localhost:4173'];
      if (command === 'browser_open') return 'imperaos-preview-open';
      return undefined;
    });
    const { user, unmount } = renderOperatorPanel(<PreviewSurface taskId="task-1" onClose={vi.fn()} />);
    await screen.findByRole('option', { name: 'http://localhost:4173' });
    await user.click(screen.getByRole('button', { name: 'Open preview' }));
    await waitFor(() => expect(screen.getByText(/Opened only the runtime-registered/)).toBeInTheDocument());

    unmount();

    await waitFor(() => expect(invoke).toHaveBeenCalledWith('browser_close', {
      request: { label: 'imperaos-preview-open' },
    }));
  });
});
