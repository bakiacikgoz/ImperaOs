import { useEffect, useRef } from 'react';

import type { ArtifactDiffChange, ArtifactDiffResult } from '../artifactDiff';
import { Button } from '../../components/primitives/Button';

const LABELS: Record<ArtifactDiffChange, string> = {
  removed: 'Removed',
  added: 'Added',
  moved: 'Moved',
  changed: 'Changed',
};

export function ArtifactDiffView({
  beforeRevisionNumber,
  afterRevisionNumber,
  afterLabel,
  dirtyDraftExcluded,
  result,
  onClose,
}: {
  beforeRevisionNumber: number;
  afterRevisionNumber: number;
  afterLabel?: string;
  dirtyDraftExcluded: boolean;
  result: ArtifactDiffResult;
  onClose: () => void;
}) {
  const titleRef = useRef<HTMLHeadingElement>(null);
  useEffect(() => titleRef.current?.focus(), []);

  return (
    <section className="artifact-diff-view" role="region" aria-labelledby="artifact-diff-title">
      <header className="artifact-diff-head">
        <div>
          <h3 id="artifact-diff-title" ref={titleRef} tabIndex={-1}>Revision comparison</h3>
          <p>Before revision {beforeRevisionNumber} · {afterLabel ?? `After revision ${afterRevisionNumber}`}</p>
        </div>
        <Button variant="ghost" onClick={onClose}>Close comparison</Button>
      </header>
      <p role="status" aria-live="polite">
        {result.totalChangesIsLowerBound ? 'At least ' : ''}{result.totalChanges} changes across {result.inspectedItems} inspected items.
      </p>
      {dirtyDraftExcluded ? (
        <p className="artifact-workspace-banner">Unsaved draft is preserved and excluded from comparison.</p>
      ) : null}
      {result.truncated ? (
        <p className="artifact-workspace-banner" role="alert">
          {result.omittedChanges > 0 ? `${result.omittedChanges} change details omitted by the output limit. ` : ''}
          {result.totalChangesIsLowerBound ? 'Inspection stopped at the safety limit; totals are a lower bound.' : ''}
        </p>
      ) : null}
      {result.entries.length > 0 ? (
        <ol className="artifact-diff-list">
          {result.entries.map((entry, index) => (
            <li key={`${entry.change}:${entry.scope}:${entry.key}:${index}`}>
              <strong>{LABELS[entry.change]}</strong>
              <code>{entry.scope}:{entry.key}</code>
              {entry.fields?.length ? <span>Fields: {entry.fields.join(', ')}</span> : null}
            </li>
          ))}
        </ol>
      ) : result.totalChangesIsLowerBound ? (
        <p>No changes found in the inspected subset; uninspected content remains.</p>
      ) : <p>No persisted revision changes.</p>}
    </section>
  );
}
