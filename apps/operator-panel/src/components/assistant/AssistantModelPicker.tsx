import type {
  AssistantProviderId,
  AssistantProviderModelCandidate,
  AssistantProviderModelsProvider,
} from '../../assistant/modelDiscovery';
import {
  canonicalAssistantProviderId,
  type AssistantModelDiscoveryState,
} from '../../assistant/useAssistantModels';
import { assistantUiText, translateAssistantText, type UiLocale } from '../../i18n';
import type { AssistantRuntimeSettings } from '../../settings';

type AssistantModelPickerProps = {
  runtimeSettings: AssistantRuntimeSettings;
  modelDiscovery?: AssistantModelDiscoveryState | null;
  locale?: UiLocale;
  onRuntimeSettingsChange: (next: Partial<AssistantRuntimeSettings>) => void;
};

const PROVIDER_VALUES = ['', 'auto', 'ollama', 'transformers', 'local-transformers', 'local-ollama'];
const FALLBACK_VALUES = ['', 'transformers', 'ollama', 'local-transformers', 'local-ollama'];

function providerFromSettings(settings: AssistantRuntimeSettings): AssistantProviderId | 'default' {
  return settings.assistantProvider.trim() || 'default';
}

function providerFromDiscovery(
  provider: AssistantProviderId | 'default',
  discoveredProviders: AssistantProviderModelsProvider[],
): AssistantProviderId | 'default' {
  if (provider === 'default') {
    return provider;
  }
  const canonicalProvider = canonicalAssistantProviderId(provider);
  const discoveredProvider = discoveredProviders.find(
    (item) =>
      item.provider === provider ||
      item.provider === canonicalProvider ||
      item.legacyProvider === provider,
  );
  return discoveredProvider?.provider ?? provider;
}

function modelsForProvider(
  models: AssistantProviderModelCandidate[],
  provider: AssistantProviderId,
): AssistantProviderModelCandidate[] {
  return models.filter((model) => model.provider === provider);
}

function modelOptionLabel(model: AssistantProviderModelCandidate, locale: UiLocale): string {
  const suffix = model.installed ? '' : ` (${translateAssistantText('configured', locale)})`;
  return `${model.displayName || model.id}${suffix}`;
}

function providerOptionLabel(provider: AssistantProviderModelsProvider, locale: UiLocale): string {
  const label = provider.displayName || provider.provider;
  const reason = provider.disabledReason || provider.errorCode;
  if (!reason || provider.available) {
    return label;
  }
  return `${label} (${translateAssistantText(reason, locale)})`;
}

function isOllamaProvider(value: string): boolean {
  return value === 'ollama' || value === 'local-ollama';
}

function isTransformersProvider(value: string): boolean {
  return value === 'transformers' || value === 'local-transformers';
}

export function AssistantModelPicker({
  runtimeSettings,
  modelDiscovery,
  locale = 'en',
  onRuntimeSettingsChange,
}: AssistantModelPickerProps) {
  const text = assistantUiText[locale];
  const discoveredProviders = modelDiscovery?.providers ?? [];
  const provider = providerFromDiscovery(providerFromSettings(runtimeSettings), discoveredProviders);
  const providerOptions: AssistantProviderModelsProvider[] = [
    ...PROVIDER_VALUES.filter(
      (value) =>
        !discoveredProviders.some(
          (item) => item.provider === value || item.legacyProvider === value,
        ),
    ).map((value) => ({
      provider: value,
      displayName: value ? value : text.useProfileDefault,
      available: true,
      selectedByConfig: false,
      models: [],
    })),
    ...discoveredProviders,
  ];
  const selectedProviderRecord = discoveredProviders.find((item) => item.provider === provider);
  const selectedModels = provider === 'default' ? [] : modelsForProvider(modelDiscovery?.models ?? [], provider);
  const discoveryStatus = modelDiscovery?.status ?? 'idle';
  const isDiscovering = discoveryStatus === 'loading';
  const discoveryError = modelDiscovery?.error;

  const updateRuntimeSetting = (key: keyof AssistantRuntimeSettings, value: string) => {
    onRuntimeSettingsChange({ [key]: value });
  };

  const updateProvider = (value: string) => {
    if (isOllamaProvider(value)) {
      onRuntimeSettingsChange({ assistantProvider: value, assistantHfModelId: '' });
      return;
    }
    if (isTransformersProvider(value)) {
      onRuntimeSettingsChange({ assistantProvider: value, assistantModel: '' });
      return;
    }
    onRuntimeSettingsChange({ assistantProvider: value });
  };
  const onRefreshModels = () => {
    modelDiscovery?.refresh();
  };

  const discoveryHelper =
    discoveryError?.message ||
    (discoveryStatus === 'empty'
      ? translateAssistantText('No local assistant models were discovered. Use refresh after installing a model.', locale)
      : isDiscovering
        ? translateAssistantText('Discovering local assistant models...', locale)
        : '');
  const refreshTitle = isDiscovering
    ? translateAssistantText('Assistant model discovery is already running.', locale)
    : translateAssistantText('Refresh assistant models', locale);
  const optionLabel = (value: string) => (value ? value : text.useProfileDefault);

  return (
    <div className="assistant-runtime-settings" aria-label="Assistant runtime settings">
      <label>
        <span>{text.provider}</span>
        <select
          aria-label="Assistant provider"
          value={provider === 'default' ? '' : provider}
          onChange={(event) => updateProvider(event.target.value)}
        >
          {providerOptions.map((item) => (
            <option
              key={item.provider || 'default'}
              value={item.provider}
              disabled={Boolean(item.provider && !item.available)}
            >
              {item.provider ? providerOptionLabel(item, locale) : optionLabel('')}
            </option>
          ))}
        </select>
      </label>

      {isOllamaProvider(provider) ? (
        <label>
          <span>{text.model}</span>
          {selectedModels.length > 0 ? (
            <select
              aria-label="Assistant model"
              value={runtimeSettings.assistantModel}
              onChange={(event) => updateRuntimeSetting('assistantModel', event.target.value)}
            >
              <option value="">{text.useProfileDefault}</option>
              {selectedModels.map((model) => (
                <option key={`${model.provider}:${model.id}`} value={model.id} disabled={!model.installed}>
                  {modelOptionLabel(model, locale)}
                </option>
              ))}
            </select>
          ) : (
            <input
              aria-label="Assistant model"
              value={runtimeSettings.assistantModel}
              onChange={(event) => updateRuntimeSetting('assistantModel', event.target.value)}
              placeholder="qwen3.5:4b"
            />
          )}
        </label>
      ) : null}

      {isTransformersProvider(provider) ? (
        <label>
          <span>{text.hfModelId}</span>
          {selectedModels.length > 0 ? (
            <select
              aria-label="Assistant HF model id"
              value={runtimeSettings.assistantHfModelId}
              onChange={(event) => updateRuntimeSetting('assistantHfModelId', event.target.value)}
            >
              <option value="">{text.useProfileDefault}</option>
              {selectedModels.map((model) => (
                <option key={`${model.provider}:${model.id}`} value={model.id} disabled={!model.installed}>
                  {modelOptionLabel(model, locale)}
                </option>
              ))}
            </select>
          ) : (
            <input
              aria-label="Assistant HF model id"
              value={runtimeSettings.assistantHfModelId}
              onChange={(event) => updateRuntimeSetting('assistantHfModelId', event.target.value)}
              placeholder="Qwen/Qwen2.5"
            />
          )}
        </label>
      ) : null}

      {provider !== 'default' && provider !== 'auto' && !isOllamaProvider(provider) && !isTransformersProvider(provider) ? (
        <label>
          <span>{text.model}</span>
          {selectedModels.length > 0 ? (
            <select
              aria-label="Assistant model"
              value={runtimeSettings.assistantModel}
              onChange={(event) => updateRuntimeSetting('assistantModel', event.target.value)}
            >
              <option value="">{text.useProfileDefault}</option>
              {selectedModels.map((model) => (
                <option key={`${model.provider}:${model.id}`} value={model.id} disabled={!model.installed}>
                  {modelOptionLabel(model, locale)}
                </option>
              ))}
            </select>
          ) : (
            <input
              aria-label="Assistant model"
              value={runtimeSettings.assistantModel}
              onChange={(event) => updateRuntimeSetting('assistantModel', event.target.value)}
              placeholder={selectedProviderRecord?.models[0]?.id || 'model-id'}
            />
          )}
        </label>
      ) : null}

      {provider === 'default' || provider === 'auto' ? (
        <label>
          <span>{text.model}</span>
          <input aria-label="Assistant model" value={text.profileManaged} readOnly />
        </label>
      ) : null}

      <label>
        <span>{text.fallback}</span>
        <select
          aria-label="Assistant fallback provider"
          value={runtimeSettings.assistantFallbackProvider}
          onChange={(event) => updateRuntimeSetting('assistantFallbackProvider', event.target.value)}
        >
          {FALLBACK_VALUES.map((value) => (
            <option
              key={value || 'default'}
              value={value}
              disabled={Boolean(
                value &&
                  discoveredProviders.find(
                    (item) =>
                      item.provider === canonicalAssistantProviderId(value) || item.legacyProvider === value,
                  )?.available === false,
              )}
            >
              {optionLabel(value)}
            </option>
          ))}
        </select>
      </label>

      <div className="assistant-model-discovery-status" aria-live="polite">
        {selectedProviderRecord?.disabledReason ? (
          <span>{translateAssistantText(selectedProviderRecord.disabledReason, locale)}</span>
        ) : discoveryHelper ? (
          <span>{discoveryHelper}</span>
        ) : (
          <span>{`${modelDiscovery?.models.length ?? 0} ${text.modelsFound}`}</span>
        )}
        {modelDiscovery ? (
          <button
            type="button"
            onClick={onRefreshModels}
            disabled={isDiscovering}
            title={refreshTitle}
            data-disabled-reason={isDiscovering ? refreshTitle : undefined}
          >
            {text.refresh}
          </button>
        ) : null}
      </div>

      {discoveredProviders.length > 0 ? (
        <div className="assistant-provider-registry" aria-label="Provider registry">
          {discoveredProviders.map((item) => {
            const status = item.available ? 'enabled' : 'disabled';
            const detail = item.disabledReason || item.errorCode || '';
            const boundary = item.dataBoundary || 'unknown';
            const risk = item.riskTier || 'unknown';
            const trustSource = item.trustSource || 'bridge_state';
            const canaryStatus = item.lastCanaryStatus || 'not_run';
            const canaryReason = item.lastCanaryReason || item.disabledReason || item.errorCode || 'none';
            const budgetState = item.budgetState || 'unknown';
            const evidenceAt = item.lastVerifiedEvidenceAtUtc || 'none';
            const conformanceStatus = item.conformanceStatus || 'unknown';
            const conformanceSummary = item.conformanceSummary || 'not_run';
            const nativeStatus = item.nativeAdapterStatus || 'not_applicable';
            return (
              <div key={item.provider} className="assistant-provider-registry-row">
                <strong>{item.displayName || item.provider}</strong>
                <span>{`${item.kind || item.legacyProvider || 'provider'} / ${boundary}`}</span>
                <em className={item.available ? 'assistant-success-value' : 'assistant-warning-value'}>
                  {detail
                    ? `${status}: ${risk}: ${translateAssistantText(detail, locale)}`
                    : `${status}: ${risk}`}
                </em>
                <small>{`source: ${trustSource}`}</small>
                <small>{`canary: ${canaryStatus}: ${translateAssistantText(canaryReason, locale)}`}</small>
                <small>{`budget: ${budgetState}${item.budgetReason ? `: ${translateAssistantText(item.budgetReason, locale)}` : ''}`}</small>
                <small>{`conformance: ${conformanceStatus}: ${conformanceSummary}`}</small>
                {item.nativeAdapterKind ? <small>{`native: ${item.nativeAdapterKind}: ${nativeStatus}`}</small> : null}
                {item.storagePolicy ? <small>{`storage: ${item.storagePolicy}`}</small> : null}
                {item.serverToolsPolicy ? <small>{`server_tools: ${item.serverToolsPolicy}`}</small> : null}
                {item.customToolsPolicy ? <small>{`custom_tools: ${item.customToolsPolicy}`}</small> : null}
                {item.clientToolsPolicy ? <small>{`client_tools: ${item.clientToolsPolicy}`}</small> : null}
                {item.toolResultLoopPolicy ? <small>{`tool_result_loop: ${item.toolResultLoopPolicy}`}</small> : null}
                {item.stopReasonPolicy ? <small>{`stop_reason: ${item.stopReasonPolicy}`}</small> : null}
                {item.liveCanaryStatus ? <small>{`live_canary: ${item.liveCanaryStatus}`}</small> : null}
                <small>{`evidence: ${evidenceAt}`}</small>
              </div>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
