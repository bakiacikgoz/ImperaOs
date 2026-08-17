import type { AssistantArtifactRef, AssistantRunRef } from '../../assistant/assistantTypes';
import { assistantUiText, translateAssistantText, type UiLocale } from '../../i18n';
import { Badge } from '../primitives/Badge';
import { Card } from '../primitives/Card';
import { StatusDot } from '../primitives/StatusDot';

export function AssistantRunReferences({
  runs,
  artifacts,
  emptyRunLabel,
  locale = 'en',
  onOpenArtifact,
}: {
  runs: AssistantRunRef[];
  artifacts: AssistantArtifactRef[];
  emptyRunLabel: string;
  locale?: UiLocale;
  onOpenArtifact?: (artifactId: string) => void;
}) {
  const text = assistantUiText[locale];
  if (runs.length === 0 && artifacts.length === 0) {
    return <span className="sr-only">{emptyRunLabel}</span>;
  }

  return (
    <Card className="assistant-reference-card">
      <div className="assistant-card-head">
        <span className="assistant-card-label">{text.referencedRuns}</span>
        <Badge tone={runs.length > 0 || artifacts.length > 0 ? 'info' : 'neutral'}>
          {runs.length + artifacts.length}
        </Badge>
      </div>
      <div className="assistant-reference-list">
        {runs.map((run) => (
          <div className="assistant-reference-row" key={run.id}>
            <StatusDot tone={run.status === 'blocked' ? 'warning' : 'info'} />
            <span>
              <strong>{run.id}</strong>
              <em>{translateAssistantText(run.summary || run.status || 'Referenced run', locale)}</em>
            </span>
          </div>
        ))}
        {artifacts.map((artifact) => {
          const content = (
            <>
              <StatusDot tone="success" />
              <span>
                <strong>{artifact.name}</strong>
                <em>{translateAssistantText(artifact.summary || artifact.path || 'Referenced artifact', locale)}</em>
              </span>
            </>
          );
          return artifact.artifactId && artifact.openable === true && onOpenArtifact ? (
            <button
              type="button"
              className="assistant-reference-row"
              aria-label={`Open ${artifact.name}`}
              key={`${artifact.artifactId}-${artifact.revisionId ?? ''}`}
              onClick={() => onOpenArtifact(artifact.artifactId as string)}
            >
              {content}
            </button>
          ) : (
            <div className="assistant-reference-row" key={`${artifact.name}-${artifact.path ?? ''}`}>
              {content}
            </div>
          );
        })}
      </div>
    </Card>
  );
}
