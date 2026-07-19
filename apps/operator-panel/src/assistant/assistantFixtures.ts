import type {
  AssistantFixtureScenario,
  AssistantSessionState,
  AssistantStartTurnResponse,
  AssistantStreamEvent,
} from './assistantTypes';
import type { AssistantProviderModelsResponse } from './modelDiscovery';
import { createAssistantSession, createAssistantTurn } from './assistantMappers';

const CONTRACT_VERSION = '3.0';
const FIXTURE_SESSION_ID = 'assistant-preview-session';
const FIXTURE_TURN_ID = 'assistant-preview-turn';

export function previewAssistantStartTurn(
  assistantTurnId = FIXTURE_TURN_ID,
  sessionId = FIXTURE_SESSION_ID,
): AssistantStartTurnResponse {
  return {
    contractVersion: CONTRACT_VERSION,
    assistantTurnId,
    sessionId,
    processId: null,
    status: 'started',
  };
}

export function previewAssistantEvents(
  assistantTurnId = FIXTURE_TURN_ID,
  sessionId = FIXTURE_SESSION_ID,
): AssistantStreamEvent[] {
  return [
    {
      contractVersion: CONTRACT_VERSION,
      assistantTurnId,
      sessionId,
      event: 'status',
      sequence: 1,
      timestampUtc: '2026-03-08T09:20:00Z',
      data: { phase: 'routing', message: 'Inspecting selected run context' },
    },
    {
      contractVersion: CONTRACT_VERSION,
      assistantTurnId,
      sessionId,
      event: 'token',
      sequence: 2,
      timestampUtc: '2026-03-08T09:20:01Z',
      data: { text: 'The selected run is blocked by an approval gate.' },
    },
    {
      contractVersion: CONTRACT_VERSION,
      assistantTurnId,
      sessionId,
      event: 'approval_pending',
      sequence: 3,
      timestampUtc: '2026-03-08T09:20:02Z',
      data: {
        approval_id: 'apr_20260308_device_action',
        title: 'Click preview form start button',
        risk: 'medium',
      },
    },
    {
      contractVersion: CONTRACT_VERSION,
      eventId: 'event-preview-artifact-committed',
      assistantTurnId,
      sessionId,
      event: 'artifact_committed',
      sequence: 4,
      timestampUtc: '2026-03-08T09:20:03Z',
      traceId: 'trace-preview-assistant',
      dataClass: 'internal',
      data: {
        artifactId: 'artifact-preview-document',
        revisionId: 'revision-1',
        kind: 'document',
        title: 'Launch plan',
        summary: 'Governed document artifact',
      },
    },
    {
      contractVersion: CONTRACT_VERSION,
      eventId: 'event-preview-form-requested',
      assistantTurnId,
      sessionId,
      event: 'form_requested',
      sequence: 5,
      timestampUtc: '2026-03-08T09:20:04Z',
      traceId: 'trace-preview-assistant',
      dataClass: 'confidential',
      data: {
        artifactId: 'artifact-preview-form',
        revisionId: 'form-revision-1',
        kind: 'form',
        title: 'Intake form',
        summary: 'Governed form artifact',
      },
    },
    {
      contractVersion: CONTRACT_VERSION,
      assistantTurnId,
      sessionId,
      event: 'final',
      sequence: 6,
      timestampUtc: '2026-03-08T09:20:05Z',
      data: {
        final_text:
          'The selected run is blocked by an approval gate. Review the pending approval before continuing.',
        trace_id: 'trace-preview-assistant',
        used_path: 'preview_fixture',
        fallback_events: [],
      },
    },
  ];
}

export function previewAssistantProviderModels(profile = 'balanced'): AssistantProviderModelsResponse {
  return {
    contractVersion: 'operator-panel.assistant-provider-models/v4',
    profile,
    provider: 'all',
    generatedAtUtc: '2026-03-08T09:20:00Z',
    providers: [
      {
        provider: 'local-ollama',
        legacyProvider: 'ollama',
        kind: 'local_ollama',
        displayName: 'Local Ollama',
        dataBoundary: 'local',
        riskTier: 'low',
        trustSource: 'preview_fixture',
        lastCanaryStatus: 'skipped',
        lastCanaryReason: 'PROVIDER_LIVE_CANARY_DISABLED',
        lastCanaryAtUtc: '2026-03-08T09:20:00Z',
        lastVerifiedEvidenceAtUtc: 'preview_fixture',
        evidencePath: null,
        budgetState: 'allow',
        budgetReason: 'PROVIDER_BUDGET_ALLOWED',
        conformanceStatus: 'pass',
        conformanceReason: 'PROVIDER_CONFORMANCE_OFFLINE_PASS',
        conformanceSummary: '8 pass / 3 skip / 0 fail',
        nativeAdapterKind: null,
        nativeAdapterStatus: 'not_applicable',
        storagePolicy: null,
        serverToolsPolicy: null,
        customToolsPolicy: null,
        clientToolsPolicy: null,
        toolResultLoopPolicy: null,
        stopReasonPolicy: null,
        liveCanaryStatus: null,
        available: true,
        selectedByConfig: true,
        disabledReason: null,
        models: [
          {
            provider: 'local-ollama',
            id: 'qwen3.5:4b',
            displayName: 'qwen3.5:4b',
            installed: true,
            configured: true,
            source: 'preview_fixture',
            warnings: [],
          },
        ],
      },
      {
        provider: 'local-transformers',
        legacyProvider: 'transformers',
        kind: 'local_transformers',
        displayName: 'Local Transformers',
        dataBoundary: 'local',
        riskTier: 'low',
        trustSource: 'preview_fixture',
        lastCanaryStatus: 'skipped',
        lastCanaryReason: 'PROVIDER_LIVE_CANARY_DISABLED',
        lastCanaryAtUtc: '2026-03-08T09:20:00Z',
        lastVerifiedEvidenceAtUtc: 'preview_fixture',
        evidencePath: null,
        budgetState: 'allow',
        budgetReason: 'PROVIDER_BUDGET_ALLOWED',
        conformanceStatus: 'pass',
        conformanceReason: 'PROVIDER_CONFORMANCE_OFFLINE_PASS',
        conformanceSummary: '6 pass / 5 skip / 0 fail',
        nativeAdapterKind: null,
        nativeAdapterStatus: 'not_applicable',
        storagePolicy: null,
        serverToolsPolicy: null,
        customToolsPolicy: null,
        clientToolsPolicy: null,
        toolResultLoopPolicy: null,
        stopReasonPolicy: null,
        liveCanaryStatus: null,
        available: true,
        selectedByConfig: false,
        disabledReason: null,
        models: [
          {
            provider: 'local-transformers',
            id: 'Qwen/Qwen3.5-4B-Instruct',
            displayName: 'Qwen/Qwen3.5-4B-Instruct',
            installed: false,
            configured: true,
            source: 'preview_fixture',
            warnings: ['Preview fixture only; local cache was not inspected.'],
          },
        ],
      },
      {
        provider: 'company-internal',
        legacyProvider: null,
        kind: 'openai_compatible',
        displayName: 'Company Internal Gateway',
        dataBoundary: 'internal',
        riskTier: 'medium',
        trustSource: 'preview_fixture',
        lastCanaryStatus: 'skipped',
        lastCanaryReason: 'PROVIDER_LIVE_CANARY_DISABLED',
        lastCanaryAtUtc: '2026-03-08T09:20:00Z',
        lastVerifiedEvidenceAtUtc: 'preview_fixture',
        evidencePath: 'artifacts/model-provider-governance/canary/company-internal.json',
        budgetState: 'allow',
        budgetReason: 'PROVIDER_BUDGET_ALLOWED',
        conformanceStatus: 'pass',
        conformanceReason: 'PROVIDER_CONFORMANCE_OFFLINE_PASS',
        conformanceSummary: '9 pass / 2 skip / 0 fail',
        nativeAdapterKind: null,
        nativeAdapterStatus: 'not_applicable',
        storagePolicy: null,
        serverToolsPolicy: null,
        customToolsPolicy: null,
        clientToolsPolicy: null,
        toolResultLoopPolicy: null,
        stopReasonPolicy: null,
        liveCanaryStatus: null,
        available: false,
        selectedByConfig: false,
        disabledReason: 'PROVIDER_SECRET_MISSING',
        errorCode: 'PROVIDER_SECRET_MISSING',
        errorMessage: 'PROVIDER_SECRET_MISSING',
        models: [
          {
            provider: 'company-internal',
            id: 'company-secure-agent-model',
            displayName: 'company-secure-agent-model',
            installed: false,
            configured: true,
            source: 'preview_fixture',
            warnings: ['Preview fixture only; secret ref is intentionally missing.'],
          },
        ],
      },
      {
        provider: 'openai-public',
        legacyProvider: null,
        kind: 'openai_compatible',
        displayName: 'OpenAI Public',
        dataBoundary: 'public_cloud',
        riskTier: 'high',
        trustSource: 'preview_fixture',
        lastCanaryStatus: 'skipped',
        lastCanaryReason: 'PROVIDER_LIVE_CANARY_DISABLED',
        lastCanaryAtUtc: '2026-03-08T09:20:00Z',
        lastVerifiedEvidenceAtUtc: 'preview_fixture',
        evidencePath: 'artifacts/model-provider-governance/canary/openai-public.json',
        budgetState: 'guarded',
        budgetReason: 'PROVIDER_CANARY_BUDGET_DISABLED',
        conformanceStatus: 'pass',
        conformanceReason: 'PROVIDER_CONFORMANCE_OFFLINE_PASS',
        conformanceSummary: '9 pass / 2 skip / 0 fail',
        nativeAdapterKind: null,
        nativeAdapterStatus: 'not_applicable',
        storagePolicy: null,
        serverToolsPolicy: null,
        customToolsPolicy: null,
        clientToolsPolicy: null,
        toolResultLoopPolicy: null,
        stopReasonPolicy: null,
        liveCanaryStatus: null,
        available: false,
        selectedByConfig: false,
        disabledReason: 'PROVIDER_REMOTE_DISABLED',
        errorCode: 'PROVIDER_REMOTE_DISABLED',
        errorMessage: 'PROVIDER_REMOTE_DISABLED',
        models: [
          {
            provider: 'openai-public',
            id: 'gpt-5.1',
            displayName: 'gpt-5.1',
            installed: false,
            configured: true,
            source: 'preview_fixture',
            warnings: ['Preview fixture only; remote providers are disabled by default.'],
          },
        ],
      },
      {
        provider: 'openai-responses-preview',
        legacyProvider: null,
        kind: 'openai_responses',
        displayName: 'OpenAI Responses Native Preview',
        dataBoundary: 'public_cloud',
        riskTier: 'high',
        trustSource: 'preview_fixture',
        lastCanaryStatus: 'skipped',
        lastCanaryReason: 'PROVIDER_LIVE_CANARY_DISABLED',
        lastCanaryAtUtc: '2026-03-08T09:20:00Z',
        lastVerifiedEvidenceAtUtc: 'preview_fixture',
        evidencePath: 'artifacts/model-provider-governance/native-v2/provider_native_adapter_gate.json',
        budgetState: 'guarded',
        budgetReason: 'PROVIDER_CANARY_BUDGET_DISABLED',
        conformanceStatus: 'pass',
        conformanceReason: 'PROVIDER_CONFORMANCE_OFFLINE_PASS',
        conformanceSummary: '12 pass / 2 skip / 0 fail',
        nativeAdapterKind: 'openai_responses',
        nativeAdapterStatus: 'canary_only',
        storagePolicy: 'hash_only/store=false',
        serverToolsPolicy: 'denied',
        customToolsPolicy: 'proposal_only',
        clientToolsPolicy: 'proposal_only',
        toolResultLoopPolicy: 'not_applicable',
        stopReasonPolicy: 'fail_closed',
        liveCanaryStatus: 'false',
        available: false,
        selectedByConfig: false,
        disabledReason: 'PROVIDER_REMOTE_DISABLED',
        errorCode: 'PROVIDER_REMOTE_DISABLED',
        errorMessage: 'PROVIDER_REMOTE_DISABLED',
        models: [
          {
            provider: 'openai-responses-preview',
            id: 'gpt-5.1',
            displayName: 'gpt-5.1',
            installed: false,
            configured: true,
            source: 'preview_fixture',
            warnings: ['Native adapter preview; canary-only and disabled by default.'],
          },
        ],
      },
      {
        provider: 'anthropic-messages-preview',
        legacyProvider: null,
        kind: 'anthropic_messages',
        displayName: 'Anthropic Messages Native Preview',
        dataBoundary: 'public_cloud',
        riskTier: 'high',
        trustSource: 'preview_fixture',
        lastCanaryStatus: 'skipped',
        lastCanaryReason: 'PROVIDER_LIVE_CANARY_DISABLED',
        lastCanaryAtUtc: '2026-03-08T09:20:00Z',
        lastVerifiedEvidenceAtUtc: 'preview_fixture',
        evidencePath: 'artifacts/model-provider-governance/native-v2/provider_native_adapter_gate.json',
        budgetState: 'guarded',
        budgetReason: 'PROVIDER_CANARY_BUDGET_DISABLED',
        conformanceStatus: 'pass',
        conformanceReason: 'PROVIDER_CONFORMANCE_OFFLINE_PASS',
        conformanceSummary: '4 pass / 13 expected-blocked / 0 fail',
        nativeAdapterKind: 'anthropic_messages',
        nativeAdapterStatus: 'canary_only',
        storagePolicy: 'hash_only/raw_disabled',
        serverToolsPolicy: 'denied',
        customToolsPolicy: 'proposal_only',
        clientToolsPolicy: 'proposal_only',
        toolResultLoopPolicy: 'not_implemented',
        stopReasonPolicy: 'fail_closed',
        liveCanaryStatus: 'false',
        available: false,
        selectedByConfig: false,
        disabledReason: 'PROVIDER_REMOTE_DISABLED',
        errorCode: 'PROVIDER_REMOTE_DISABLED',
        errorMessage: 'PROVIDER_REMOTE_DISABLED',
        models: [
          {
            provider: 'anthropic-messages-preview',
            id: 'claude-sonnet-4-6',
            displayName: 'claude-sonnet-4-6',
            installed: false,
            configured: true,
            source: 'preview_fixture',
            warnings: ['Anthropic native adapter preview; canary-only and disabled by default.'],
          },
        ],
      },
    ],
  };
}

function baseState(): AssistantSessionState {
  return createAssistantSession(FIXTURE_SESSION_ID);
}

function runningState(): AssistantSessionState {
  const turn = createAssistantTurn({
    id: FIXTURE_TURN_ID,
    sessionId: FIXTURE_SESSION_ID,
    userMessage: 'Son run hatasını özetle',
    createdAtUtc: '2026-03-08T09:20:00Z',
  });
  turn.status = 'streaming';
  turn.eventSequence = 3;
  turn.assistantMessage.text = 'The selected run is blocked by an approval gate.';
  turn.assistantMessage.timeline = [
    {
      id: 'activity-routing',
      tone: 'info',
      title: 'Routing',
      subtitle: 'Inspecting selected run context',
      timestampUtc: '2026-03-08T09:20:00Z',
    },
    {
      id: 'activity-events',
      tone: 'success',
      title: 'Events loaded',
      subtitle: '8 redacted runtime events are available',
      timestampUtc: '2026-03-08T09:20:01Z',
    },
  ];
  turn.assistantMessage.referencedRuns = [
    {
      id: 'job-ui-preview-cu-1',
      status: 'blocked',
      summary: 'Awaiting operator approval before the next computer-use action.',
    },
  ];

  return {
    ...baseState(),
    turns: [turn],
    activeTurnId: turn.id,
    status: 'streaming',
    selectedRunIds: ['job-ui-preview-cu-1'],
  };
}

function approvalRequiredState(): AssistantSessionState {
  const state = runningState();
  const turn = state.turns[0];
  turn.status = 'awaiting_approval';
  turn.assistantMessage.proposedAction = {
    id: 'click_start_button',
    title: 'Click preview form start button',
    target: 'safari:ImperaOS Preview Form / #start',
    risk: 'medium',
    dryRunSummary: 'Dry-run verified that the target is visible. Execution remains approval-gated.',
    commandPreview: 'computer-use action click --target #start',
  };
  turn.assistantMessage.approval = {
    approvalId: 'apr_20260308_device_action',
    title: 'Click preview form start button',
    status: 'pending',
    risk: 'medium',
    detailLoaded: true,
  };
  turn.assistantMessage.timeline = [
    ...turn.assistantMessage.timeline,
    {
      id: 'activity-approval',
      tone: 'warning',
      title: 'Approval required',
      subtitle: 'Existing governance lifecycle must approve before execution.',
      timestampUtc: '2026-03-08T09:20:02Z',
    },
  ];

  return {
    ...state,
    status: 'awaiting_approval',
    pendingApprovalId: 'apr_20260308_device_action',
  };
}

export function getAssistantFixture(scenario: AssistantFixtureScenario): AssistantSessionState {
  if (scenario === 'running') {
    return runningState();
  }
  if (scenario === 'approval_required') {
    return approvalRequiredState();
  }
  return baseState();
}
