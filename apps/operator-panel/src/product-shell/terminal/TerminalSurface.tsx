import '@xterm/xterm/css/xterm.css';

import { FitAddon } from '@xterm/addon-fit';
import { SearchAddon } from '@xterm/addon-search';
import { WebLinksAddon } from '@xterm/addon-web-links';
import { Terminal } from '@xterm/xterm';
import { invoke } from '@tauri-apps/api/core';
import { listen } from '@tauri-apps/api/event';
import { useEffect, useRef, useState } from 'react';

import { nativeErrorMessage } from '../nativeErrorMessage';

type StartResponse = { sessionId: string; shell: string };
type OutputEvent = { sessionId: string; data: string };
type StatusEvent = { sessionId: string; exitCode: number | null; signal: string | null };

function decodeBase64(value: string): Uint8Array {
  return Uint8Array.from(atob(value), (character) => character.charCodeAt(0));
}

export function TerminalSurface({ active = true, onClose, projectRootRef, projectRootDisplayName }: { active?: boolean; onClose: () => void; projectRootRef?: string; projectRootDisplayName?: string }) {
  const hostRef = useRef<HTMLDivElement>(null);
  const sessionRef = useRef<string | null>(null);
  const activeRef = useRef(active);
  const searchAddonRef = useRef<SearchAddon | null>(null);
  const [error, setError] = useState('');
  const [terminalStatus, setTerminalStatus] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [searchStatus, setSearchStatus] = useState('');

  useEffect(() => { activeRef.current = active; }, [active]);

  useEffect(() => {
    if (!hostRef.current) return;
    const terminal = new Terminal({ cursorBlink: true, fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', theme: { background: '#0b1016', foreground: '#e8eef7' } });
    const fit = new FitAddon(); const search = new SearchAddon();
    searchAddonRef.current = search;
    terminal.loadAddon(fit);
    terminal.loadAddon(search);
    terminal.loadAddon(new WebLinksAddon((_event, uri) => {
      setSearchStatus(`Terminal link selected: ${uri}. Open it from the governed Browser surface.`);
    }));
    terminal.open(hostRef.current); fit.fit();
    const resize = new ResizeObserver(() => {
      if (!activeRef.current) return;
      fit.fit();
      if (sessionRef.current && terminal.cols > 0 && terminal.rows > 0) {
        void invoke('terminal_resize', {
          request: { sessionId: sessionRef.current, cols: terminal.cols, rows: terminal.rows },
        }).catch((cause) => setError(nativeErrorMessage(cause, 'Terminal resize failed.')));
      }
    });
    resize.observe(hostRef.current);
    let unlistenOutput: (() => void) | undefined;
    let unlistenStatus: (() => void) | undefined;
    let disposed = false;
    const pendingOutput: OutputEvent[] = [];
    const pendingStatus: StatusEvent[] = [];
    const reportStatus = (payload: StatusEvent) => {
      const suffix = payload.signal ? ` (${payload.signal})` : '';
      setTerminalStatus(`Terminal exited with code ${payload.exitCode ?? 'unknown'}${suffix}.`);
    };
    const start = async () => {
      try {
        [unlistenOutput, unlistenStatus] = await Promise.all([
          listen<OutputEvent>('terminal://output', ({ payload }) => {
            if (!sessionRef.current) {
              if (pendingOutput.length < 128) pendingOutput.push(payload);
              return;
            }
            if (payload.sessionId === sessionRef.current) terminal.write(decodeBase64(payload.data));
          }),
          listen<StatusEvent>('terminal://status', ({ payload }) => {
            if (!sessionRef.current) {
              if (pendingStatus.length < 16) pendingStatus.push(payload);
              return;
            }
            if (payload.sessionId === sessionRef.current) reportStatus(payload);
          }),
        ]);
        if (disposed) {
          unlistenOutput();
          unlistenStatus();
          return;
        }
        const session = await invoke<StartResponse>('terminal_start', { request: { mode: 'user', rootRef: projectRootRef, cols: terminal.cols || 80, rows: terminal.rows || 24 } });
        if (disposed) {
          void invoke('terminal_kill', {
            request: { sessionId: session.sessionId },
          }).catch(() => undefined);
          return;
        }
        sessionRef.current = session.sessionId; terminal.writeln(`\x1b[32mImperaOS terminal · ${session.shell}\x1b[0m`);
        pendingOutput
          .filter((payload) => payload.sessionId === session.sessionId)
          .forEach((payload) => terminal.write(decodeBase64(payload.data)));
        pendingOutput.length = 0;
        pendingStatus
          .filter((payload) => payload.sessionId === session.sessionId)
          .forEach(reportStatus);
        pendingStatus.length = 0;
      } catch (cause) {
        if (!disposed) setError(nativeErrorMessage(cause, 'Terminal unavailable.'));
      }
    };
    void start();
    const input = terminal.onData((data) => {
      if (sessionRef.current) {
        void invoke('terminal_write', {
          request: { sessionId: sessionRef.current, data },
        }).catch((cause) => setError(nativeErrorMessage(cause, 'Terminal write failed.')));
      }
    });
    return () => {
      disposed = true;
      input.dispose();
      resize.disconnect();
      unlistenOutput?.();
      unlistenStatus?.();
      searchAddonRef.current = null;
      if (sessionRef.current) {
        void invoke('terminal_kill', {
          request: { sessionId: sessionRef.current },
        }).catch(() => undefined);
      }
      terminal.dispose();
    };
  }, [projectRootRef]);

  const interrupt = () => {
    if (!sessionRef.current) return;
    void invoke('terminal_interrupt', { request: { sessionId: sessionRef.current } })
      .catch((cause) => setError(nativeErrorMessage(cause, 'Terminal interrupt failed.')));
  };
  const find = (direction: 'next' | 'previous') => {
    const query = searchQuery.trim();
    if (!query || !searchAddonRef.current) return;
    const matched = direction === 'next'
      ? searchAddonRef.current.findNext(query)
      : searchAddonRef.current.findPrevious(query);
    setSearchStatus(matched ? 'Terminal match found.' : 'No terminal match found.');
  };

  return <section className="terminal-view native-terminal-surface" aria-label="Governed terminal"><header><strong>Terminal</strong><input type="search" aria-label="Search terminal output" value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} /><button type="button" disabled={!searchQuery.trim()} onClick={() => find('previous')}>Find previous</button><button type="button" disabled={!searchQuery.trim()} onClick={() => find('next')}>Find next</button><button type="button" disabled={Boolean(terminalStatus)} onClick={interrupt}>Interrupt</button><button type="button" onClick={onClose}>Close</button></header><p className="ps-muted">User PTY · {projectRootRef ? `registered project root (${projectRootDisplayName || 'project'})` : 'verified ImperaOS runtime workspace'} · agent input denied</p>{error ? <p role="alert">{error}</p> : null}{terminalStatus ? <p role="status">{terminalStatus}</p> : null}{searchStatus ? <p role="status">{searchStatus}</p> : null}<div className="terminal-host" ref={hostRef} /></section>;
}
