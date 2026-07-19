import type { ChatTransport, UIMessage, UIMessageChunk } from 'ai';

import { normalizeAssistantStreamEvent } from './assistantMappers';
import type { AssistantComposerControls, AssistantStreamEvent } from './assistantTypes';


export type ImperaUIDataParts = {
  status: { event: string; data: unknown; sequence: number };
  governance: { event: string; data: unknown; sequence: number };
  artifact: Record<string, unknown>;
  form: Record<string, unknown>;
};

export type ImperaUIMessage = UIMessage<
  {
    traceId?: string;
    dataClass?: string;
    turnId?: string;
    createdAtUtc?: string;
    selectedRunId?: string;
    controls?: AssistantComposerControls;
  },
  ImperaUIDataParts
>;

export interface ImperaTauriTransportAdapter {
  listen(handler: (event: AssistantStreamEvent) => void): Promise<() => void>;
  start(request: {
    assistantTurnId: string;
    sessionId: string;
    userMessage: string;
    compiledPrompt: string;
    trigger: 'submit-message' | 'regenerate-message';
  }): Promise<unknown>;
  cancel(assistantTurnId: string): Promise<unknown>;
}

export interface ImperaTauriChatTransportOptions {
  adapter: ImperaTauriTransportAdapter;
  compilePrompt(messages: ImperaUIMessage[]): Promise<string>;
  createTurnId?: () => string;
}

function defaultTurnId(): string {
  return `turn-${globalThis.crypto.randomUUID()}`;
}

function latestUserText(messages: ImperaUIMessage[]): string {
  const user = [...messages].reverse().find((message) => message.role === 'user');
  if (!user) return '';
  return user.parts
    .map((part) => (part.type === 'text' ? part.text : ''))
    .join('')
    .trim();
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null ? (value as Record<string, unknown>) : {};
}

function readText(value: unknown, ...keys: string[]): string {
  const record = asRecord(value);
  for (const key of keys) {
    if (typeof record[key] === 'string') return record[key];
  }
  return '';
}

export class ImperaTauriChatTransport implements ChatTransport<ImperaUIMessage> {
  private readonly adapter: ImperaTauriTransportAdapter;
  private readonly compilePrompt: (messages: ImperaUIMessage[]) => Promise<string>;
  private readonly createTurnId: () => string;

  constructor(options: ImperaTauriChatTransportOptions) {
    this.adapter = options.adapter;
    this.compilePrompt = options.compilePrompt;
    this.createTurnId = options.createTurnId ?? defaultTurnId;
  }

  async sendMessages(
    options: Parameters<ChatTransport<ImperaUIMessage>['sendMessages']>[0],
  ): Promise<ReadableStream<UIMessageChunk>> {
    const assistantTurnId = this.createTurnId();
    const textPartId = `${assistantTurnId}-text`;
    const assistantMessageId = `${assistantTurnId}-assistant`;
    const userMessage = latestUserText(options.messages);
    const compiledPrompt = await this.compilePrompt(options.messages);
    const adapter = this.adapter;

    return new ReadableStream<UIMessageChunk>({
      async start(controller) {
        let unlisten: (() => void) | null = null;
        let closed = false;
        let lastSequence = 0;
        let emittedText = false;

        const cleanup = () => {
          options.abortSignal?.removeEventListener('abort', onAbort);
          unlisten?.();
          unlisten = null;
        };
        const close = () => {
          if (closed) return;
          closed = true;
          cleanup();
          controller.close();
        };
        const fail = (code: string) => {
          if (closed) return;
          controller.enqueue({ type: 'error', errorText: code });
          close();
        };
        const onAbort = () => {
          if (closed) return;
          void adapter.cancel(assistantTurnId).finally(() => {
            if (!closed) controller.enqueue({ type: 'abort', reason: 'cancelled' });
            close();
          });
        };
        const onEvent = (raw: AssistantStreamEvent) => {
          if (closed) return;
          const event = normalizeAssistantStreamEvent(raw);
          if (
            !event ||
            event.assistantTurnId !== assistantTurnId ||
            event.sessionId !== options.chatId
          ) {
            return;
          }
          if (event.sequence <= lastSequence) return;
          const terminalSynthetic = event.event === 'cancelled' || event.event === 'error';
          if (!terminalSynthetic && event.sequence !== lastSequence + 1) {
            fail('ASSISTANT_EVENT_SEQUENCE_GAP');
            return;
          }
          lastSequence = event.sequence;
          if (event.event === 'token' || event.event === 'delta' || event.event === 'text_delta') {
            const delta = readText(event.data, 'text', 'token', 'delta');
            if (delta) {
              emittedText = true;
              controller.enqueue({
                type: 'data-status',
                id: event.eventId,
                data: { event: event.event, data: event.data, sequence: event.sequence },
              });
              controller.enqueue({ type: 'text-delta', id: textPartId, delta });
            }
            return;
          }
          if (event.event.startsWith('artifact_')) {
            controller.enqueue({
              type: 'data-artifact',
              id: event.eventId,
              data: { ...asRecord(event.data), event: event.event, sequence: event.sequence },
            });
            return;
          }
          if (event.event.startsWith('form_')) {
            controller.enqueue({
              type: 'data-form',
              id: event.eventId,
              data: { ...asRecord(event.data), event: event.event, sequence: event.sequence },
            });
            return;
          }
          if (event.event === 'final') {
            const finalText = readText(event.data, 'final_text', 'finalText', 'text', 'content');
            if (!emittedText && finalText) {
              controller.enqueue({ type: 'text-delta', id: textPartId, delta: finalText });
            }
            controller.enqueue({ type: 'text-end', id: textPartId });
            controller.enqueue({ type: 'finish', finishReason: 'stop' });
            close();
            return;
          }
          if (event.event === 'cancelled') {
            controller.enqueue({ type: 'abort', reason: 'cancelled' });
            close();
            return;
          }
          if (event.event === 'error') {
            fail(readText(event.data, 'code') || 'ASSISTANT_FAILED');
            return;
          }
          const governanceEvents = new Set([
            'router_decision',
            'policy_decision',
            'approval_pending',
            'tool_result',
          ]);
          controller.enqueue({
            type: governanceEvents.has(event.event) ? 'data-governance' : 'data-status',
            id: event.eventId,
            data: { event: event.event, data: event.data, sequence: event.sequence },
          });
        };

        controller.enqueue({ type: 'start', messageId: assistantMessageId });
        controller.enqueue({ type: 'text-start', id: textPartId });
        options.abortSignal?.addEventListener('abort', onAbort, { once: true });
        try {
          unlisten = await adapter.listen(onEvent);
          if (closed) {
            cleanup();
            return;
          }
          if (options.abortSignal?.aborted) {
            onAbort();
            return;
          }
          await adapter.start({
            assistantTurnId,
            sessionId: options.chatId,
            userMessage,
            compiledPrompt,
            trigger: options.trigger,
          });
        } catch {
          fail('ASSISTANT_TAURI_TRANSPORT_FAILED');
        }
      },
      async cancel() {
        await adapter.cancel(assistantTurnId);
      },
    });
  }

  async reconnectToStream(): Promise<ReadableStream<UIMessageChunk> | null> {
    return null;
  }
}
