import { describe, expect, it } from 'vitest';

import {
  getComputerUseCapability,
  getComputerUseVisionRuntimeBlockers,
  getComputerUseVisionRuntimeCapability,
  hasContractMismatch,
  isComputerUseLiveEnabled,
  isComputerUseSessionStartAllowed,
  isComputerUseVisionRuntimeLiveEnabled,
} from './capabilities';

const baseCommands = {
  computerUseSubmit: true,
  computerUsePause: true,
  computerUseResume: true,
  computerUseStop: true,
  computerUseStateJson: true,
  computerUseSummaryJson: true,
  teamSubmit: true,
  teamResumeSubmit: true,
  teamListJson: true,
  teamStatusJson: true,
  teamReplayJson: true,
  approvalShowJson: true,
  approvalPendingJson: true,
  approvalDecide: true,
  approvalExecute: true,
  configResolveJson: true,
  authWhoamiJson: true,
  authCheckJson: true,
  securityBaselineJson: true,
  keysStatusJson: true,
  keysVerifyJson: true,
  keysRotatePlanJson: true,
  supportBundleExportJson: true,
  metricsSnapshotJson: true,
  gaReadinessJson: true,
  qualificationRunJson: true,
  backupCreateJson: true,
  backupVerifyJson: true,
  restoreVerifyJson: true,
  migratePlanJson: true,
  migrateApplyDryRunJson: true,
};

const enabledComputerUse = {
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

const visionRuntime = {
  enabled: false,
  stage: 'not_qualified',
  platform: 'windows',
  scope: 'vision_first_desktop_web_file',
  executionModes: ['dry_run', 'step_approval'],
  replayable: true,
  failClosed: true,
  reasonCode: 'WINDOWS_COMPUTER_USE_NOT_QUALIFIED',
  summary: 'Vision runtime is not qualified on Windows.',
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
    platform: 'windows',
    profile: 'balanced',
    status: 'blocked',
    liveEnabled: false,
    supervisedLiveAllowed: false,
    publicLiveClaimAllowed: false,
    reasonCode: 'WINDOWS_COMPUTER_USE_NOT_QUALIFIED',
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
  platforms: {
    macos: {
      platform: 'macos',
      stage: 'not_qualified',
      liveEnabled: false,
      captureBackend: 'screencapture',
      inputBackend: 'disabled',
      provider: 'none',
      permissions: [],
      executionModes: ['dry_run', 'step_approval'],
      replayable: true,
      failClosed: true,
      reasonCode: 'MACOS_COMPUTER_USE_NOT_QUALIFIED',
      summary: null,
      blockers: ['VISION_PROVIDER_UNAVAILABLE'],
      qualificationStatus: 'missing',
      environment: {},
    },
    windows: {
      platform: 'windows',
      stage: 'not_qualified',
      liveEnabled: false,
      captureBackend: 'disabled',
      inputBackend: 'disabled',
      provider: 'none',
      permissions: [],
      executionModes: ['dry_run', 'step_approval'],
      replayable: true,
      failClosed: true,
      reasonCode: 'WINDOWS_COMPUTER_USE_NOT_QUALIFIED',
      summary: null,
      blockers: ['WINDOWS_CAPTURE_BACKEND_DISABLED'],
      qualificationStatus: 'missing',
      environment: {},
    },
    linux: {
      platform: 'linux',
      stage: 'not_qualified',
      liveEnabled: false,
      captureBackend: 'disabled',
      inputBackend: 'disabled',
      provider: 'none',
      permissions: [],
      executionModes: ['dry_run', 'step_approval'],
      replayable: true,
      failClosed: true,
      reasonCode: 'LINUX_COMPUTER_USE_NOT_QUALIFIED',
      summary: null,
      blockers: ['LINUX_INPUT_BACKEND_DISABLED'],
      qualificationStatus: 'missing',
      environment: {},
    },
  },
};

describe('capability handshake validation', () => {
  it('accepts fully compatible capabilities', () => {
    expect(
      hasContractMismatch({
        capabilities: {
          contractVersion: '3.0',
          commands: baseCommands,
        },
      }),
    ).toBe(false);
  });

  it('rejects mismatched contract version', () => {
    expect(
      hasContractMismatch({
        capabilities: {
          contractVersion: '1.0',
          commands: baseCommands,
        },
      }),
    ).toBe(true);
  });

  it('rejects the former Operator Panel contract version', () => {
    expect(
      hasContractMismatch({
        capabilities: {
          contractVersion: ['2', '0'].join('.'),
          commands: baseCommands,
        },
      }),
    ).toBe(true);
  });

  it('rejects when required command flags are missing', () => {
    expect(
      hasContractMismatch({
        capabilities: {
          contractVersion: '3.0',
          commands: {
            ...baseCommands,
            approvalExecute: false,
          },
        },
      }),
    ).toBe(true);
  });

  it('rejects when enterprise command flags are missing', () => {
    expect(
      hasContractMismatch({
        capabilities: {
          contractVersion: '3.0',
          commands: {
            ...baseCommands,
            supportBundleExportJson: false,
          },
        },
      }),
    ).toBe(true);
  });

  it('reads computer-use capability details', () => {
    expect(
      getComputerUseCapability({
        capabilities: {
          features: {
            computerUsePilot: enabledComputerUse,
          },
        },
      }),
    ).toEqual(enabledComputerUse);
  });

  it('enables live computer-use only when the fail-closed pilot is enabled', () => {
    expect(
      isComputerUseLiveEnabled({
        capabilities: {
          features: {
            computerUsePilot: enabledComputerUse,
          },
        },
      }),
    ).toBe(true);
  });

  it('does not allow default vision-first start from legacy pilot alone', () => {
    const handshake = {
      capabilities: {
        features: {
          computerUsePilot: enabledComputerUse,
          computerUseVisionRuntime: visionRuntime,
        },
      },
    };

    expect(isComputerUseSessionStartAllowed(handshake, 'vision-first')).toBe(false);
    expect(isComputerUseSessionStartAllowed(handshake, 'auto')).toBe(false);
    expect(isComputerUseSessionStartAllowed(handshake, 'legacy-pilot')).toBe(true);
  });

  it('allows vision-first start only when the vision runtime is enabled and fail-closed', () => {
    const handshake = {
      capabilities: {
        features: {
          computerUsePilot: { ...enabledComputerUse, enabled: false },
          computerUseVisionRuntime: {
            ...visionRuntime,
            enabled: true,
            platform: 'macos',
            reasonCode: null,
          },
        },
      },
    };

    expect(isComputerUseSessionStartAllowed(handshake, 'vision-first')).toBe(true);
  });

  it('keeps Windows computer-use disabled and exposes the reason code', () => {
    const capability = getComputerUseCapability({
      capabilities: {
        features: {
          computerUsePilot: {
            ...enabledComputerUse,
            enabled: false,
            stage: 'not_qualified',
            platform: 'windows',
            scope: 'core+operator_panel+bundled_runtime',
            executionModes: [],
            adapterStatus: 'windows_scaffold',
            reasonCode: 'WINDOWS_COMPUTER_USE_NOT_QUALIFIED',
            summary: 'Windows live computer-use is not qualified.',
          },
        },
      },
    });

    expect(capability.enabled).toBe(false);
    expect(capability.reasonCode).toBe('WINDOWS_COMPUTER_USE_NOT_QUALIFIED');
    expect(isComputerUseLiveEnabled({ capabilities: { features: { computerUsePilot: capability } } })).toBe(false);
    expect(
      isComputerUseSessionStartAllowed(
        {
          capabilities: {
            features: {
              computerUsePilot: capability,
              computerUseVisionRuntime: visionRuntime,
            },
          },
        },
        'vision-first',
      ),
    ).toBe(false);
  });

  it('reads additive vision runtime capability without enabling live execution', () => {
    const capability = getComputerUseVisionRuntimeCapability({
      capabilities: {
        features: {
          computerUseVisionRuntime: visionRuntime,
        },
      },
    });

    expect(capability).toEqual(visionRuntime);
    expect(capability.platforms.windows.reasonCode).toBe('WINDOWS_COMPUTER_USE_NOT_QUALIFIED');
    expect(capability.platforms.linux.liveEnabled).toBe(false);
    expect(
      isComputerUseVisionRuntimeLiveEnabled({
        capabilities: { features: { computerUseVisionRuntime: visionRuntime } },
      }),
    ).toBe(false);
  });

  it('keeps legacy vision runtime payloads parseable without resolver output', () => {
    const legacyVisionRuntime = { ...visionRuntime } as Record<string, unknown>;
    delete legacyVisionRuntime.capabilityResolution;
    const capability = getComputerUseVisionRuntimeCapability({
      capabilities: {
        features: {
          computerUseVisionRuntime: legacyVisionRuntime,
        },
      },
    });

    expect(capability.capabilityResolution).toBeNull();
    expect(capability.platforms.windows.reasonCode).toBe('WINDOWS_COMPUTER_USE_NOT_QUALIFIED');
  });

  it('does not trust optimistic resolver flags for live enablement', () => {
    const optimisticVisionRuntime = {
      ...visionRuntime,
      capabilityResolution: {
        ...visionRuntime.capabilityResolution,
        liveEnabled: true,
        supervisedLiveAllowed: true,
        publicLiveClaimAllowed: true,
      },
    };
    const handshake = {
      capabilities: {
        features: {
          computerUseVisionRuntime: optimisticVisionRuntime,
        },
      },
    };

    const capability = getComputerUseVisionRuntimeCapability(handshake);

    expect(capability.capabilityResolution?.liveEnabled).toBe(false);
    expect(capability.capabilityResolution?.supervisedLiveAllowed).toBe(true);
    expect(capability.capabilityResolution?.publicLiveClaimAllowed).toBe(false);
    expect(isComputerUseVisionRuntimeLiveEnabled(handshake)).toBe(false);
  });

  it('merges vision reason codes and blockers for operator remediation display', () => {
    const blockers = getComputerUseVisionRuntimeBlockers({
      capabilities: {
        features: {
          computerUseVisionRuntime: visionRuntime,
        },
      },
    });

    expect(blockers).toContain('WINDOWS_COMPUTER_USE_NOT_QUALIFIED');
    expect(blockers).toContain('COMPUTER_USE_EVIDENCE_MISSING');
    expect(blockers).toContain('WINDOWS_CAPTURE_BACKEND_DISABLED');
  });

  it('normalizes boolean raw screenshot safety drift for UI display', () => {
    const capability = getComputerUseVisionRuntimeCapability({
      capabilities: {
        features: {
          computerUseVisionRuntime: {
            ...visionRuntime,
            safety: {
              ...visionRuntime.safety,
              rawScreenshotPersistence: true,
            },
          },
        },
      },
    });

    expect(capability.safety.rawScreenshotPersistence).toBe('enabled');
  });
});
