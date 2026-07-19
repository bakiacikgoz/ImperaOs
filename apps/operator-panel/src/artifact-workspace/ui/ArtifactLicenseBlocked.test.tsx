import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { ArtifactLicenseBlocked } from './ArtifactLicenseBlocked';

const artifact = {
  artifactId: 'canvas-1', workspaceId: 'workspace-1', kind: 'canvas' as const, title: 'Board',
  status: 'active' as const, schemaVersion: 1, dataClass: 'internal' as const,
  currentRevisionId: 'revision-1', currentRevisionNumber: 1, sourceSessionId: null,
  sourceTurnId: null, createdByType: 'user' as const, createdById: 'user-1',
  updatedById: 'user-1', createdAtUtc: '2026-07-16T08:00:00Z',
  updatedAtUtc: '2026-07-16T08:00:00Z', archivedAtUtc: null, etag: 'etag', metadata: {},
};

describe('ArtifactLicenseBlocked', () => {
  it('samples only a fixed structural budget before encoding the preview', () => {
    const content = {
      kind: 'canvas', schemaVersion: 1,
      snapshot: { records: Array.from({ length: 100_000 }, (_, index) => ({ id: `shape-${index}` })) },
      assetIds: [], embeds: 'deny', remoteAssets: 'deny',
    } as const;
    render(<ArtifactLicenseBlocked
      artifact={artifact}
      content={content as never}
      capability={{
        contractVersion: 'artifact-license-capability/v1', kind: 'canvas', enabled: false,
        reasonCode: 'ARTIFACT_LICENSE_EVIDENCE_MISSING',
      }}
    />);
    const summary = screen.getByLabelText('canvas bounded content summary').textContent ?? '';
    expect(summary.length).toBeLessThanOrEqual(8_194);
    expect(summary).toContain('99984 more items');
    expect(summary).not.toContain('shape-99999');
  });

  it('offers JSON only for a legacy canvas revision', async () => {
    const onExport = vi.fn();
    render(<ArtifactLicenseBlocked
      artifact={artifact}
      content={{ kind: 'canvas', schemaVersion: 1, snapshot: {}, assetIds: [], embeds: 'deny', remoteAssets: 'deny' }}
      capability={{
        contractVersion: 'artifact-license-capability/v1', kind: 'canvas', enabled: false,
        reasonCode: 'ARTIFACT_LICENSE_EVIDENCE_MISSING',
      }}
      onExport={onExport}
    />);
    expect(screen.getByRole('status')).toHaveTextContent('ARTIFACT_LICENSE_EVIDENCE_MISSING');
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /edit|save|paste/i })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Export JSON' }));
    expect(onExport).toHaveBeenNthCalledWith(1, 'json');
    expect(screen.queryByRole('button', { name: 'Export SVG' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Export PNG' })).not.toBeInTheDocument();
  });

  it('offers JSON, SVG, and PNG for a strict canvas v2 revision', async () => {
    const onExport = vi.fn();
    render(<ArtifactLicenseBlocked
      artifact={{ ...artifact, schemaVersion: 2 }}
      content={{
        kind: 'canvas', schemaVersion: 2, snapshot: { objects: [] }, assetIds: [],
        embeds: 'deny', remoteAssets: 'deny',
      }}
      capability={{
        contractVersion: 'artifact-license-capability/v1', kind: 'canvas', enabled: false,
        reasonCode: 'ARTIFACT_LICENSE_EVIDENCE_MISSING',
      }}
      onExport={onExport}
    />);
    await userEvent.click(screen.getByRole('button', { name: 'Export SVG' }));
    await userEvent.click(screen.getByRole('button', { name: 'Export PNG' }));
    expect(onExport).toHaveBeenNthCalledWith(1, 'svg');
    expect(onExport).toHaveBeenNthCalledWith(2, 'png');
  });
});
