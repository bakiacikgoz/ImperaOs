import type { ArtifactContextSelection } from '../selectionContext';
import { contextSelectionLabel } from '../selectionContext';

export function ArtifactSelectionChip({ selection }: { selection: ArtifactContextSelection | null }) {
  return (
    <p
      className="artifact-workspace-selection-status"
      role="status"
      aria-label="Artifact selection"
      aria-live="polite"
    >
      {contextSelectionLabel(selection)}
    </p>
  );
}
