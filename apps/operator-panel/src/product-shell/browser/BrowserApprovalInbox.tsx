import { invoke, isTauri } from '@tauri-apps/api/core';
import { listen } from '@tauri-apps/api/event';
import { useEffect, useState } from 'react';

type BrowserMode = 'user' | 'preview' | 'agent';
type BrowserApprovalRequest = {
  kind: 'new_window' | 'download' | 'external_application';
  url: string;
  mode: BrowserMode;
  taskId?: string | null;
  sourceSessionLabel?: string | null;
};

export function BrowserApprovalInbox() {
  const [request, setRequest] = useState<BrowserApprovalRequest | null>(null);
  const [status, setStatus] = useState('');

  useEffect(() => {
    if (!isTauri()) return;
    let unlisten: (() => void) | undefined;
    void listen<BrowserApprovalRequest>('browser://approval-required', (event) => {
      setStatus('');
      setRequest(event.payload);
      if (event.payload.sourceSessionLabel) {
        void invoke('browser_hide', { request: { label: event.payload.sourceSessionLabel } });
      }
    }).then((dispose) => { unlisten = dispose; });
    return () => unlisten?.();
  }, []);

  if (!request) return status ? <p className="ps-browser-status" role="status">{status}</p> : null;

  const openApprovedWindow = async () => {
    try {
      if (!request.sourceSessionLabel) throw new Error('The governed browser tab is no longer available.');
      await invoke('browser_navigate', {
        request: { label: request.sourceSessionLabel, url: request.url },
      });
      await invoke('browser_show', { request: { label: request.sourceSessionLabel } });
      setStatus('Approved popup opened in the governed browser tab.');
    } catch (cause) {
      setStatus(cause instanceof Error ? cause.message : 'Browser approval could not be completed.');
    } finally {
      setRequest(null);
    }
  };
  const dismiss = () => {
    if (request.sourceSessionLabel) {
      void invoke('browser_show', { request: { label: request.sourceSessionLabel } });
    }
    setRequest(null);
  };

  const isPopup = request.kind === 'new_window';
  const title = isPopup
    ? 'A new browser window needs your approval.'
    : request.kind === 'download'
      ? 'A download needs your approval.'
      : 'An external application needs your approval.';

  return <div className="browser-approval-backdrop"><section className="browser-approval-modal" role="alertdialog" aria-label="Browser approval required">
      <strong>{title}</strong>
      <code>{request.url}</code>
      <p>{isPopup
        ? 'The popup was blocked until you explicitly approve opening it in the governed browser tab.'
        : request.kind === 'download'
          ? 'Browser downloads stay blocked until ImperaOS has a governed save-and-approval workflow.'
          : 'External applications stay blocked; no operating-system application will be opened from the browser.'}</p>
      <div>
        {isPopup ? <button type="button" onClick={() => void openApprovedWindow()}>Approve and open</button> : null}
        <button type="button" onClick={dismiss}>{isPopup ? 'Deny' : 'Acknowledge and keep blocked'}</button>
      </div>
    </section></div>;
}
