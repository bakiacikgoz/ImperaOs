import type { ArtifactContent, ArtifactDescriptor, ArtifactLicenseCapability } from '../artifactContracts';

type Props = {
  artifact: ArtifactDescriptor;
  content: ArtifactContent;
  capability: ArtifactLicenseCapability;
  onExport?(format: 'json' | 'svg' | 'png' | 'csv' | 'xlsx'): void;
};

function boundedArtifactSummary(content: ArtifactContent): string {
  let remainingNodes = 256;
  const sample = (value: unknown, depth: number): unknown => {
    if (remainingNodes <= 0) return '[truncated]';
    remainingNodes -= 1;
    if (typeof value === 'string') {
      return value.length <= 512 ? value : `${value.slice(0, 512)}…`;
    }
    if (value === null || typeof value !== 'object') return value;
    if (depth >= 4) return '[truncated]';
    if (Array.isArray(value)) {
      const result = value.slice(0, 16).map((item) => sample(item, depth + 1));
      if (value.length > 16) result.push(`[${value.length - 16} more items]`);
      return result;
    }
    const result: Record<string, unknown> = {};
    let observed = 0;
    for (const key in value) {
      if (!Object.prototype.hasOwnProperty.call(value, key)) continue;
      if (observed >= 16) {
        result['…'] = '[more fields]';
        break;
      }
      result[key] = sample((value as Record<string, unknown>)[key], depth + 1);
      observed += 1;
    }
    return result;
  };
  const encoded = JSON.stringify(sample(content, 0), null, 2);
  return encoded.length <= 8_192 ? encoded : `${encoded.slice(0, 8_192)}\n…`;
}

export function ArtifactReadOnlyContent({ artifact, content }: { artifact: ArtifactDescriptor; content: ArtifactContent }) {
  return <section aria-label={`${artifact.kind} bounded read-only content`}>
    <strong>{artifact.title}</strong>
    <pre aria-label={`${artifact.kind} bounded content summary`}>{boundedArtifactSummary(content)}</pre>
  </section>;
}

export function ArtifactLicenseBlocked({ artifact, content, capability, onExport }: Props) {
  return (
    <section className="artifact-license-blocked" aria-label={`${artifact.kind} read-only fallback`}>
      <div className="artifact-workspace-banner" role="status">
        <strong>Licensed editor unavailable</strong>
        <span>{capability.reasonCode}</span>
      </div>
      <p>
        This artifact remains readable, archived history remains available, and only verified safe
        export actions are offered. Editing, paste, save, and AI apply are disabled.
      </p>
      <pre aria-label={`${artifact.kind} bounded content summary`}>{boundedArtifactSummary(content)}</pre>
      {artifact.kind === 'canvas' && onExport ? (
        <div role="group" aria-label="Canvas safe exports">
          <button type="button" onClick={() => onExport('json')}>Export JSON</button>
          {artifact.schemaVersion === 2 ? (
            <>
              <button type="button" onClick={() => onExport('svg')}>Export SVG</button>
              <button type="button" onClick={() => onExport('png')}>Export PNG</button>
            </>
          ) : null}
        </div>
      ) : null}
      {artifact.kind === 'spreadsheet' ? (
        <p>Use the verified sheet-specific CSV or complete-workbook XLSX actions below.</p>
      ) : null}
    </section>
  );
}
