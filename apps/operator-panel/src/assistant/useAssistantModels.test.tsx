import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { DEFAULT_SETTINGS } from '../settings';
import { useAssistantModels } from './useAssistantModels';

const bridgeMocks = vi.hoisted(() => ({
  listAssistantModels: vi.fn(),
}));

vi.mock('../bridge', () => ({
  listAssistantModels: bridgeMocks.listAssistantModels,
  BridgeError: class BridgeError extends Error {
    readonly payload: {
      code: string;
      message: string;
      stderrPreview: string;
      command: string;
      retryable: boolean;
    };

    constructor(payload: {
      code: string;
      message: string;
      stderrPreview: string;
      command: string;
      retryable: boolean;
    }) {
      super(payload.message);
      this.name = 'BridgeError';
      this.payload = payload;
    }
  },
}));

function providerModels(models: unknown[] = []) {
  return {
    contractVersion: 'operator-panel.assistant-provider-models/v2',
    profile: 'balanced',
    provider: 'local-ollama',
    generatedAtUtc: '2026-06-07T00:00:00.000Z',
    providers: [
      {
        provider: 'local-ollama',
        legacyProvider: 'ollama',
        kind: 'local_ollama',
        displayName: 'Local Ollama',
        available: true,
        selectedByConfig: true,
        disabledReason: null,
        models,
      },
    ],
  };
}

function canonicalProviderModels({
  provider,
  legacyProvider,
}: {
  provider: 'local-ollama' | 'local-transformers';
  legacyProvider: 'ollama' | 'transformers';
}) {
  const modelId = provider === 'local-ollama' ? 'qwen3.5:4b' : 'Qwen/Qwen2.5';
  return {
    contractVersion: 'operator-panel.assistant-provider-models/v2',
    profile: 'balanced',
    provider,
    generatedAtUtc: '2026-06-07T00:00:00.000Z',
    providers: [
      {
        provider,
        legacyProvider,
        kind: provider === 'local-ollama' ? 'local_ollama' : 'local_transformers',
        displayName: provider === 'local-ollama' ? 'Local Ollama' : 'Local Transformers',
        available: true,
        selectedByConfig: true,
        disabledReason: null,
        models: [
          {
            provider,
            id: modelId,
            displayName: modelId,
            installed: true,
            configured: true,
            source: provider === 'local-ollama' ? 'ollama' : 'transformers_cache',
            warnings: [],
          },
        ],
      },
    ],
  };
}

describe('useAssistantModels', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('loads and flattens assistant model discovery candidates', async () => {
    bridgeMocks.listAssistantModels.mockResolvedValue(
      providerModels([
        {
          provider: 'local-ollama',
          id: 'qwen3.5:4b',
          displayName: 'qwen3.5:4b',
          installed: true,
          configured: true,
          source: 'ollama',
          warnings: [],
        },
      ]),
    );

    const { result } = renderHook(() =>
      useAssistantModels({ settings: { ...DEFAULT_SETTINGS }, profile: 'balanced', provider: 'local-ollama' }),
    );

    await waitFor(() => expect(result.current.status).toBe('success'));
    expect(result.current.models).toHaveLength(1);
    expect(result.current.models[0]?.id).toBe('qwen3.5:4b');
    expect(bridgeMocks.listAssistantModels).toHaveBeenCalledWith(
      expect.objectContaining({ profile: 'balanced' }),
      expect.objectContaining({ profile: 'balanced', provider: 'local-ollama', refresh: false }),
    );
  });

  it.each([
    ['ollama', 'local-ollama', 'qwen3.5:4b'],
    ['transformers', 'local-transformers', 'Qwen/Qwen2.5'],
  ] as const)(
    'resolves legacy provider %s to canonical discovery record %s',
    async (legacyProvider, canonicalProvider, modelId) => {
      bridgeMocks.listAssistantModels.mockResolvedValue(
        canonicalProviderModels({ provider: canonicalProvider, legacyProvider }),
      );

      const { result } = renderHook(() =>
        useAssistantModels({ settings: { ...DEFAULT_SETTINGS }, profile: 'balanced', provider: legacyProvider }),
      );

      await waitFor(() => expect(result.current.status).toBe('success'));
      expect(result.current.models).toEqual([
        expect.objectContaining({ provider: canonicalProvider, id: modelId }),
      ]);
      expect(bridgeMocks.listAssistantModels).toHaveBeenCalledWith(
        expect.objectContaining({ profile: 'balanced' }),
        expect.objectContaining({ provider: canonicalProvider }),
      );
    },
  );

  it.each([
    ['local-ollama', 'ollama'],
    ['local-transformers', 'transformers'],
  ] as const)('passes canonical provider %s through to discovery', async (canonicalProvider, legacyProvider) => {
    bridgeMocks.listAssistantModels.mockResolvedValue(
      canonicalProviderModels({ provider: canonicalProvider, legacyProvider }),
    );

    const { result } = renderHook(() =>
      useAssistantModels({ settings: { ...DEFAULT_SETTINGS }, profile: 'balanced', provider: canonicalProvider }),
    );

    await waitFor(() => expect(result.current.status).toBe('success'));
    expect(bridgeMocks.listAssistantModels).toHaveBeenCalledWith(
      expect.objectContaining({ profile: 'balanced' }),
      expect.objectContaining({ provider: canonicalProvider }),
    );
  });

  it('reports an empty discovery state when no candidates are returned', async () => {
    bridgeMocks.listAssistantModels.mockResolvedValue(providerModels([]));

    const { result } = renderHook(() =>
      useAssistantModels({ settings: { ...DEFAULT_SETTINGS }, profile: 'balanced', provider: 'local-ollama' }),
    );

    await waitFor(() => expect(result.current.status).toBe('empty'));
    expect(result.current.models).toEqual([]);
  });

  it('surfaces model discovery errors', async () => {
    bridgeMocks.listAssistantModels.mockRejectedValue(new Error('discovery failed'));

    const { result } = renderHook(() =>
      useAssistantModels({ settings: { ...DEFAULT_SETTINGS }, profile: 'balanced', provider: 'local-ollama' }),
    );

    await waitFor(() => expect(result.current.status).toBe('error'));
    expect(result.current.error).toEqual({
      code: 'MODEL_DISCOVERY_FAILED',
      message: 'discovery failed',
    });
  });

  it('refreshes discovery when trusted runtime configuration changes', async () => {
    bridgeMocks.listAssistantModels.mockResolvedValue(providerModels([]));

    const { rerender } = renderHook(
      ({ settings }) => useAssistantModels({ settings, profile: 'balanced', provider: 'local-ollama' }),
      {
        initialProps: {
          settings: { ...DEFAULT_SETTINGS },
        },
      },
    );

    await waitFor(() => expect(bridgeMocks.listAssistantModels).toHaveBeenCalledTimes(1));

    rerender({
      settings: { ...DEFAULT_SETTINGS, rootDir: '.imperaos/team/alternate-jobs' },
    });

    await waitFor(() => expect(bridgeMocks.listAssistantModels).toHaveBeenCalledTimes(2));
  });

  it('treats malformed provider discovery payloads as errors', async () => {
    bridgeMocks.listAssistantModels.mockResolvedValue({ providers: null });

    const { result } = renderHook(() =>
      useAssistantModels({ settings: { ...DEFAULT_SETTINGS }, profile: 'balanced', provider: 'local-ollama' }),
    );

    await waitFor(() => expect(result.current.status).toBe('error'));
    expect(result.current.error?.code).toBe('MODEL_DISCOVERY_FAILED');
  });
});
