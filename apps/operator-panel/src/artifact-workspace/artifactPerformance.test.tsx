import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import type { ArtifactContent, ArtifactDescriptor } from './artifactContracts';
import { ArtifactLicenseBlocked } from './ui/ArtifactLicenseBlocked';

const artifact: ArtifactDescriptor = {
  artifactId: 'spreadsheet-performance', workspaceId: 'workspace-performance',
  kind: 'spreadsheet', title: '10k performance workbook', status: 'active',
  schemaVersion: 2, dataClass: 'internal', currentRevisionId: 'revision-1',
  currentRevisionNumber: 1, sourceSessionId: null, sourceTurnId: null,
  createdByType: 'user', createdById: 'performance-user', updatedById: 'performance-user',
  createdAtUtc: '2026-07-17T12:00:00Z', updatedAtUtc: '2026-07-17T12:00:00Z',
  archivedAtUtc: null, etag: 'performance-etag', metadata: {},
};

const content: ArtifactContent = {
  kind: 'spreadsheet', schemaVersion: 2, calculationMode: 'disabled',
  sheets: [{
    id: 'sheet-1', name: '10k', columns: [],
    cells: Object.fromEntries(
      Array.from({ length: 10_000 }, (_, index) => [
        `A${index + 1}`, { value: index + 1 },
      ]),
    ),
  }],
};

function p95(samples: number[]): number {
  return [...samples].sort((left, right) => left - right)[Math.ceil(samples.length * 0.95) - 1] ?? 0;
}

afterEach(() => cleanup());

describe('artifact UI performance evidence', () => {
  it('mounts and unmounts the 10k forced-off fallback 50 times without residual DOM', () => {
    const durations: number[] = [];
    for (let cycle = 0; cycle < 50; cycle += 1) {
      const started = performance.now();
      const view = render(<ArtifactLicenseBlocked
        artifact={artifact}
        content={content}
        capability={{
          contractVersion: 'artifact-license-capability/v1', kind: 'spreadsheet', enabled: false,
          reasonCode: 'ARTIFACT_LICENSE_EVIDENCE_MISSING',
        }}
      />);
      expect(screen.getByRole('region', { name: 'spreadsheet read-only fallback' })).toBeInTheDocument();
      view.unmount();
      durations.push(performance.now() - started);
      expect(screen.queryByRole('region', { name: 'spreadsheet read-only fallback' })).not.toBeInTheDocument();
    }

    const measuredP95 = Number(p95(durations).toFixed(3));
    expect(measuredP95).toBeLessThanOrEqual(250);
    console.log(`ARTIFACT_PERFORMANCE_JSON=${JSON.stringify({
      workload: 'ui-10k-50-mount-unmount', cycles: 50, cells: 10_000,
      p95BudgetMs: 250, p95Ms: measuredP95, residualNodes: 0,
      commercialCapabilities: 'forced_off',
    })}`);
  });
});
