import { useEffect, useRef, useState } from 'react';

import type { ArtifactConflict } from '../workspaceController';
import { Button } from '../../components/primitives/Button';

export function ArtifactConflictPanel({
  conflict,
  resolvingAction,
  comparisonOpen,
  onRefresh,
  onCompare,
  onReload,
  onFork,
}: {
  conflict: ArtifactConflict;
  resolvingAction: 'refresh' | 'reload' | 'fork' | null;
  comparisonOpen: boolean;
  onRefresh: () => void;
  onCompare: () => void;
  onReload: () => void;
  onFork: () => void;
}) {
  const [confirmReload, setConfirmReload] = useState(false);
  const confirmationRef = useRef<HTMLDialogElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const compareRef = useRef<HTMLButtonElement>(null);
  const reloadRef = useRef<HTMLButtonElement>(null);
  const reloadStatusRef = useRef<HTMLParagraphElement>(null);
  const reloadAttempted = useRef(false);
  const previousComparisonOpen = useRef(comparisonOpen);
  const previousResolvingAction = useRef(resolvingAction);
  const busy = resolvingAction !== null || conflict.status === 'loading';
  const backgroundActionsDisabled = busy || confirmReload;

  useEffect(() => {
    if (!confirmReload) return undefined;
    const dialog = confirmationRef.current;
    if (!dialog) return undefined;
    if (!dialog.open) {
      if (typeof dialog.showModal === 'function') dialog.showModal();
      else dialog.setAttribute('open', '');
    }
    return () => {
      if (dialog.open && typeof dialog.close === 'function') dialog.close();
    };
  }, [confirmReload]);
  useEffect(() => {
    if (confirmReload) cancelRef.current?.focus();
  }, [confirmReload]);
  useEffect(() => {
    if (previousComparisonOpen.current && !comparisonOpen) {
      compareRef.current?.focus();
    }
    previousComparisonOpen.current = comparisonOpen;
  }, [comparisonOpen]);
  useEffect(() => {
    if (confirmReload && resolvingAction === 'reload') {
      reloadStatusRef.current?.focus();
    }
    if (
      reloadAttempted.current
      && previousResolvingAction.current === 'reload'
      && resolvingAction === null
    ) {
      reloadAttempted.current = false;
      setConfirmReload(false);
      setTimeout(() => reloadRef.current?.focus(), 0);
    }
    previousResolvingAction.current = resolvingAction;
  }, [confirmReload, resolvingAction]);

  const cancelReload = () => {
    reloadAttempted.current = false;
    setConfirmReload(false);
    setTimeout(() => reloadRef.current?.focus(), 0);
  };

  return (
    <section className="artifact-conflict-panel" role="region" aria-labelledby="artifact-conflict-title" aria-busy={busy || undefined}>
      <h3 id="artifact-conflict-title">Revision conflict</h3>
      <p role="alert">Your local draft is preserved. ImperaOS will not merge or overwrite either version silently.</p>
      <p>Draft base revision {conflict.baseRevisionNumber}.</p>
      {conflict.status === 'loading' ? <p role="status">Loading latest remote revision…</p> : null}
      {conflict.status === 'error' ? (
        <>
          <p role="alert">{conflict.error ?? 'The latest remote revision is unavailable.'}</p>
          <Button variant="ghost" disabled={busy} onClick={onRefresh}>Retry loading latest</Button>
        </>
      ) : null}
      {conflict.status === 'ready' && conflict.remote ? (
        <>
          <p>Latest remote revision {conflict.remote.revision.revisionNumber}.</p>
          <div className="artifact-conflict-actions">
            <button ref={compareRef} type="button" disabled={backgroundActionsDisabled} onClick={onCompare}>Compare</button>
            <Button variant="ghost" disabled={backgroundActionsDisabled} onClick={onFork}>Fork local draft</Button>
            <button ref={reloadRef} type="button" disabled={backgroundActionsDisabled} onClick={() => setConfirmReload(true)}>
              Reload latest remote
            </button>
          </div>
        </>
      ) : null}
      {busy ? <p role="status">{resolvingAction === 'fork' ? 'Forking local draft…' : 'Loading latest remote revision…'}</p> : null}
      {confirmReload ? (
        <dialog
          className="artifact-conflict-confirmation"
          ref={confirmationRef}
          role="alertdialog"
          aria-modal="true"
          aria-labelledby="artifact-conflict-confirm-title"
          aria-describedby="artifact-conflict-confirm-description"
          onCancel={(event) => {
            event.preventDefault();
            if (!busy) cancelReload();
          }}
          onKeyDown={(event) => {
            if (event.key === 'Escape' && !busy) {
              event.preventDefault();
              event.stopPropagation();
              cancelReload();
              return;
            }
            if (event.key !== 'Tab') return;
            const focusable = Array.from(
              confirmationRef.current?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)') ?? [],
            );
            if (focusable.length === 0) return;
            const first = focusable[0];
            const last = focusable[focusable.length - 1];
            if (event.shiftKey && document.activeElement === first) {
              event.preventDefault();
              last.focus();
            } else if (!event.shiftKey && document.activeElement === last) {
              event.preventDefault();
              first.focus();
            }
          }}
        >
          <h4 id="artifact-conflict-confirm-title">Discard local draft?</h4>
          <p id="artifact-conflict-confirm-description">The latest remote revision will replace this unsaved local draft. Revision history is not rewritten.</p>
          {resolvingAction === 'reload' ? (
            <p ref={reloadStatusRef} role="status" tabIndex={-1}>Reloading latest remote revision…</p>
          ) : null}
          <button ref={cancelRef} type="button" disabled={busy} onClick={cancelReload}>Cancel</button>
          <Button
            variant="danger"
            disabled={busy}
            onClick={() => {
              reloadAttempted.current = true;
              onReload();
            }}
          >
            Discard draft and reload
          </Button>
        </dialog>
      ) : null}
    </section>
  );
}
