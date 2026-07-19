import type { ArtifactKind } from './artifactContracts';

const editorLoadFailures = new Map<ArtifactKind | 'unknown', number>();

export function recordArtifactEditorLoadFailure(kind: ArtifactKind | 'unknown'): void {
  editorLoadFailures.set(kind, (editorLoadFailures.get(kind) ?? 0) + 1);
}

export function artifactUiMetricSnapshot(): Array<{
  name: 'imperaos_artifact_editor_load_failure_total';
  labels: { kind: ArtifactKind | 'unknown' };
  value: number;
}> {
  return [...editorLoadFailures.entries()].map(([kind, value]) => ({
    name: 'imperaos_artifact_editor_load_failure_total',
    labels: { kind },
    value,
  }));
}

export function resetArtifactUiMetricsForTest(): void {
  editorLoadFailures.clear();
}
