import type { ComputerUseCapability, ComputerUseVisionRuntimeCapability } from '../capabilities';
import type { BridgeErrorPayload } from '../bridge';
import { DEFAULT_SETTINGS, type PanelSettings } from '../settings';

export const qaSettingsFixture: PanelSettings = {
  ...DEFAULT_SETTINGS,
  operatorId: 'qa-operator',
  rootDir: '.imperaos/test-ui/jobs',
  debugRaw: false,
};

export const bridgeErrorPayloadFixture: BridgeErrorPayload = {
  code: 'CLI_FAILED',
  message: 'Command failed',
  stderrPreview: 'redacted stderr preview',
  command: 'imperaos ...',
  retryable: true,
};

export const approvalTicketFixture = {
  id: 'approval_qa_1',
  title: 'device_action',
  subtitle: 'run_qa_1',
  status: 'pending',
  requested_action: 'Review and approve supervised action.',
};

export const runSummaryFixture = {
  contract_version: '3.0',
  runs: [
    {
      job_id: 'run_qa_1',
      status: 'running',
      request: 'QA fixture run',
      created_at: '2026-03-08T09:30:00Z',
    },
  ],
};

export const legacyComputerUseCapabilityFixture: ComputerUseCapability = {
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

export const blockedVisionComputerUseCapabilityFixture: ComputerUseVisionRuntimeCapability = {
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
