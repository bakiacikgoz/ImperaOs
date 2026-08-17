import { useCallback, useEffect, useMemo, useState } from 'react';

import { BridgeError, listAssistantModels } from '../bridge';
import type { PanelSettings } from '../settings';
import {
  flattenAssistantModels,
  type AssistantProviderId,
  type AssistantProviderModelCandidate,
  type AssistantProviderModelsProvider,
  type AssistantProviderModelsResponse,
} from './modelDiscovery';

export type AssistantModelDiscoveryStatus = 'idle' | 'loading' | 'success' | 'empty' | 'error';

export type AssistantModelDiscoveryError = {
  code: string;
  message: string;
};

export type AssistantModelDiscoveryState = {
  status: AssistantModelDiscoveryStatus;
  response: AssistantProviderModelsResponse | null;
  providers: AssistantProviderModelsProvider[];
  models: AssistantProviderModelCandidate[];
  error: AssistantModelDiscoveryError | null;
  refresh: () => void;
};

export function canonicalAssistantProviderId(provider: AssistantProviderId | 'all'): AssistantProviderId | 'all' {
  if (provider === 'ollama') {
    return 'local-ollama';
  }
  if (provider === 'transformers') {
    return 'local-transformers';
  }
  return provider;
}

export function useAssistantModels({
  settings,
  profile,
  provider,
}: {
  settings: PanelSettings;
  profile: string;
  provider: AssistantProviderId | 'all';
}): AssistantModelDiscoveryState {
  const canonicalProvider = canonicalAssistantProviderId(provider);
  const [response, setResponse] = useState<AssistantProviderModelsResponse | null>(null);
  const [status, setStatus] = useState<AssistantModelDiscoveryStatus>('idle');
  const [error, setError] = useState<AssistantModelDiscoveryError | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);
  const settingsFingerprint = useMemo(
    () =>
      JSON.stringify({
        mode: settings.mode,
        cliPath: settings.cliPath,
        bundledPythonPath: settings.bundledPythonPath,
        profile: settings.profile,
        rootDir: settings.rootDir,
      }),
    [
      settings.bundledPythonPath,
      settings.cliPath,
      settings.mode,
      settings.profile,
      settings.rootDir,
    ],
  );

  useEffect(() => {
    let cancelled = false;

    setStatus('loading');
    setError(null);

    listAssistantModels(settings, {
      profile,
      provider: canonicalProvider,
      refresh: refreshToken > 0,
    })
      .then((payload) => {
        if (cancelled) {
          return;
        }
        const models = flattenAssistantModels(payload, canonicalProvider);
        setResponse(payload);
        setStatus(models.length > 0 ? 'success' : 'empty');
      })
      .catch((err: unknown) => {
        if (cancelled) {
          return;
        }
        setResponse(null);
        if (err instanceof BridgeError) {
          setError({
            code: err.payload.code || 'BRIDGE_ERROR',
            message: err.payload.message || err.message,
          });
        } else {
          setError({
            code: 'MODEL_DISCOVERY_FAILED',
            message: err instanceof Error ? err.message : 'Assistant model discovery failed.',
          });
        }
        setStatus('error');
      });

    return () => {
      cancelled = true;
    };
  }, [canonicalProvider, profile, refreshToken, settingsFingerprint]);

  const refresh = useCallback(() => {
    setRefreshToken((value) => value + 1);
  }, []);

  const models = useMemo(
    () => (response ? flattenAssistantModels(response, canonicalProvider) : []),
    [canonicalProvider, response],
  );

  return {
    status,
    response,
    providers: response?.providers ?? [],
    models,
    error,
    refresh,
  };
}
