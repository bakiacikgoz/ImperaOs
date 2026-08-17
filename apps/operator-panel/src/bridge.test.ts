import { describe, expect, it } from 'vitest';

import {
  cancelAssistantTurn,
  decideApproval,
  executeApproval,
  exportRunArtifacts,
  getComputerUseSessionState,
  getComputerUseSummary,
  handshake,
  isBridgePreviewMode,
  isPreviewAllowedForEnv,
  listAssistantModels,
  listRuns,
  pauseComputerUseSession,
  readArtifact,
  resumeComputerUseSession,
  resolveConfig,
  showApproval,
  startAssistantTurn,
  stopComputerUseSession,
  submitComputerUseRun,
  submitTeamRun,
  tailEvents,
} from './bridge';
import { DEFAULT_SETTINGS } from './settings';

describe('bridge preview fallback', () => {
  it('requires dev, test, or explicit env flag for browser preview mode', () => {
    expect(isPreviewAllowedForEnv({ MODE: 'production', DEV: false })).toBe(false);
    expect(isPreviewAllowedForEnv({ MODE: 'production', DEV: false, VITE_OPERATOR_PANEL_PREVIEW: '1' })).toBe(true);
    expect(isPreviewAllowedForEnv({ MODE: 'test', DEV: false })).toBe(true);
    expect(isPreviewAllowedForEnv({ MODE: 'production', DEV: true })).toBe(true);
  });

  it('returns preview handshake data when tauri runtime is unavailable', async () => {
    expect(isBridgePreviewMode()).toBe(true);

    const payload = await handshake({ ...DEFAULT_SETTINGS });
    const record = payload as Record<string, unknown>;
    const capabilities = record.capabilities as Record<string, unknown>;

    expect(record.coreVersion).toBe('0.6.0-preview');
    expect(record.contractVersion).toBe('3.0');
    expect(capabilities.previewMode).toBe(true);
  });

  it('returns preview submit payloads for task workspace actions', async () => {
    const [teamPayload, computerUsePayload] = await Promise.all([
      submitTeamRun(
        { ...DEFAULT_SETTINGS },
        {
          specPath: 'examples/team/restricted_pilot.yaml',
          request: 'inspect queue',
        },
      ),
      submitComputerUseRun(
        { ...DEFAULT_SETTINGS },
        {
          request: 'open "https://preview.imperaos.local/form"',
          mode: 'step_approval',
          runtime: 'vision-first',
        },
      ),
    ]);

    const teamRecord = teamPayload as Record<string, unknown>;
    expect(teamRecord.contractVersion).toBe('3.0');
    expect(teamRecord.jobId).toBe('job-ui-preview-1');

    const computerUseRecord = computerUsePayload as Record<string, unknown>;
    expect(computerUseRecord.contractVersion).toBe('3.0');
    expect(computerUseRecord.jobId).toBe('job-ui-preview-cu-1');
    expect(computerUseRecord.runtime).toBe('vision-first');
  });

  it('returns preview assistant start payloads without starting a bridge process', async () => {
    const payload = await startAssistantTurn(
      { ...DEFAULT_SETTINGS },
      {
        assistantTurnId: 'turn-preview',
        sessionId: 'session-preview',
        userMessage: 'hello',
        compiledPrompt: 'hello',
      },
    );

    expect(payload.contractVersion).toBe('3.0');
    expect(payload.assistantTurnId).toBe('turn-preview');
    expect(payload.sessionId).toBe('session-preview');
    expect(payload.processId).toBeNull();
  });

  it('returns preview assistant cancel payloads without a bridge process', async () => {
    const payload = await cancelAssistantTurn({ ...DEFAULT_SETTINGS }, 'turn-preview');

    expect(payload.contractVersion).toBe('3.0');
    expect(payload.assistantTurnId).toBe('turn-preview');
    expect(payload.processId).toBeNull();
    expect(payload.status).toBe('cancelled');
  });

  it('returns filtered preview assistant provider models', async () => {
    const payload = await listAssistantModels(
      { ...DEFAULT_SETTINGS, profile: 'balanced' },
      { profile: 'balanced', provider: 'ollama' },
    );

    expect(payload.contractVersion).toBe('operator-panel.assistant-provider-models/v4');
    expect(payload.provider).toBe('ollama');
    expect(payload.providers).toHaveLength(1);
    expect(payload.providers[0]?.provider).toBe('local-ollama');
    expect(payload.providers[0]?.legacyProvider).toBe('ollama');
    expect(payload.providers[0]?.models[0]?.id).toBe('qwen3.5:4b');
  });

  it('treats preview auto assistant provider as all providers', async () => {
    const payload = await listAssistantModels(
      { ...DEFAULT_SETTINGS, profile: 'balanced' },
      { profile: 'balanced', provider: 'auto' },
    );

    expect(payload.contractVersion).toBe('operator-panel.assistant-provider-models/v4');
    expect(payload.provider).toBe('all');
    expect(payload.providers.map((item) => item.provider)).toContain('openai-public');
    expect(payload.providers.map((item) => item.provider)).toContain('local-ollama');
  });

  it('applies preview config resolve provider and model overrides', async () => {
    const payload = await resolveConfig(
      { ...DEFAULT_SETTINGS },
      {
        provider: 'ollama',
        fallbackProvider: 'transformers',
        model: 'qwen3.5:4b',
        hfModelId: 'Qwen/Qwen2.5',
      },
    );
    const record = payload as Record<string, unknown>;
    const resolved = record.resolved as Record<string, unknown>;
    const sourceMap = record.source_map as Record<string, unknown>;

    expect(resolved.llm_provider).toBe('ollama');
    expect(resolved.fallback_provider).toBe('transformers');
    expect(resolved.model_name).toBe('qwen3.5:4b');
    expect(resolved.hf_model_id).toBe('Qwen/Qwen2.5');
    expect(sourceMap.model_name).toBe('cli');
  });

  it('returns preview computer-use summary payloads', async () => {
    const payload = await getComputerUseSummary({ ...DEFAULT_SETTINGS }, 2);
    const record = payload as Record<string, unknown>;
    const window = record.window as Record<string, unknown>;
    const counts = record.counts as Record<string, unknown>;

    expect(record.contractVersion).toBe('3.0');
    expect(window.limit).toBe(2);
    expect(counts.blocked).toBe(1);
  });

  it('returns preview control payloads for computer-use sessions', async () => {
    const [pause, resume, stop, state] = await Promise.all([
      pauseComputerUseSession({ ...DEFAULT_SETTINGS }, 'job-ui-preview-cu-1'),
      resumeComputerUseSession({ ...DEFAULT_SETTINGS }, 'job-ui-preview-cu-1'),
      stopComputerUseSession({ ...DEFAULT_SETTINGS }, 'job-ui-preview-cu-1'),
      getComputerUseSessionState({ ...DEFAULT_SETTINGS }, 'job-ui-preview-cu-1'),
    ]);

    expect((pause as Record<string, unknown>).requested).toBe('pause');
    expect((pause as Record<string, unknown>).outcome).toBe('rejected');
    expect((resume as Record<string, unknown>).requested).toBe('resume');
    expect((resume as Record<string, unknown>).reason).toBe('approval_not_executed');
    expect((stop as Record<string, unknown>).requested).toBe('stop');
    expect((stop as Record<string, unknown>).outcome).toBe('accepted');
    expect(((state as Record<string, unknown>).computer_use as Record<string, unknown>).stage).toBe(
      'require_approval',
    );
    expect(((state as Record<string, unknown>).recovery as Record<string, unknown>).resume_allowed).toBe(
      false,
    );
  });

  it('returns preview config resolve payload for system workspace', async () => {
    const payload = await resolveConfig({ ...DEFAULT_SETTINGS });
    const record = payload as Record<string, unknown>;
    expect(record.contract_version).toBe('3.0');
    expect(record.status).toBe('ok');
    expect((record.resolved as Record<string, unknown>).profile_name).toBe(DEFAULT_SETTINGS.profile);
  });

  it('returns runtime-shaped preview payloads for approvals and runs', async () => {
    const [approval, runs, artifact, events, approvalDecision, approvalExecution, exportPayload] =
      await Promise.all([
        showApproval({ ...DEFAULT_SETTINGS }, 'apr_preview'),
        listRuns({ ...DEFAULT_SETTINGS }),
        readArtifact({ ...DEFAULT_SETTINGS }, 'job-preview', 'status.json'),
        tailEvents({ ...DEFAULT_SETTINGS }, 'job-preview', 0),
        decideApproval({ ...DEFAULT_SETTINGS }, 'apr_preview', true, 'qa-operator', 'preview smoke'),
        executeApproval({ ...DEFAULT_SETTINGS }, 'apr_preview', 'qa-operator'),
        exportRunArtifacts({ ...DEFAULT_SETTINGS }, 'job-preview', './exports/job-preview'),
      ]);

    const approvalRecord = approval as Record<string, unknown>;
    expect(approvalRecord.contract_version).toBe('3.0');
    expect((approvalRecord.ticket as Record<string, unknown>).approval_id).toBe('apr_preview');

    const runRecord = runs as Record<string, unknown>;
    expect(runRecord.contract_version).toBe('3.0');
    expect(runRecord.count).toBeGreaterThan(0);

    const artifactRecord = artifact as Record<string, unknown>;
    expect(artifactRecord.contractVersion).toBe('3.0');
    expect(artifactRecord.artifactName).toBe('status.json');
    expect(
      ((artifactRecord.payload as Record<string, unknown>).computer_use as Record<string, unknown>).stage,
    ).toBe('require_approval');

    expect(events.contractVersion).toBe('3.0');
    expect(events.events.length).toBeGreaterThan(0);

    expect((approvalDecision as Record<string, unknown>).approval_id).toBe('apr_preview');
    expect(((approvalDecision as Record<string, unknown>).ticket as Record<string, unknown>).status).toBe(
      'approved',
    );
    expect((approvalExecution as Record<string, unknown>).runtime_mode).toBe('preview_fixture');
    expect((approvalExecution as Record<string, unknown>).isMock).toBe(true);
    expect(((approvalExecution as Record<string, unknown>).ticket as Record<string, unknown>).status).toBe(
      'simulated',
    );
    expect((exportPayload as Record<string, unknown>).export_dir).toBe('./exports/job-preview');
  });
});
