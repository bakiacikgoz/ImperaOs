import { describe, expect, it } from 'vitest';

import { getAssistantFixture } from '../../assistant/assistantFixtures';
import { transientConversationTurns } from './conversationState';

describe('transientConversationTurns', () => {
  it('does not duplicate persisted user and assistant messages after a task reload', () => {
    const state = getAssistantFixture('running');
    const turn = state.turns[0];
    turn.status = 'completed';
    const transient = transientConversationTurns(state, [
      { messageId: 'user-1', role: 'user', body: turn.userMessage.text, createdAtUtc: turn.userMessage.createdAtUtc },
      { messageId: 'assistant-1', role: 'assistant', body: turn.assistantMessage.text, createdAtUtc: turn.completedAtUtc ?? turn.startedAtUtc },
    ]);

    expect(transient).toEqual([]);
  });

  it('keeps only the assistant part transient while its completed response is being persisted', () => {
    const state = getAssistantFixture('running');
    const turn = state.turns[0];
    const transient = transientConversationTurns(state, [
      { messageId: 'user-1', role: 'user', body: turn.userMessage.text, createdAtUtc: turn.userMessage.createdAtUtc },
    ]);

    expect(transient).toMatchObject([{ id: turn.id, user: null, assistant: turn.assistantMessage.text }]);
  });
});
