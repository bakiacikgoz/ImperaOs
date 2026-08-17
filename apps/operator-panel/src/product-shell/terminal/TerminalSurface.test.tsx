import { screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const runtime = vi.hoisted(() => ({
  invoke: vi.fn(),
  listen: vi.fn(),
  sequence: [] as string[],
  writes: [] as Uint8Array[],
  outputHandler: undefined as undefined | ((event: { payload: { sessionId: string; data: string } }) => void),
  statusHandler: undefined as undefined | ((event: { payload: { sessionId: string; exitCode: number | null; signal: string | null } }) => void),
  dataHandler: undefined as undefined | ((data: string) => void),
}));

vi.mock('@tauri-apps/api/core', () => ({ invoke: runtime.invoke }));
vi.mock('@tauri-apps/api/event', () => ({ listen: runtime.listen }));
vi.mock('@xterm/addon-fit', () => ({
  FitAddon: class {
    fit() {}
  },
}));
vi.mock('@xterm/addon-search', () => ({
  SearchAddon: class {
    findNext(value: string) { return value === 'error'; }
    findPrevious(value: string) { return value === 'error'; }
  },
}));
vi.mock('@xterm/addon-web-links', () => ({ WebLinksAddon: class {} }));
vi.mock('@xterm/xterm', () => ({
  Terminal: class {
    cols = 80;
    rows = 24;
    loadAddon() {}
    open() {}
    writeln() {}
    write(value: Uint8Array) { runtime.writes.push(value); }
    onData(handler: (data: string) => void) {
      runtime.dataHandler = handler;
      return { dispose() {} };
    }
    dispose() {}
  },
}));

import { renderOperatorPanel } from '../../test/render';
import { TerminalSurface } from './TerminalSurface';

describe('TerminalSurface', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal('ResizeObserver', class {
      observe() {}
      disconnect() {}
    });
    runtime.sequence.length = 0;
    runtime.writes.length = 0;
    runtime.outputHandler = undefined;
    runtime.statusHandler = undefined;
    runtime.dataHandler = undefined;
    runtime.listen.mockImplementation(async (event: string, handler: typeof runtime.outputHandler | typeof runtime.statusHandler) => {
      runtime.sequence.push('listen');
      if (event === 'terminal://output') runtime.outputHandler = handler as typeof runtime.outputHandler;
      if (event === 'terminal://status') runtime.statusHandler = handler as typeof runtime.statusHandler;
      return () => undefined;
    });
    runtime.invoke.mockImplementation(async (command: string) => {
      if (command === 'terminal_start') {
        runtime.sequence.push('start');
        return { sessionId: 'terminal-1', shell: '/bin/zsh' };
      }
      return undefined;
    });
  });

  it('subscribes to native output before starting the PTY so initial output cannot race the listener', async () => {
    renderOperatorPanel(<TerminalSurface onClose={vi.fn()} />);

    await waitFor(() => expect(runtime.invoke).toHaveBeenCalledWith('terminal_start', {
      request: { mode: 'user', rootRef: undefined, cols: 80, rows: 24 },
    }));

    expect(runtime.sequence.at(0)).toBe('listen');
    expect(runtime.sequence.indexOf('listen')).toBeLessThan(runtime.sequence.indexOf('start'));
  });

  it('shows the exact native terminal denial returned as a Tauri string error', async () => {
    runtime.invoke.mockImplementation(async (command: string) => {
      if (command === 'terminal_start') {
        throw 'TERMINAL_DENIED: registered project root is unavailable';
      }
      return undefined;
    });

    renderOperatorPanel(<TerminalSurface onClose={vi.fn()} />);

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'TERMINAL_DENIED: registered project root is unavailable',
    );
  });

  it('buffers PTY output emitted before terminal_start returns the new session ID', async () => {
    runtime.invoke.mockImplementation(async (command: string) => {
      if (command === 'terminal_start') {
        runtime.outputHandler?.({
          payload: { sessionId: 'terminal-early', data: btoa('early prompt') },
        });
        return { sessionId: 'terminal-early', shell: '/bin/zsh' };
      }
      return undefined;
    });

    renderOperatorPanel(<TerminalSurface onClose={vi.fn()} />);

    await waitFor(() => expect(runtime.writes).toHaveLength(1));
    expect(new TextDecoder().decode(runtime.writes[0])).toBe('early prompt');
  });

  it('reports a native PTY exit instead of leaving a dead terminal looking active', async () => {
    renderOperatorPanel(<TerminalSurface onClose={vi.fn()} />);
    await waitFor(() => expect(runtime.statusHandler).toBeTypeOf('function'));

    runtime.statusHandler?.({
      payload: { sessionId: 'terminal-1', exitCode: 0, signal: null },
    });

    expect(await screen.findByRole('status')).toHaveTextContent('Terminal exited with code 0');
  });

  it('provides the UI Lab terminal search controls over the live xterm buffer', async () => {
    const { user } = renderOperatorPanel(<TerminalSurface onClose={vi.fn()} />);

    await user.type(screen.getByRole('searchbox', { name: 'Search terminal output' }), 'error');
    await user.click(screen.getByRole('button', { name: 'Find next' }));

    expect(await screen.findByRole('status')).toHaveTextContent('Terminal match found');
  });

  it('absorbs an idempotent native cleanup rejection after the PTY has already exited', async () => {
    const cleanupCatch = vi.fn();
    runtime.invoke.mockImplementation((command: string) => {
      if (command === 'terminal_start') {
        return Promise.resolve({ sessionId: 'terminal-exited', shell: '/bin/zsh' });
      }
      if (command === 'terminal_kill') {
        return { catch: cleanupCatch };
      }
      return Promise.resolve(undefined);
    });
    const { unmount } = renderOperatorPanel(<TerminalSurface onClose={vi.fn()} />);
    await waitFor(() => expect(runtime.invoke).toHaveBeenCalledWith('terminal_start', expect.anything()));

    unmount();
    expect(runtime.invoke).toHaveBeenCalledWith('terminal_kill', {
      request: { sessionId: 'terminal-exited' },
    });
    expect(cleanupCatch).toHaveBeenCalledOnce();
  });

  it('kills a PTY that finishes starting after its terminal tab has already unmounted', async () => {
    let resolveStart: ((value: { sessionId: string; shell: string }) => void) | undefined;
    runtime.invoke.mockImplementation((command: string) => {
      if (command === 'terminal_start') {
        return new Promise((resolve) => { resolveStart = resolve; });
      }
      return Promise.resolve(undefined);
    });
    const { unmount } = renderOperatorPanel(<TerminalSurface onClose={vi.fn()} />);
    await waitFor(() => expect(runtime.invoke).toHaveBeenCalledWith('terminal_start', expect.anything()));

    unmount();
    resolveStart?.({ sessionId: 'terminal-late', shell: '/bin/zsh' });

    await waitFor(() => expect(runtime.invoke).toHaveBeenCalledWith('terminal_kill', {
      request: { sessionId: 'terminal-late' },
    }));
  });

  it('reports a native PTY write rejection instead of producing an unhandled promise', async () => {
    runtime.invoke.mockImplementation(async (command: string) => {
      if (command === 'terminal_start') {
        return { sessionId: 'terminal-write', shell: '/bin/zsh' };
      }
      if (command === 'terminal_write') {
        throw 'TERMINAL_DENIED: terminal session is unknown';
      }
      return undefined;
    });
    renderOperatorPanel(<TerminalSurface onClose={vi.fn()} />);
    await waitFor(() => expect(runtime.dataHandler).toBeTypeOf('function'));

    runtime.dataHandler?.('echo test');

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'TERMINAL_DENIED: terminal session is unknown',
    );
  });
});
