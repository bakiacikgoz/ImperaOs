import { screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { AssistantModelDiscoveryState } from '../../assistant/useAssistantModels';
import { DEFAULT_ASSISTANT_RUNTIME_SETTINGS } from '../../settings';
import { renderOperatorPanel } from '../../test/render';
import { AssistantModelPicker } from './AssistantModelPicker';

function discovery(overrides: Partial<AssistantModelDiscoveryState> = {}): AssistantModelDiscoveryState {
  return {
    status: 'success',
    response: null,
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
        lastVerifiedEvidenceAtUtc: 'preview_fixture',
        budgetState: 'allow',
        budgetReason: 'PROVIDER_BUDGET_ALLOWED',
        conformanceStatus: 'pass',
        conformanceReason: 'PROVIDER_CONFORMANCE_OFFLINE_PASS',
        conformanceSummary: '8 pass / 3 skip / 0 fail',
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
        provider: 'company-internal',
        legacyProvider: null,
        kind: 'openai_compatible',
        displayName: 'Company Internal Gateway',
        dataBoundary: 'internal',
        riskTier: 'medium',
        trustSource: 'preview_fixture',
        lastCanaryStatus: 'skipped',
        lastCanaryReason: 'PROVIDER_LIVE_CANARY_DISABLED',
        lastVerifiedEvidenceAtUtc: 'preview_fixture',
        budgetState: 'allow',
        budgetReason: 'PROVIDER_BUDGET_ALLOWED',
        conformanceStatus: 'pass',
        conformanceReason: 'PROVIDER_CONFORMANCE_OFFLINE_PASS',
        conformanceSummary: '9 pass / 2 skip / 0 fail',
        available: false,
        selectedByConfig: false,
        disabledReason: 'PROVIDER_SECRET_MISSING',
        errorCode: 'PROVIDER_SECRET_MISSING',
        models: [],
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
        lastVerifiedEvidenceAtUtc: 'preview_fixture',
        budgetState: 'guarded',
        budgetReason: 'PROVIDER_CANARY_BUDGET_DISABLED',
        conformanceStatus: 'pass',
        conformanceReason: 'PROVIDER_CONFORMANCE_OFFLINE_PASS',
        conformanceSummary: '9 pass / 2 skip / 0 fail',
        available: false,
        selectedByConfig: false,
        disabledReason: 'PROVIDER_REMOTE_DISABLED',
        errorCode: 'PROVIDER_REMOTE_DISABLED',
        models: [],
      },
      {
        provider: 'policy-blocked',
        legacyProvider: null,
        kind: 'openai_compatible',
        displayName: 'Policy Blocked',
        dataBoundary: 'public_cloud',
        riskTier: 'blocked',
        trustSource: 'live_evidence',
        lastCanaryStatus: 'denied',
        lastCanaryReason: 'PROVIDER_DATA_BOUNDARY_DENIED',
        lastVerifiedEvidenceAtUtc: '2026-06-10T08:00:00Z',
        budgetState: 'allow',
        budgetReason: 'PROVIDER_BUDGET_ALLOWED',
        conformanceStatus: 'fail',
        conformanceReason: 'PROVIDER_CONFORMANCE_OFFLINE_FAIL',
        conformanceSummary: '8 pass / 2 skip / 1 fail',
        available: false,
        selectedByConfig: false,
        disabledReason: 'PROVIDER_DATA_BOUNDARY_DENIED',
        errorCode: 'PROVIDER_DATA_BOUNDARY_DENIED',
        models: [],
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
        lastVerifiedEvidenceAtUtc: 'preview_fixture',
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
        models: [],
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
        lastVerifiedEvidenceAtUtc: 'preview_fixture',
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
        models: [],
      },
    ],
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
    error: null,
    refresh: vi.fn(),
    ...overrides,
  };
}

function renderPicker(state: AssistantModelDiscoveryState | null = discovery(), provider = '') {
  return renderOperatorPanel(
    <AssistantModelPicker
      runtimeSettings={{ ...DEFAULT_ASSISTANT_RUNTIME_SETTINGS, assistantProvider: provider }}
      modelDiscovery={state}
      onRuntimeSettingsChange={vi.fn()}
    />,
  );
}

describe('AssistantModelPicker provider governance states', () => {
  it('renders local ready, auth missing, remote disabled, and policy blocked registry states', () => {
    renderPicker();

    const registry = screen.getByLabelText('Provider registry');
    expect(within(registry).getByText('Local Ollama')).toBeInTheDocument();
    expect(within(registry).getByText('local_ollama / local')).toBeInTheDocument();
    expect(within(registry).getByText('enabled: low')).toBeInTheDocument();
    expect(within(registry).getByText('Company Internal Gateway')).toBeInTheDocument();
    expect(within(registry).getByText('disabled: medium: PROVIDER_SECRET_MISSING')).toBeInTheDocument();
    expect(within(registry).getByText('OpenAI Public')).toBeInTheDocument();
    expect(
      within(registry).getAllByText('disabled: high: PROVIDER_REMOTE_DISABLED').length,
    ).toBeGreaterThan(0);
    expect(within(registry).getAllByText('source: preview_fixture').length).toBeGreaterThan(0);
    expect(
      within(registry).getAllByText('canary: skipped: PROVIDER_LIVE_CANARY_DISABLED').length,
    ).toBeGreaterThan(0);
    expect(
      within(registry).getAllByText('budget: guarded: PROVIDER_CANARY_BUDGET_DISABLED').length,
    ).toBeGreaterThan(0);
    expect(
      within(registry).getAllByText('conformance: pass: 9 pass / 2 skip / 0 fail').length,
    ).toBeGreaterThan(0);
    expect(within(registry).getByText('Policy Blocked')).toBeInTheDocument();
    expect(
      within(registry).getByText('disabled: blocked: PROVIDER_DATA_BOUNDARY_DENIED'),
    ).toBeInTheDocument();
    expect(within(registry).getByText('source: live_evidence')).toBeInTheDocument();
    expect(
      within(registry).getByText('canary: denied: PROVIDER_DATA_BOUNDARY_DENIED'),
    ).toBeInTheDocument();
    expect(within(registry).getByText('conformance: fail: 8 pass / 2 skip / 1 fail')).toBeInTheDocument();
    expect(within(registry).getByText('OpenAI Responses Native Preview')).toBeInTheDocument();
    expect(within(registry).getByText('native: openai_responses: canary_only')).toBeInTheDocument();
    expect(within(registry).getByText('storage: hash_only/store=false')).toBeInTheDocument();
    expect(within(registry).getAllByText('server_tools: denied').length).toBeGreaterThan(0);
    expect(within(registry).getAllByText('custom_tools: proposal_only').length).toBeGreaterThan(0);
    expect(within(registry).getByText('Anthropic Messages Native Preview')).toBeInTheDocument();
    expect(within(registry).getByText('native: anthropic_messages: canary_only')).toBeInTheDocument();
    expect(within(registry).getByText('storage: hash_only/raw_disabled')).toBeInTheDocument();
    expect(within(registry).getAllByText('client_tools: proposal_only').length).toBeGreaterThan(0);
    expect(within(registry).getByText('tool_result_loop: not_implemented')).toBeInTheDocument();
    expect(within(registry).getAllByText('stop_reason: fail_closed').length).toBeGreaterThan(0);
    expect(within(registry).getAllByText('live_canary: false').length).toBeGreaterThan(0);
  });

  it('shows loading and empty discovery states without raw JSON', () => {
    const { rerender } = renderPicker(discovery({ status: 'loading', providers: [], models: [] }));

    expect(screen.getByText('Discovering local assistant models...')).toBeInTheDocument();

    rerender(
      <AssistantModelPicker
        runtimeSettings={{ ...DEFAULT_ASSISTANT_RUNTIME_SETTINGS }}
        modelDiscovery={discovery({ status: 'empty', providers: [], models: [] })}
        onRuntimeSettingsChange={vi.fn()}
      />,
    );

    expect(screen.getByText('No local assistant models were discovered. Use refresh after installing a model.')).toBeInTheDocument();
    expect(screen.queryByLabelText('Provider registry')).not.toBeInTheDocument();
  });

  it('surfaces a selected provider blocked reason', () => {
    renderPicker(discovery(), 'openai-public');

    expect(screen.getByText('PROVIDER_REMOTE_DISABLED')).toBeInTheDocument();
  });

  it.each([
    ['ollama', 'local-ollama', 'qwen3.5:4b', 'Assistant model'],
    ['transformers', 'local-transformers', 'Qwen/Qwen2.5', 'Assistant HF model id'],
  ] as const)(
    'resolves legacy provider %s to canonical selectable models',
    (legacyProvider, canonicalProvider, modelId, modelLabel) => {
      const state = discovery({
        providers: [{
          provider: canonicalProvider,
          legacyProvider,
          kind: canonicalProvider === 'local-ollama' ? 'local_ollama' : 'local_transformers',
          displayName: canonicalProvider === 'local-ollama' ? 'Local Ollama' : 'Local Transformers',
          available: true,
          selectedByConfig: true,
          disabledReason: null,
          models: [],
        }],
        models: [{
          provider: canonicalProvider,
          id: modelId,
          displayName: modelId,
          installed: true,
          configured: true,
          source: canonicalProvider === 'local-ollama' ? 'ollama' : 'transformers_cache',
          warnings: [],
        }],
      });

      renderPicker(state, legacyProvider);

      expect(screen.getByLabelText('Assistant provider')).toHaveValue(canonicalProvider);
      expect(within(screen.getByLabelText(modelLabel)).getByRole('option', { name: modelId })).toBeEnabled();
    },
  );

  it.each(['ollama', 'transformers', 'local-ollama', 'local-transformers'] as const)(
    'preserves configured provider %s when discovery has no matching record',
    (provider) => {
      renderPicker(discovery({ status: 'empty', providers: [], models: [] }), provider);

      expect(screen.getByLabelText('Assistant provider')).toHaveValue(provider);
    },
  );

  it('disables an unavailable discovered provider instead of exposing its legacy alias', () => {
    renderPicker(
      discovery({
        providers: [{
          provider: 'local-ollama', legacyProvider: 'ollama', kind: 'local_ollama',
          displayName: 'Local Ollama', available: false, selectedByConfig: false,
          disabledReason: 'OLLAMA_NOT_AVAILABLE', models: [],
        }],
        models: [],
      }),
    );

    const providerSelect = screen.getByLabelText('Assistant provider');
    expect(
      within(providerSelect).getByRole('option', { name: 'Local Ollama (OLLAMA_NOT_AVAILABLE)' }),
    ).toBeDisabled();
    expect(within(providerSelect).queryByRole('option', { name: 'ollama' })).not.toBeInTheDocument();
    expect(
      within(screen.getByLabelText('Assistant fallback provider')).getByRole('option', { name: 'ollama' }),
    ).toBeDisabled();
  });

  it('disables discovered models that are not installed', () => {
    renderPicker(
      discovery({
        models: [{
          provider: 'local-ollama', id: 'configured-but-missing:latest',
          displayName: 'configured-but-missing:latest', installed: false, configured: true,
          source: 'config', warnings: ['Configured Ollama model is not present in ollama list.'],
        }],
      }),
      'local-ollama',
    );

    expect(
      screen.getByRole('option', { name: 'configured-but-missing:latest (configured)' }),
    ).toBeDisabled();
  });
});
