import { describe, expect, it } from 'vitest';

import { createAssistantSession } from './assistantMappers';
import { buildAssistantPrompt } from './assistantPromptBuilder';

describe('assistant prompt builder', () => {
  it('builds a prompt without selected run context', () => {
    const result = buildAssistantPrompt({
      userMessage: 'hello',
      session: createAssistantSession('session-test'),
      selectedRunStatus: null,
      selectedRunEvents: [],
      selectedArtifacts: {},
      pendingApproval: null,
      systemHealth: null,
    });

    expect(result.compiledPrompt).toContain('## User message');
    expect(result.compiledPrompt).toContain('hello');
    expect(result.compiledPrompt).toContain('untrusted context');
  });

  it('redacts obvious secrets before compiling context', () => {
    const result = buildAssistantPrompt({
      userMessage: 'inspect sk-abc1234567890000',
      session: createAssistantSession('session-test'),
      selectedRunStatus: { token: 'ghp_abcdefghijklmnopqrstuvwxyz' },
      selectedRunEvents: [],
      selectedArtifacts: {},
      pendingApproval: null,
      systemHealth: null,
    });

    expect(result.compiledPrompt).not.toContain('sk-abc1234567890000');
    expect(result.compiledPrompt).not.toContain('ghp_abcdefghijklmnopqrstuvwxyz');
    expect(result.compiledPrompt).toContain('[redacted-secret]');
  });

  it('honors compiled prompt character limits', () => {
    const result = buildAssistantPrompt({
      userMessage: 'x'.repeat(1000),
      session: createAssistantSession('session-test'),
      selectedRunStatus: { big: 'y'.repeat(1000) },
      selectedRunEvents: [{ event: 'one', payload: 'z'.repeat(1000) }],
      selectedArtifacts: { 'status.json': { big: 'a'.repeat(1000) } },
      pendingApproval: null,
      systemHealth: null,
      maxChars: 500,
    });

    expect(result.characterCount).toBeLessThanOrEqual(500);
    expect(result.truncated).toBe(true);
    expect(result.omittedSections).toContain('compiledPromptTail');
  });

  it('only includes selected safe context attachments and tool intents', () => {
    const result = buildAssistantPrompt({
      userMessage: 'explain blocker',
      session: createAssistantSession('session-test'),
      selectedRunStatus: { run_id: 'run-test' },
      selectedRunEvents: [{ event: 'approval_required' }],
      selectedArtifacts: { 'status.json': { status: 'blocked' } },
      pendingApproval: { approval_id: 'apr-test' },
      systemHealth: { health: 'Healthy' },
      controls: {
        contextAttachmentKinds: ['active_run', 'approval_summary'],
        toolIntents: ['explain_policy_blocker'],
      },
    });

    expect(result.compiledPrompt).toContain('## Allowed tool intents');
    expect(result.compiledPrompt).toContain('explain_policy_blocker');
    expect(result.compiledPrompt).toContain('## Selected run status');
    expect(result.compiledPrompt).toContain('## Pending approval');
    expect(result.compiledPrompt).not.toContain('## Recent normalized events');
    expect(result.compiledPrompt).not.toContain('## Artifact summary');
    expect(result.compiledPrompt).not.toContain('## System health');
  });

  it('redacts adversarial canaries and absolute paths from run and event context', () => {
    const result = buildAssistantPrompt({
      userMessage: 'inspect the selected run',
      session: createAssistantSession('session-security'),
      selectedRunStatus: {
        message: 'synthetic-provider-secret-canary',
        path: 'C:/synthetic/private/path',
      },
      selectedRunEvents: [{ message: 'failed at C:\\Users\\private\\trace.json' }],
      selectedArtifacts: {},
      pendingApproval: null,
      systemHealth: null,
    });

    expect(result.compiledPrompt).not.toContain('synthetic-provider-secret-canary');
    expect(result.compiledPrompt).not.toContain('C:/synthetic/private/path');
    expect(result.compiledPrompt).not.toContain('C:\\Users\\private\\trace.json');
    expect(result.compiledPrompt).not.toContain('Users');
    expect(result.compiledPrompt).not.toContain('private');
    expect(result.compiledPrompt).not.toContain('trace.json');
    expect(result.compiledPrompt).toContain('[redacted');
  });

  it('redacts arbitrary POSIX, UNC, and extended Windows absolute paths', () => {
    const result = buildAssistantPrompt({
      userMessage: 'inspect the selected run',
      session: createAssistantSession('session-path-redaction'),
      selectedRunStatus: null,
      selectedRunEvents: [
        { message: 'failed at /opt/impera/private/trace.json' },
        { message: 'credential at /root/.ssh/id_rsa' },
        { message: 'network at \\\\server\\share\\private\\trace.json' },
        { message: 'extended at \\\\?\\C:\\private\\trace.json' },
        { message: "quoted at '/opt/impera/private/trace.json'" },
        { message: "spaced at 'C:\\Program Files\\ImperaOS\\trace.json'" },
      ],
      selectedArtifacts: {},
      pendingApproval: null,
      systemHealth: null,
    });

    for (const fragment of [
      'opt', 'impera', 'root', '.ssh', 'server', 'share', 'trace.json', 'Program Files', 'ImperaOS',
    ]) {
      expect(result.compiledPrompt).not.toContain(fragment);
    }
    expect(result.compiledPrompt).toContain('[redacted-path]');
  });

  it('projects artifact metadata and a typed context request without raw content', () => {
    const result = buildAssistantPrompt({
      userMessage: 'Update the selected paragraph.',
      session: createAssistantSession('session-artifact'),
      selectedRunStatus: null,
      selectedRunEvents: [],
      selectedArtifacts: {
        brief: {
          artifactId: 'artifact-1',
          currentRevisionId: 'revision-2',
          currentRevisionNumber: 2,
          kind: 'document',
          blocks: [{ text: 'raw-secret-artifact-body' }],
        },
      },
      artifactContextRequest: {
        artifactId: 'artifact-1',
        revisionId: 'revision-2',
        purpose: 'edit',
        allowedScopes: ['selection', 'metadata'],
        selection: { kind: 'document', blockIds: ['block-1'] },
      },
      pendingApproval: null,
      systemHealth: null,
    });

    expect(result.compiledPrompt).toContain('## Governed artifact context request');
    expect(result.compiledPrompt).toContain('artifact-1');
    expect(result.compiledPrompt).toContain('block-1');
    expect(result.compiledPrompt).not.toContain('raw-secret-artifact-body');
    expect(result.compiledPrompt).not.toContain('"blocks"');
  });
});
