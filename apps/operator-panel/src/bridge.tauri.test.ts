import { afterEach, describe, expect, it, vi } from 'vitest';

import { DEFAULT_SETTINGS } from './settings';

type BridgeModule = typeof import('./bridge');

function mockTauriInvoke(data: unknown = {}): ReturnType<typeof vi.fn> {
  const invoke = vi.fn().mockResolvedValue({
    ok: true,
    data,
    error: null,
  });

  vi.stubGlobal('__TAURI_INTERNALS__', {});
  vi.doMock('@tauri-apps/api/core', () => ({ invoke }));
  vi.doMock('@tauri-apps/api/event', () => ({ listen: vi.fn() }));
  return invoke;
}

async function importBridgeWithInvoke(data?: unknown): Promise<{
  invoke: ReturnType<typeof vi.fn>;
  bridge: BridgeModule;
}> {
  const invoke = mockTauriInvoke(data);
  return {
    invoke,
    bridge: await import('./bridge'),
  };
}

describe('bridge tauri contract', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.doUnmock('@tauri-apps/api/core');
    vi.doUnmock('@tauri-apps/api/event');
    vi.resetModules();
  });

  it('passes handshake config to the Tauri command', async () => {
    const { invoke, bridge } = await importBridgeWithInvoke({
      uiVersion: '0.5.0-beta.1',
      coreVersion: '0.4.1',
      contractVersion: '3.0',
      capabilities: {},
      doctor: {},
    });

    await bridge.handshake({
      ...DEFAULT_SETTINGS,
      mode: 'external',
      cliPath: '/usr/local/bin/imperaos',
      profile: 'balanced',
      rootDir: '.imperaos/team/jobs',
    });

    expect(invoke).toHaveBeenCalledWith(
      'bridge_handshake',
      expect.objectContaining({
        config: expect.objectContaining({
          mode: 'external',
          cliPath: '/usr/local/bin/imperaos',
          profile: 'balanced',
          rootDir: '.imperaos/team/jobs',
        }),
      }),
    );
  });

  it('never passes renderer provider secrets through bridge config env', async () => {
    const { invoke, bridge } = await importBridgeWithInvoke({
      contractVersion: 'operator-panel.assistant-provider-models/v4',
      profile: 'balanced',
      provider: 'all',
      generatedAtUtc: '2026-06-07T00:00:00.000Z',
      providers: [],
    });

    const pollutedLegacySettings = {
      ...DEFAULT_SETTINGS,
      assistantOpenAiApiKey: 'sk-openai',
      assistantDeepSeekApiKey: 'sk-deepseek',
    } as typeof DEFAULT_SETTINGS & {
      assistantOpenAiApiKey: string;
      assistantDeepSeekApiKey: string;
    };
    await bridge.listAssistantModels(
      pollutedLegacySettings,
      { profile: 'balanced', provider: 'all' },
    );

    const call = invoke.mock.calls.find(([command]) => command === 'bridge_assistant_provider_models');
    const config = (call?.[1] as { config?: { env?: Record<string, string> } }).config;
    expect(config?.env).toMatchObject({
      IMPERAOS_PROFILE_NAME: 'balanced',
      IMPERAOS_TEAM_ARTIFACT_DIR: DEFAULT_SETTINGS.rootDir,
    });
    expect(config?.env).not.toHaveProperty('IMPERAOS_REMOTE_PROVIDERS_ENABLED');
    expect(config?.env).not.toHaveProperty('OPENAI_API_KEY');
    expect(config?.env).not.toHaveProperty('DEEPSEEK_API_KEY');
  });

  it('passes assistant provider and model options to the Tauri command', async () => {
    const { invoke, bridge } = await importBridgeWithInvoke({
      contractVersion: '3.0',
      assistantTurnId: 'turn-tauri',
      sessionId: 'session-tauri',
      processId: 42,
      status: 'started',
    });

    await bridge.startAssistantTurn(
      { ...DEFAULT_SETTINGS },
      {
        assistantTurnId: 'turn-tauri',
        sessionId: 'session-tauri',
        userMessage: 'hello',
        compiledPrompt: 'compiled prompt',
        profile: 'balanced',
        provider: 'auto',
        providerId: 'company-internal',
        fallbackProvider: 'transformers',
        fallbackProviderId: 'local-transformers',
        model: 'qwen3.5:4b',
        hfModelId: 'Qwen/Qwen2.5',
      },
    );

    expect(invoke).toHaveBeenCalledWith(
      'bridge_assistant_start_turn',
      expect.objectContaining({
        config: expect.objectContaining({
          profile: 'balanced',
          timeoutMs: 120000,
        }),
        assistantTurnId: 'turn-tauri',
        sessionId: 'session-tauri',
        userMessage: 'hello',
        compiledPrompt: 'compiled prompt',
        provider: 'auto',
        providerId: 'company-internal',
        fallbackProvider: 'transformers',
        fallbackProviderId: 'local-transformers',
        model: 'qwen3.5:4b',
        hfModelId: 'Qwen/Qwen2.5',
      }),
    );
  });

  it('passes assistant cancel requests to the Tauri command', async () => {
    const { invoke, bridge } = await importBridgeWithInvoke({
      contractVersion: '3.0',
      assistantTurnId: 'turn-tauri',
      sessionId: 'session-tauri',
      processId: 42,
      status: 'cancelled',
    });

    await bridge.cancelAssistantTurn({ ...DEFAULT_SETTINGS }, 'turn-tauri');

    expect(invoke).toHaveBeenCalledWith(
      'bridge_assistant_cancel_turn',
      expect.objectContaining({
        assistantTurnId: 'turn-tauri',
      }),
    );
  });

  it('passes assistant model discovery requests to the Tauri command', async () => {
    const { invoke, bridge } = await importBridgeWithInvoke({
      contractVersion: 'operator-panel.assistant-provider-models/v2',
      profile: 'balanced',
      provider: 'local-ollama',
      generatedAtUtc: '2026-06-07T00:00:00Z',
      providers: [],
    });

    await bridge.listAssistantModels(
      { ...DEFAULT_SETTINGS, profile: 'balanced' },
      { profile: 'balanced', provider: 'ollama', refresh: true },
    );

    expect(invoke).toHaveBeenCalledWith(
      'bridge_assistant_provider_models',
      expect.objectContaining({
        config: expect.objectContaining({
          profile: 'balanced',
          timeoutMs: 15000,
        }),
        profile: 'balanced',
        provider: 'ollama',
        refresh: true,
      }),
    );
  });

  it('passes config resolve provider and model overrides to the Tauri command', async () => {
    const { invoke, bridge } = await importBridgeWithInvoke({ contract_version: '3.0', status: 'ok' });

    await bridge.resolveConfig(
      { ...DEFAULT_SETTINGS, profile: 'balanced' },
      {
        provider: 'ollama',
        fallbackProvider: 'transformers',
        model: 'qwen3.5:4b',
        hfModelId: 'Qwen/Qwen2.5',
      },
    );

    expect(invoke).toHaveBeenCalledWith(
      'bridge_config_resolve',
      expect.objectContaining({
        config: expect.objectContaining({ profile: 'balanced' }),
        provider: 'ollama',
        fallbackProvider: 'transformers',
        model: 'qwen3.5:4b',
        hfModelId: 'Qwen/Qwen2.5',
      }),
    );
  });

  it('passes control-plane snapshot requests to the Tauri command', async () => {
    const { invoke, bridge } = await importBridgeWithInvoke({
      contractVersion: 'control-plane.snapshot/v1',
      dataSource: {
        mode: 'tauri_live',
        isMock: false,
        isSilentFallback: false,
        lastRefreshUtc: '2026-06-01T12:00:00Z',
        ageMs: 0,
        freshness: 'fresh',
        contractVersion: 'control-plane.snapshot/v1',
      },
    });

    await bridge.fetchControlPlaneSnapshot({ ...DEFAULT_SETTINGS, profile: 'enterprise' });

    expect(invoke).toHaveBeenCalledWith(
      'bridge_control_plane_snapshot',
      expect.objectContaining({
        config: expect.objectContaining({
          profile: 'enterprise',
          timeoutMs: 30000,
        }),
      }),
    );
  });

  it('passes pilot install rehearsal requests to the Tauri command', async () => {
    const { invoke, bridge } = await importBridgeWithInvoke({
      version: 'control-plane.install-rehearsal/v1',
      status: 'pass',
    });

    await bridge.runInstallRehearsal(
      { ...DEFAULT_SETTINGS, profile: 'enterprise' },
      {
        targetRoot: '.imperaos/rehearsal/design-partner',
        output: 'artifacts/install-rehearsal/report.json',
        mode: 'source-cli',
      },
    );

    expect(invoke).toHaveBeenCalledWith(
      'bridge_install_rehearsal',
      expect.objectContaining({
        config: expect.objectContaining({
          profile: 'enterprise',
          timeoutMs: 120000,
        }),
        targetRoot: '.imperaos/rehearsal/design-partner',
        output: 'artifacts/install-rehearsal/report.json',
        mode: 'source-cli',
      }),
    );
  });

  it('passes pilot security review requests to the Tauri command', async () => {
    const { invoke, bridge } = await importBridgeWithInvoke({
      version: 'control-plane.security-review/v1',
      status: 'pass',
    });

    await bridge.generateSecurityReview(
      { ...DEFAULT_SETTINGS, profile: 'enterprise' },
      {
        outputRoot: 'artifacts/security-review',
        evidenceRoot: 'artifacts/evidence-corpus/valid',
      },
    );

    expect(invoke).toHaveBeenCalledWith(
      'bridge_security_review',
      expect.objectContaining({
        config: expect.objectContaining({
          profile: 'enterprise',
          timeoutMs: 120000,
        }),
        outputRoot: 'artifacts/security-review',
        evidenceRoot: 'artifacts/evidence-corpus/valid',
      }),
    );
  });

  it('passes team submit model metadata and run identifiers to the Tauri command', async () => {
    const { invoke, bridge } = await importBridgeWithInvoke({ contractVersion: '3.0', jobId: 'job-live' });

    await bridge.submitTeamRun(
      { ...DEFAULT_SETTINGS },
      {
        specPath: 'examples/team/restricted_pilot.yaml',
        request: 'inspect queue',
        caseId: 'case-1',
        jobId: 'job-ui-1',
        provider: 'ollama',
        fallbackProvider: 'transformers',
        model: 'qwen3.5:4b',
        hfModelId: 'Qwen/Qwen2.5',
      },
    );

    expect(invoke).toHaveBeenCalledWith(
      'bridge_team_submit',
      expect.objectContaining({
        config: expect.objectContaining({ rootDir: DEFAULT_SETTINGS.rootDir }),
        specPath: 'examples/team/restricted_pilot.yaml',
        request: 'inspect queue',
        caseId: 'case-1',
        jobId: 'job-ui-1',
        provider: 'ollama',
        fallbackProvider: 'transformers',
        model: 'qwen3.5:4b',
        hfModelId: 'Qwen/Qwen2.5',
      }),
    );
  });

  it('passes approval decide and execute actor args to the Tauri commands', async () => {
    const { invoke, bridge } = await importBridgeWithInvoke({ contract_version: '3.0' });

    await bridge.decideApproval({ ...DEFAULT_SETTINGS }, 'apr-1', false, 'qa-operator', 'operator rejected');
    await bridge.executeApproval({ ...DEFAULT_SETTINGS }, 'apr-1', 'qa-operator');

    expect(invoke).toHaveBeenNthCalledWith(
      1,
      'bridge_approval_decide',
      expect.objectContaining({
        approvalId: 'apr-1',
        approve: false,
        operatorId: 'qa-operator',
        reason: 'operator rejected',
      }),
    );
    expect(invoke).toHaveBeenNthCalledWith(
      2,
      'bridge_approval_execute',
      expect.objectContaining({
        approvalId: 'apr-1',
        operatorId: 'qa-operator',
      }),
    );
  });

  it('passes computer-use submit and control args to the Tauri commands', async () => {
    const { invoke, bridge } = await importBridgeWithInvoke({ contractVersion: '3.0', jobId: 'job-cu' });

    await bridge.submitComputerUseRun(
      { ...DEFAULT_SETTINGS },
      {
        request: 'open the dashboard',
        caseId: 'case-cu',
        jobId: 'job-cu',
        mode: 'step_approval',
        runtime: 'vision-first',
        provider: 'ollama',
        fallbackProvider: 'transformers',
        model: 'qwen3.5:4b',
        hfModelId: 'Qwen/Qwen2.5',
      },
    );
    await bridge.pauseComputerUseSession({ ...DEFAULT_SETTINGS }, 'job-cu');
    await bridge.resumeComputerUseSession({ ...DEFAULT_SETTINGS }, 'job-cu');
    await bridge.stopComputerUseSession({ ...DEFAULT_SETTINGS }, 'job-cu');

    expect(invoke).toHaveBeenNthCalledWith(
      1,
      'bridge_computer_use_submit',
      expect.objectContaining({
        request: 'open the dashboard',
        caseId: 'case-cu',
        jobId: 'job-cu',
        mode: 'step_approval',
        runtime: 'vision-first',
        provider: 'ollama',
        fallbackProvider: 'transformers',
        model: 'qwen3.5:4b',
        hfModelId: 'Qwen/Qwen2.5',
      }),
    );
    expect(invoke).toHaveBeenNthCalledWith(
      2,
      'bridge_computer_use_pause',
      expect.objectContaining({ jobId: 'job-cu' }),
    );
    expect(invoke).toHaveBeenNthCalledWith(
      3,
      'bridge_computer_use_resume',
      expect.objectContaining({ jobId: 'job-cu' }),
    );
    expect(invoke).toHaveBeenNthCalledWith(
      4,
      'bridge_computer_use_stop',
      expect.objectContaining({ jobId: 'job-cu' }),
    );
  });

  it('passes artifact read and run export args to the Tauri commands', async () => {
    const { invoke, bridge } = await importBridgeWithInvoke({ contractVersion: '3.0' });

    await bridge.readArtifact({ ...DEFAULT_SETTINGS, rootDir: '.imperaos/jobs' }, 'job-1', 'status.json', 4096);
    await bridge.exportRunArtifacts({ ...DEFAULT_SETTINGS }, 'job-1', './exports/job-1');

    expect(invoke).toHaveBeenNthCalledWith(
      1,
      'bridge_read_artifact',
      expect.objectContaining({
        rootDir: '.imperaos/jobs',
        jobId: 'job-1',
        artifactName: 'status.json',
        maxBytes: 4096,
      }),
    );
    expect(invoke).toHaveBeenNthCalledWith(
      2,
      'bridge_team_export',
      expect.objectContaining({
        jobId: 'job-1',
        exportDir: './exports/job-1',
      }),
    );
  });
});
