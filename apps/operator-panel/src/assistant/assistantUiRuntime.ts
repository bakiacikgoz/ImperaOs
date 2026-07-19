import { useMemo } from 'react';
import { useExternalStoreRuntime, type ThreadMessageLike } from '@assistant-ui/react';

import type { AssistantSessionState } from './assistantTypes';


export interface AssistantUiExternalMessage {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  createdAtUtc: string;
  status: 'running' | 'complete';
}

export function assistantUiMessages(state: AssistantSessionState): AssistantUiExternalMessage[] {
  return state.turns.flatMap((turn) => [
    {
      id: turn.userMessage.id,
      role: 'user' as const,
      text: turn.userMessage.text,
      createdAtUtc: turn.userMessage.createdAtUtc,
      status: 'complete' as const,
    },
    {
      id: turn.assistantMessage.id,
      role: 'assistant' as const,
      text: turn.assistantMessage.text,
      createdAtUtc: turn.startedAtUtc,
      status:
        turn.status === 'starting' || turn.status === 'streaming'
          ? ('running' as const)
          : ('complete' as const),
    },
  ]);
}

export function textFromAppendMessage(message: { content: readonly unknown[] }): string {
  return message.content
    .map((part) => {
      if (typeof part !== 'object' || part === null) return '';
      const candidate = part as { type?: unknown; text?: unknown };
      return candidate.type === 'text' && typeof candidate.text === 'string' ? candidate.text : '';
    })
    .join('')
    .trim();
}

function convertMessage(message: AssistantUiExternalMessage): ThreadMessageLike {
  return {
    id: message.id,
    role: message.role,
    content: [{ type: 'text', text: message.text }],
    createdAt: new Date(message.createdAtUtc),
    ...(message.role === 'assistant'
      ? {
          status:
            message.status === 'running'
              ? ({ type: 'running' } as const)
              : ({ type: 'complete', reason: 'stop' } as const),
        }
      : {}),
  };
}

export function useImperaAssistantUiRuntime({
  state,
  onNew,
  onCancel,
  onRegenerate,
}: {
  state: AssistantSessionState;
  onNew: (text: string) => void | Promise<void>;
  onCancel: () => void | Promise<void>;
  onRegenerate: (turnId: string) => void | Promise<void>;
}) {
  const messages = useMemo(() => assistantUiMessages(state), [state]);
  return useExternalStoreRuntime({
    messages,
    isRunning: state.status === 'starting' || state.status === 'streaming',
    convertMessage,
    onNew: async (message) => {
      const text = textFromAppendMessage(message);
      if (text) await onNew(text);
    },
    onCancel: async () => onCancel(),
    onReload: async (messageId) => {
      const turnId =
        messageId?.replace(/-(?:user|assistant)$/, '') ?? state.turns.at(-1)?.id;
      if (turnId) await onRegenerate(turnId);
    },
  });
}
