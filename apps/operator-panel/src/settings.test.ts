import { beforeEach, describe, expect, it } from 'vitest';

import {
  DEFAULT_OPERATOR_ID,
  DEFAULT_SETTINGS,
  SETTINGS_KEY,
  assistantRuntimeOptionsFromSettings,
  isOperatorIdValid,
  loadSettings,
  resolveLocale,
  saveSettings,
  validateAssistantRuntimeSettings,
} from './settings';

beforeEach(() => {
  localStorage.clear();
});

describe('operator id validation', () => {
  it('uses only the canonical ImperaOS browser settings namespace', () => {
    const formerKey = ['ae', 'gis', 'os.operator.settings.v1'].join('');
    localStorage.setItem(formerKey, JSON.stringify({ ...DEFAULT_SETTINGS, profile: 'strict' }));

    expect(SETTINGS_KEY).toBe('imperaos.operator.settings.v1');
    expect(loadSettings().profile).toBe(DEFAULT_SETTINGS.profile);

    const nextSettings = { ...DEFAULT_SETTINGS, profile: 'fast' };
    saveSettings(nextSettings);
    expect(JSON.parse(localStorage.getItem('imperaos.operator.settings.v1') ?? '{}')).toEqual(nextSettings);
    expect(localStorage.getItem(formerKey)).not.toBeNull();
  });

  it('accepts expected format', () => {
    expect(isOperatorIdValid('ops-team_01')).toBe(true);
  });

  it('rejects invalid format', () => {
    expect(isOperatorIdValid('ab')).toBe(false);
    expect(isOperatorIdValid('bad value')).toBe(false);
    expect(isOperatorIdValid('bad*id')).toBe(false);
  });

  it('ships with a valid local operator id for first-run use', () => {
    expect(DEFAULT_SETTINGS.operatorId).toBe(DEFAULT_OPERATOR_ID);
    expect(isOperatorIdValid(DEFAULT_SETTINGS.operatorId)).toBe(true);
  });

  it('keeps an explicitly cleared operator id fail-closed while defaulting a missing legacy field', () => {
    localStorage.setItem(
      SETTINGS_KEY,
      JSON.stringify({
        mode: 'auto',
        profile: 'balanced',
        rootDir: '.imperaos/team/jobs',
        operatorId: '',
      }),
    );

    expect(loadSettings().operatorId).toBe('');

    localStorage.setItem(
      SETTINGS_KEY,
      JSON.stringify({
        mode: 'auto',
        profile: 'balanced',
        rootDir: '.imperaos/team/jobs',
      }),
    );

    expect(loadSettings().operatorId).toBe(DEFAULT_OPERATOR_ID);
  });

  it('preserves invalid explicit operator ids so the mutation gate can fail closed', () => {
    localStorage.setItem(
      SETTINGS_KEY,
      JSON.stringify({
        ...DEFAULT_SETTINGS,
        operatorId: 'ab',
      }),
    );

    expect(loadSettings().operatorId).toBe('ab');
    expect(isOperatorIdValid(loadSettings().operatorId)).toBe(false);
  });
});

describe('locale resolver', () => {
  it('respects explicit locale', () => {
    expect(resolveLocale('en')).toBe('en');
    expect(resolveLocale('tr')).toBe('tr');
  });
});

describe('assistant runtime settings', () => {
  it('loads legacy settings with profile-default assistant runtime fields', () => {
    localStorage.setItem(
      SETTINGS_KEY,
      JSON.stringify({
        mode: 'auto',
        profile: 'balanced',
        rootDir: '.imperaos/team/jobs',
      }),
    );

    expect(loadSettings()).toEqual(
      expect.objectContaining({
        assistantProvider: '',
        assistantFallbackProvider: '',
        assistantModel: '',
        assistantHfModelId: '',
      }),
    );
  });

  it('scrubs legacy assistant API keys from renderer storage', () => {
    localStorage.setItem(
      SETTINGS_KEY,
      JSON.stringify({
        ...DEFAULT_SETTINGS,
        assistantOpenAiApiKey: 'sk-openai',
        assistantDeepSeekApiKey: 'sk-deepseek',
      }),
    );

    const loaded = loadSettings();
    expect(loaded).not.toHaveProperty('assistantOpenAiApiKey');
    expect(loaded).not.toHaveProperty('assistantDeepSeekApiKey');
    expect(localStorage.getItem(SETTINGS_KEY)).not.toContain('sk-openai');
    expect(localStorage.getItem(SETTINGS_KEY)).not.toContain('sk-deepseek');
  });

  it('leaves empty assistant runtime overrides undefined for CLI defaults', () => {
    expect(assistantRuntimeOptionsFromSettings({ ...DEFAULT_SETTINGS })).toEqual({
      provider: undefined,
      providerId: undefined,
      fallbackProvider: undefined,
      fallbackProviderId: undefined,
      model: undefined,
      hfModelId: undefined,
    });
  });

  it('maps canonical provider ids separately from legacy provider flags', () => {
    expect(
      assistantRuntimeOptionsFromSettings({
        ...DEFAULT_SETTINGS,
        assistantProvider: 'company-internal',
        assistantFallbackProvider: 'local-transformers',
      }),
    ).toEqual(
      expect.objectContaining({
        provider: undefined,
        providerId: 'company-internal',
        fallbackProvider: undefined,
        fallbackProviderId: 'local-transformers',
      }),
    );
  });

  it('validates provider-specific model override combinations', () => {
    expect(
      validateAssistantRuntimeSettings({
        assistantProvider: 'ollama',
        assistantFallbackProvider: 'transformers',
        assistantModel: 'qwen3.5:4b',
        assistantHfModelId: '',
      }),
    ).toBe('');

    expect(
      validateAssistantRuntimeSettings({
        assistantProvider: 'transformers',
        assistantFallbackProvider: '',
        assistantModel: 'qwen3.5:4b',
        assistantHfModelId: '',
      }),
    ).toContain('Use HF model id');
  });
});
