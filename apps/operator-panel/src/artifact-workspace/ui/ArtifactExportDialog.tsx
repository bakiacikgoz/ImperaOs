import { useEffect, useRef, useState } from 'react';

export type ArtifactExportChoice = { value: string; label: string };

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${Math.ceil(value / 1024)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

export function ArtifactExportDialog({
  artifactTitle, formats, busy = false, suggestedFilename, revisionNumber,
  dataClass, policyState, estimatedSizeBytes, securityWarning, initialFormat,
  onCancel, onConfirm,
}: {
  artifactTitle: string;
  formats: ArtifactExportChoice[];
  busy?: boolean;
  suggestedFilename?: string;
  revisionNumber?: number;
  dataClass?: string;
  policyState?: string;
  estimatedSizeBytes?: number;
  securityWarning?: string;
  initialFormat?: string;
  onCancel: () => void;
  onConfirm: (format: string) => void;
}) {
  const [format, setFormat] = useState(
    formats.some((choice) => choice.value === initialFormat) ? initialFormat ?? '' : formats[0]?.value ?? '',
  );
  const dialogRef = useRef<HTMLDivElement>(null);
  const restoreFocusRef = useRef<HTMLElement | null>(null);
  const confirmRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    restoreFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    confirmRef.current?.focus();
  }, []);
  const cancel = () => {
    onCancel();
    queueMicrotask(() => restoreFocusRef.current?.focus());
  };

  return <div ref={dialogRef} className="artifact-export-dialog-backdrop" role="presentation" onMouseDown={(event) => {
    if (event.target === event.currentTarget && !busy) cancel();
  }}>
    <section className="artifact-export-dialog" role="dialog" aria-modal="true" aria-label={`Export ${artifactTitle}`} onKeyDown={(event) => {
      if (event.key === 'Escape' && !busy) { event.preventDefault(); cancel(); return; }
      if (event.key !== 'Tab') return;
      const focusable = Array.from(dialogRef.current?.querySelectorAll<HTMLButtonElement | HTMLSelectElement>('button:not(:disabled), select:not(:disabled)') ?? []);
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }}>
      <h3>Export {artifactTitle}</h3>
      <p>Your operating system will ask where to save the export. No path is stored in the workspace.</p>
      <dl className="artifact-export-dialog-summary">
        {suggestedFilename ? <div><dt>Suggested filename</dt><dd>{suggestedFilename}</dd></div> : null}
        {revisionNumber !== undefined ? <div><dt>Revision</dt><dd>Revision {revisionNumber}</dd></div> : null}
        {dataClass ? <div><dt>Data class</dt><dd>{dataClass}</dd></div> : null}
        {policyState ? <div><dt>Policy state</dt><dd>{policyState}</dd></div> : null}
        {estimatedSizeBytes !== undefined ? <div><dt>Estimated size</dt><dd>{formatBytes(estimatedSizeBytes)}</dd></div> : null}
      </dl>
      {securityWarning ? <p role="alert" className="artifact-workspace-banner">{securityWarning}</p> : null}
      <label>Export format
        <select aria-label="Export format" value={format} disabled={busy} onChange={(event) => setFormat(event.target.value)}>
          {formats.map((choice) => <option key={choice.value} value={choice.value}>{choice.label}</option>)}
        </select>
      </label>
      <div className="artifact-export-dialog-actions">
        <button type="button" disabled={busy} onClick={cancel}>Cancel export</button>
        <button ref={confirmRef} type="button" disabled={busy || !format} onClick={() => onConfirm(format)}>{busy ? 'Preparing export…' : 'Choose destination and export'}</button>
      </div>
    </section>
  </div>;
}
