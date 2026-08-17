import { invoke } from '@tauri-apps/api/core';
import { ChevronLeft, ChevronRight, ExternalLink, RotateCw, X } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import { nativeErrorMessage } from '../nativeErrorMessage';

type BrowserHistoryState = { canBack: boolean; canForward: boolean };

const emptyHistory: BrowserHistoryState = { canBack: false, canForward: false };

function normalizeHistory(value: unknown): BrowserHistoryState {
  if (typeof value !== 'object' || value === null) return emptyHistory;
  const record = value as Record<string, unknown>;
  return {
    canBack: record.canBack === true,
    canForward: record.canForward === true,
  };
}

export function BrowserSurface({ active = true, onClose, sessionLabel: persistedSessionLabel, onSessionChange }: { active?: boolean; onClose: () => void; sessionLabel?: string; onSessionChange?: (sessionLabel: string | null) => void }) {
  const [address, setAddress] = useState('https://');
  const [ownedSessionLabel, setOwnedSessionLabel] = useState<string | null>(null);
  const [history, setHistory] = useState<BrowserHistoryState>(emptyHistory);
  const [status, setStatus] = useState('');
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const openingRef = useRef(false);
  const disposedRef = useRef(false);
  const [opening, setOpening] = useState(false);
  const sessionLabel = persistedSessionLabel ?? ownedSessionLabel;
  const sessionLabelRef = useRef<string | null>(sessionLabel);
  sessionLabelRef.current = sessionLabel;
  const setSessionLabel = (next: string | null) => {
    sessionLabelRef.current = next;
    setOwnedSessionLabel(next);
    onSessionChange?.(next);
  };

  const refreshHistory = async (label = sessionLabel) => {
    if (!label) { setHistory(emptyHistory); return; }
    const next = await invoke<unknown>('browser_history_state', { request: { label } });
    setHistory(normalizeHistory(next));
  };
  const open = async () => {
    if (openingRef.current || disposedRef.current) return;
    openingRef.current = true;
    setOpening(true);
    try {
      if (sessionLabel) {
        await invoke('browser_navigate', { request: { label: sessionLabel, url: address } });
        if (disposedRef.current) return;
        await refreshHistory(sessionLabel);
        setStatus(`Navigated governed browser: ${sessionLabel}`);
      } else {
        const label = await invoke<string>('browser_open', { request: { mode: 'user', url: address } });
        if (disposedRef.current) {
          void invoke('browser_close', { request: { label } }).catch(() => undefined);
          return;
        }
        setSessionLabel(label);
        setHistory(emptyHistory);
        setStatus(`Opened native browser: ${label}`);
      }
    } catch (cause) {
      if (!disposedRef.current) setStatus(nativeErrorMessage(cause, 'Browser navigation failed.'));
    } finally {
      openingRef.current = false;
      if (!disposedRef.current) setOpening(false);
    }
  };
  const move = async (direction: 'back' | 'forward') => {
    if (!sessionLabel) return;
    try {
      await invoke(direction === 'back' ? 'browser_back' : 'browser_forward', { request: { label: sessionLabel } });
      await refreshHistory(sessionLabel);
      setStatus(`Navigated ${direction} through governed browser history.`);
    } catch (cause) { setStatus(nativeErrorMessage(cause, 'Browser history navigation failed.')); }
  };
  const close = () => {
    disposedRef.current = true;
    const label = sessionLabelRef.current;
    if (label) void invoke('browser_close', { request: { label } }).catch(() => undefined);
    setSessionLabel(null);
    onClose();
  };
  const reload = () => {
    if (!sessionLabel) return;
    void invoke('browser_reload', { request: { label: sessionLabel } })
      .catch((cause) => setStatus(nativeErrorMessage(cause, 'Browser reload failed.')));
  };

  useEffect(() => {
    disposedRef.current = false;
    return () => {
      disposedRef.current = true;
      const label = sessionLabelRef.current;
      queueMicrotask(() => {
        if (!disposedRef.current || !label || sessionLabelRef.current !== label) return;
        sessionLabelRef.current = null;
        void invoke('browser_close', { request: { label } }).catch(() => undefined);
      });
    };
  }, []);

  useEffect(() => {
    if (!sessionLabel) return;
    void refreshHistory(sessionLabel).catch((cause) => setStatus(nativeErrorMessage(cause, 'Browser history is unavailable.')));
  }, [sessionLabel]);

  useEffect(() => {
    if (!sessionLabel || !active || !viewportRef.current) return;
    let mounted = true;
    const synchronize = () => {
      const viewport = viewportRef.current;
      if (!mounted || !viewport) return;
      const bounds = viewport.getBoundingClientRect();
      if (bounds.width <= 0 || bounds.height <= 0) return;
      const request = {
        label: sessionLabel,
        x: Math.round(bounds.x), y: Math.round(bounds.y),
        width: Math.round(bounds.width), height: Math.round(bounds.height),
      };
      void invoke('browser_set_bounds', { request })
        .then(() => invoke('browser_show', { request: { label: sessionLabel } }))
        .catch((cause) => { if (mounted) setStatus(nativeErrorMessage(cause, 'Browser viewport could not be synchronized.')); });
    };
    synchronize();
    const observer = typeof ResizeObserver === 'undefined' ? undefined : new ResizeObserver(synchronize);
    observer?.observe(viewportRef.current);
    window.addEventListener('resize', synchronize);
    return () => {
      mounted = false;
      observer?.disconnect();
      window.removeEventListener('resize', synchronize);
      void invoke('browser_hide', { request: { label: sessionLabel } });
    };
  }, [active, sessionLabel]);

  return (
    <section className="browser-surface" aria-label="Native browser">
      <div className="browser-toolbar">
        <button type="button" aria-label="Back" disabled={!sessionLabel || !history.canBack} onClick={() => void move('back')}><ChevronLeft size={16} /></button>
        <button type="button" aria-label="Forward" disabled={!sessionLabel || !history.canForward} onClick={() => void move('forward')}><ChevronRight size={16} /></button>
        <button type="button" aria-label="Reload" disabled={!sessionLabel} onClick={reload}><RotateCw size={15} /></button>
        <form className="browser-address-bar" onSubmit={(event) => { event.preventDefault(); void open(); }}>
          <span className="browser-lock" aria-hidden="true">●</span>
          <input
            aria-label="Browser address"
            value={address}
            onChange={(event) => setAddress(event.target.value)}
            autoCapitalize="none"
            autoCorrect="off"
            inputMode="url"
            spellCheck={false}
          />
          <button type="submit" disabled={opening}>{opening ? 'Opening…' : sessionLabel ? 'Navigate HTTPS' : 'Open HTTPS'}<ExternalLink size={14} /></button>
        </form>
        <button type="button" aria-label="Close" onClick={close}><X size={16} /></button>
      </div>
      <div ref={viewportRef} className="browser-page native-browser-viewport" aria-label="Browser page viewport" />
      {status ? <p className="native-surface-status" role="status">{status}</p> : null}
      <p className="native-policy-note">User mode opens only explicitly entered HTTPS URLs. Each explicit history target and every redirect is revalidated by native policy.</p>
    </section>
  );
}
