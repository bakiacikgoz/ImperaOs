import { describe, expect, it } from 'vitest';

import { resolveArtifactFeatureFlags, resolveEffectiveArtifactFeatureFlags } from './artifactFeatureFlags';

describe('artifact feature flags', () => {
  it('keeps every surface off when the global authority is off', () => {
    const flags = resolveArtifactFeatureFlags({
      VITE_ARTIFACT_WORKSPACE: '0',
      VITE_ARTIFACT_DOCUMENT_EDITOR: '1',
      VITE_ARTIFACT_FORM_EDITOR: '1',
    });
    expect(Object.values(flags).every((value) => value === false)).toBe(true);
  });

  it('never lets renderer flags forge commercial license capability', () => {
    const flags = resolveArtifactFeatureFlags(
      {
        VITE_ARTIFACT_WORKSPACE: '1',
        VITE_ARTIFACT_DOCUMENT_EDITOR: '1',
        VITE_ARTIFACT_SPREADSHEET_EDITOR: '1',
        VITE_ARTIFACT_CANVAS_EDITOR: '1',
      },
      { spreadsheet: false, canvas: false },
    );
    expect(flags.workspace).toBe(true);
    expect(flags.document).toBe(true);
    expect(flags.spreadsheet).toBe(false);
    expect(flags.canvas).toBe(false);
  });

  it('fails closed until backend authority is successfully known', () => {
    const renderer = resolveArtifactFeatureFlags({
      VITE_ARTIFACT_WORKSPACE: '1',
      VITE_ARTIFACT_DOCUMENT_EDITOR: '1',
      VITE_ARTIFACT_EXPORT: '1',
    });
    expect(Object.values(resolveEffectiveArtifactFeatureFlags(renderer, null)).every((value) => value === false)).toBe(true);
    expect(resolveEffectiveArtifactFeatureFlags(renderer, {
      globalEnabled: true,
      features: {
        'artifact_workspace.document.enabled': true,
        'artifact_workspace.export.enabled': true,
      },
    })).toMatchObject({ workspace: true, document: true, export: true });
  });
});
