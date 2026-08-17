import { describe, expect, it } from 'vitest';

import {
  previewArtifact,
  previewConfigResolve,
  previewControlPlaneAgentList,
  previewControlPlaneSnapshot,
  previewHandshake,
  previewIdentity,
  previewRunDetail,
  previewRunReplay,
  previewRunSummary,
  previewSubmitResponse,
  previewTailEvents,
} from './previewFixtures';
import { DEFAULT_SETTINGS } from './settings';

describe('preview runtime paths', () => {
  it('uses ImperaOS preview hosts, windows, and team identifiers', () => {
    const settings = { ...DEFAULT_SETTINGS, rootDir: '.imperaos/preview/jobs' };
    const serialized = JSON.stringify([previewRunDetail(settings), previewTailEvents()]);
    const formerHost = ['preview.', 'ae', 'gis', '.local'].join('');
    const formerWindowTitle = ['Ae', 'gis', ' Preview Form'].join('');

    expect(serialized).toContain('imperaos-computer-use');
    expect(serialized).toContain('https://preview.imperaos.local/form');
    expect(serialized).toContain('ImperaOS Preview Form');
    expect(serialized).not.toContain(formerHost);
    expect(serialized).not.toContain(formerWindowTitle);
  });

  it('uses the canonical ImperaOS team runtime kind', () => {
    const agentList = previewControlPlaneAgentList();

    expect(agentList.agents[0].runtime_kind).toBe('imperaos_team');
  });

  it('serializes fixtures without legacy state paths and replaces the team root', () => {
    const legacyStateRoot = ['.', 'bin', 'liquid'].join('');
    const customRoot = '.imperaos/custom-preview/jobs';
    const settings = { ...DEFAULT_SETTINGS, rootDir: customRoot };
    const payloads = [
      previewHandshake(settings),
      previewSubmitResponse(settings),
      previewRunSummary(settings),
      previewRunDetail(settings),
      previewRunReplay(),
      previewArtifact(settings, 'job-ui-preview-1', 'audit_envelope.json'),
      previewConfigResolve(settings),
      previewIdentity(settings),
      previewControlPlaneSnapshot(settings),
    ];
    const serialized = JSON.stringify(payloads);

    expect(serialized).not.toContain(legacyStateRoot);
    expect(JSON.stringify(previewRunSummary(settings))).toContain(customRoot);
    expect(JSON.stringify(previewRunDetail(settings))).toContain(customRoot);
    expect(JSON.stringify(previewControlPlaneSnapshot(settings))).toContain(
      '.imperaos/control-plane',
    );
  });
});
