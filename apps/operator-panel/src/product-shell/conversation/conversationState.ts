import type { AssistantSessionState } from '../../assistant/assistantTypes';

export type StoredMessage = { messageId: string; role: 'user' | 'assistant' | 'system'; body: string; createdAtUtc: string };
export type TransientTurn = { id: string; user: string | null; assistant: string | null; status: string | null };

function storedKey(role: StoredMessage['role'], body: string): string {
  return `${role}\u0000${body}`;
}

/** Returns only assistant-runtime parts that have not reached durable task storage. */
export function transientConversationTurns(state: AssistantSessionState, stored: StoredMessage[]): TransientTurn[] {
  const counts = new Map<string, number>();
  stored.forEach((message) => {
    const key = storedKey(message.role, message.body);
    counts.set(key, (counts.get(key) ?? 0) + 1);
  });
  const consume = (role: 'user' | 'assistant', body: string) => {
    if (!body) return false;
    const key = storedKey(role, body);
    const count = counts.get(key) ?? 0;
    if (!count) return false;
    counts.set(key, count - 1);
    return true;
  };
  return state.turns.flatMap((turn) => {
    const user = consume('user', turn.userMessage.text) ? null : turn.userMessage.text;
    const assistantText = turn.assistantMessage.text.trim();
    const assistant = assistantText && !consume('assistant', assistantText) ? assistantText : null;
    const status = turn.status === 'completed' ? null : turn.status.replace('_', ' ');
    return user || assistant || status ? [{ id: turn.id, user, assistant, status }] : [];
  });
}
