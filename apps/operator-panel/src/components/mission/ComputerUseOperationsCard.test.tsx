import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { ComputerUseOperationsCard } from './ComputerUseOperationsCard';
import type {
  ComputerUseCapability,
  ComputerUseRuntimeChoice,
  ComputerUseVisionRuntimeCapability,
} from '../../capabilities';

const legacyCapability: ComputerUseCapability = {
  enabled: true,
  stage: 'execution_slice',
  platform: 'macos',
  scope: 'browser+desktop+file',
  executionModes: ['dry_run', 'step_approval', 'execute'],
  replayable: true,
  failClosed: true,
  adapterStatus: 'safari_applescript',
  reasonCode: 'MACOS_COMPUTER_USE_PILOT',
  summary: 'macOS pilot is enabled.',
};

const visionCapability: ComputerUseVisionRuntimeCapability = {
  enabled: false,
  stage: 'not_qualified',
  platform: 'macos',
  scope: 'vision_first_desktop_web_file',
  executionModes: ['dry_run', 'step_approval'],
  replayable: true,
  failClosed: true,
  reasonCode: 'MACOS_COMPUTER_USE_NOT_QUALIFIED',
  summary: 'Vision runtime is not qualified.',
  provider: {
    kind: 'none',
    configured: false,
    model: null,
  },
  safety: {
    rawScreenshotPersistence: 'disabled',
    terminalControl: 'deny',
    approvalRequiredForRiskyActions: true,
  },
  capabilityResolution: {
    schemaVersion: 1,
    platform: 'macos',
    profile: 'balanced',
    status: 'blocked',
    liveEnabled: false,
    supervisedLiveAllowed: false,
    publicLiveClaimAllowed: false,
    reasonCode: 'MACOS_COMPUTER_USE_NOT_QUALIFIED',
    blockers: ['COMPUTER_USE_EVIDENCE_MISSING'],
    evidence: {
      status: 'missing',
      source: 'none',
      fresh: false,
      commitMatch: false,
      configMatch: false,
      providerMatch: false,
      backendMatch: false,
    },
    config: {
      visionEnabled: false,
      provider: 'none',
      captureBackend: 'disabled',
      inputBackend: 'disabled',
      rawScreenshotPersistence: false,
      terminalPolicy: 'deny',
    },
    driver: {
      ready: false,
      captureReady: false,
      inputReady: false,
      permissionReady: false,
    },
    safety: {
      failClosed: true,
      rawScreenshotPersistenceAllowed: false,
      requiresStepApproval: true,
      sensitiveSurfaceStopEnabled: true,
    },
  },
  platforms: {},
};

const summary = {
  contractVersion: '3.0',
  counts: {
    success: 1,
    blocked: 2,
    failed: 0,
    stopped: 1,
    active: 0,
  },
  top_failure_codes: [{ code: 'approval_not_executed', count: 2 }],
  readiness_blockers: ['VISION_PROVIDER_UNAVAILABLE'],
};

function render(runtimeChoice: ComputerUseRuntimeChoice, overrides = {}) {
  return renderToStaticMarkup(
    <ComputerUseOperationsCard
      legacyCapability={legacyCapability}
      visionCapability={visionCapability}
      summary={summary}
      runtimeChoice={runtimeChoice}
      startAllowed={false}
      disabledReason="Computer-use live action disabled: MACOS_COMPUTER_USE_NOT_QUALIFIED"
      blockers={['MACOS_COMPUTER_USE_NOT_QUALIFIED']}
      onRuntimeChoiceChange={() => undefined}
      {...overrides}
    />,
  );
}

describe('ComputerUseOperationsCard', () => {
  it('renders unqualified reason codes, summary counts, and blockers', () => {
    const html = render('vision-first');

    expect(html).toContain('Computer-Use Operations');
    expect(html).toContain('Live gate blocked');
    expect(html).toContain('MACOS_COMPUTER_USE_NOT_QUALIFIED');
    expect(html).toContain('approval_not_executed');
    expect(html).toContain('VISION_PROVIDER_UNAVAILABLE');
    expect(html).toContain('Run doctor/preflight; do not start live automation.');
  });

  it('warns when legacy pilot is explicitly selected', () => {
    const html = render('legacy-pilot');

    expect(html).toContain('Legacy pilot selected.');
    expect(html).toContain('MACOS_COMPUTER_USE_PILOT');
  });

  it('warns on raw screenshot persistence drift', () => {
    const html = render('vision-first', {
      visionCapability: {
        ...visionCapability,
        safety: {
          ...visionCapability.safety,
          rawScreenshotPersistence: 'enabled',
        },
      },
    });

    expect(html).toContain('raw screenshot persistence drift');
  });
});
