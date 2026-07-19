import { PRODUCT_IDENTITY } from './productIdentity';

export type CoreMode = 'auto' | 'external' | 'bundled';
export type LocaleMode = 'auto' | 'en' | 'tr';
export type UpdaterMode = 'off' | 'manual' | 'auto';
export type ThemeMode = 'light' | 'dark' | 'system';

export interface AssistantRuntimeSettings {
  assistantProvider: string;
  assistantFallbackProvider: string;
  assistantModel: string;
  assistantHfModelId: string;
}

export interface PanelSettings {
  mode: CoreMode;
  cliPath: string;
  bundledPythonPath: string;
  profile: string;
  rootDir: string;
  operatorId: string;
  locale: LocaleMode;
  remoteTelemetry: boolean;
  updaterMode: UpdaterMode;
  debugRaw: boolean;
  theme: ThemeMode;
  assistantProvider: string;
  assistantFallbackProvider: string;
  assistantModel: string;
  assistantHfModelId: string;
}

export const SETTINGS_KEY = `${PRODUCT_IDENTITY.slug}.operator.settings.v1`;

export const DEFAULT_ASSISTANT_RUNTIME_SETTINGS: AssistantRuntimeSettings = {
  assistantProvider: '',
  assistantFallbackProvider: '',
  assistantModel: '',
  assistantHfModelId: '',
};

export const DEFAULT_OPERATOR_ID = 'local-operator';

export const DEFAULT_SETTINGS: PanelSettings = {
  mode: 'auto',
  cliPath: '',
  bundledPythonPath: '',
  profile: 'balanced',
  rootDir: '.imperaos/team/jobs',
  operatorId: DEFAULT_OPERATOR_ID,
  locale: 'auto',
  remoteTelemetry: false,
  updaterMode: 'off',
  debugRaw: false,
  theme: 'system',
  ...DEFAULT_ASSISTANT_RUNTIME_SETTINGS,
};

const MODEL_TOKEN_PATTERN = /^[A-Za-z0-9._:/@+-]+$/;

function cleanRuntimeValue(value: string): string {
  return value.trim();
}

function normalizeStoredOperatorId(value: unknown): string {
  if (typeof value !== 'string') {
    return DEFAULT_OPERATOR_ID;
  }
  // An explicitly cleared identity must remain cleared so mutation controls
  // fail closed. Only a missing/invalid stored field receives the local default.
  return value.trim();
}

export function getAssistantRuntimeSettings(settings: PanelSettings): AssistantRuntimeSettings {
  return {
    assistantProvider: settings.assistantProvider,
    assistantFallbackProvider: settings.assistantFallbackProvider,
    assistantModel: settings.assistantModel,
    assistantHfModelId: settings.assistantHfModelId,
  };
}

export function assistantRuntimeOptionsFromSettings(settings: PanelSettings): {
  provider?: string;
  providerId?: string;
  fallbackProvider?: string;
  fallbackProviderId?: string;
  model?: string;
  hfModelId?: string;
} {
  const provider = cleanRuntimeValue(settings.assistantProvider);
  const legacyProviders = new Set(['auto', 'ollama', 'transformers']);
  const fallbackProvider = cleanRuntimeValue(settings.assistantFallbackProvider);
  return {
    provider: provider && legacyProviders.has(provider) ? provider : undefined,
    providerId: provider && !legacyProviders.has(provider) ? provider : undefined,
    fallbackProvider: fallbackProvider && legacyProviders.has(fallbackProvider) ? fallbackProvider : undefined,
    fallbackProviderId: fallbackProvider && !legacyProviders.has(fallbackProvider) ? fallbackProvider : undefined,
    model: cleanRuntimeValue(settings.assistantModel) || undefined,
    hfModelId: cleanRuntimeValue(settings.assistantHfModelId) || undefined,
  };
}

export function validateAssistantRuntimeSettings(settings: AssistantRuntimeSettings): string {
  const provider = cleanRuntimeValue(settings.assistantProvider).toLowerCase();
  const model = cleanRuntimeValue(settings.assistantModel);
  const hfModelId = cleanRuntimeValue(settings.assistantHfModelId);

  if (model && !MODEL_TOKEN_PATTERN.test(model)) {
    return 'Model may only include letters, numbers, dot, dash, underscore, slash, colon, plus, or @.';
  }
  if (hfModelId && !MODEL_TOKEN_PATTERN.test(hfModelId)) {
    return 'HF model id may only include letters, numbers, dot, dash, underscore, slash, colon, plus, or @.';
  }
  if ((provider === 'transformers' || provider === 'local-transformers') && model) {
    return 'Use HF model id for provider=transformers; leave Model empty.';
  }
  if ((provider === 'ollama' || provider === 'local-ollama') && hfModelId) {
    return 'Use Model for provider=ollama; leave HF model id empty.';
  }
  return '';
}

export function loadSettings(): PanelSettings {
  const raw = globalThis.localStorage?.getItem(SETTINGS_KEY);
  if (!raw) {
    return { ...DEFAULT_SETTINGS };
  }

  try {
    const parsed = JSON.parse(raw) as Partial<PanelSettings> & {
      assistantOpenAiApiKey?: unknown;
      assistantDeepSeekApiKey?: unknown;
    };
    const loaded: PanelSettings = {
      ...DEFAULT_SETTINGS,
      ...parsed,
      operatorId: normalizeStoredOperatorId(parsed.operatorId),
      assistantProvider: typeof parsed.assistantProvider === 'string' ? parsed.assistantProvider : '',
      assistantFallbackProvider:
        typeof parsed.assistantFallbackProvider === 'string' ? parsed.assistantFallbackProvider : '',
      assistantModel: typeof parsed.assistantModel === 'string' ? parsed.assistantModel : '',
      assistantHfModelId: typeof parsed.assistantHfModelId === 'string' ? parsed.assistantHfModelId : '',
    };
    delete (loaded as PanelSettings & { assistantOpenAiApiKey?: unknown }).assistantOpenAiApiKey;
    delete (loaded as PanelSettings & { assistantDeepSeekApiKey?: unknown }).assistantDeepSeekApiKey;
    if ('assistantOpenAiApiKey' in parsed || 'assistantDeepSeekApiKey' in parsed) {
      globalThis.localStorage?.setItem(SETTINGS_KEY, JSON.stringify(loaded));
    }
    return loaded;
  } catch {
    return { ...DEFAULT_SETTINGS };
  }
}

export function saveSettings(settings: PanelSettings): void {
  globalThis.localStorage?.setItem(SETTINGS_KEY, JSON.stringify(settings));
}

export function resolveLocale(locale: LocaleMode): 'en' | 'tr' {
  if (locale === 'en' || locale === 'tr') {
    return locale;
  }
  const browserLocale = (globalThis.navigator?.language ?? 'en').toLowerCase();
  return browserLocale.startsWith('tr') ? 'tr' : 'en';
}

export function resolveThemeMode(theme: ThemeMode): 'light' | 'dark' {
  if (theme === 'light' || theme === 'dark') {
    return theme;
  }
  return globalThis.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

export const OPERATOR_ID_PATTERN = /^[a-zA-Z0-9._-]{3,64}$/;

export function isOperatorIdValid(value: string): boolean {
  return OPERATOR_ID_PATTERN.test(value.trim());
}
