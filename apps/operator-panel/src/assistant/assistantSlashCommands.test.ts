import { describe, expect, it } from 'vitest';

import { resolveAssistantSlashCommand } from './assistantSlashCommands';

describe('assistant slash command registry', () => {
  it('maps a registered command to safe prompt controls without changing the user request', () => {
    expect(resolveAssistantSlashCommand('/inspect-run summarize the deployment')).toEqual({
      command: '/inspect-run',
      message: 'summarize the deployment',
      contextAttachmentKinds: ['active_run'],
      toolIntents: ['inspect_run'],
    });
  });

  it('keeps unsupported slash commands out of the governed prompt', () => {
    expect(resolveAssistantSlashCommand('/full-access deploy now')).toBeNull();
  });
});
