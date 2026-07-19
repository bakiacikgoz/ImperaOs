import { describe, expect, it } from 'vitest';

import { createAssistantSession, createAssistantTurn } from './assistantMappers';
import { assistantUiMessages, textFromAppendMessage } from './assistantUiRuntime';


describe('assistant-ui ExternalStore parity adapter', () => {
  it('projects existing turns into stable user and assistant messages', () => {
    const turn = createAssistantTurn({
      id: 'turn-1',
      sessionId: 'session-1',
      userMessage: 'Create a plan',
      createdAtUtc: '2026-07-16T08:00:00Z',
    });
    turn.status = 'streaming';
    turn.assistantMessage.text = 'Drafting';
    const state = { ...createAssistantSession('session-1'), turns: [turn], status: 'streaming' as const };

    expect(assistantUiMessages(state)).toEqual([
      {
        id: 'turn-1-user',
        role: 'user',
        text: 'Create a plan',
        createdAtUtc: '2026-07-16T08:00:00Z',
        status: 'complete',
      },
      {
        id: 'turn-1-assistant',
        role: 'assistant',
        text: 'Drafting',
        createdAtUtc: '2026-07-16T08:00:00Z',
        status: 'running',
      },
    ]);
  });

  it('accepts only text parts from assistant-ui composer messages', () => {
    expect(
      textFromAppendMessage({
        content: [
          { type: 'text', text: 'hello' },
          { type: 'text', text: ' world' },
          { type: 'image', image: 'data:image/png;base64,blocked' },
        ],
      }),
    ).toBe('hello world');
  });
});
