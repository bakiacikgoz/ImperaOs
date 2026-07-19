import { describe, expect, it, vi } from 'vitest';

import type { AssistantStreamEvent } from './assistantTypes';
import { ImperaTauriChatTransport, type ImperaUIMessage } from './imperaTauriChatTransport';


function userMessage(): ImperaUIMessage {
  return { id: 'user-1', role: 'user', parts: [{ type: 'text', text: 'Create a document' }] };
}

async function readAll(stream: ReadableStream<unknown>): Promise<unknown[]> {
  const reader = stream.getReader();
  const chunks: unknown[] = [];
  for (;;) {
    const { value, done } = await reader.read();
    if (done) return chunks;
    chunks.push(value);
  }
}

function event(sequence: number, type: AssistantStreamEvent['event'], data: unknown): AssistantStreamEvent {
  return {
    contractVersion: '3.0',
    eventId: `event-${sequence}`,
    assistantTurnId: 'turn-1',
    sessionId: 'chat-1',
    event: type,
    sequence,
    timestampUtc: `2026-07-16T08:00:0${sequence}Z`,
    traceId: 'trace-1',
    dataClass: 'internal',
    data,
  };
}

describe('Impera Tauri AI SDK transport', () => {
  it('streams text and governed data parts without HTTP and cleans up on final', async () => {
    let handler!: (value: AssistantStreamEvent) => void;
    const unlisten = vi.fn();
    const adapter = {
      listen: vi.fn(async (next) => {
        handler = next;
        return unlisten;
      }),
      start: vi.fn(async () => ({ assistantTurnId: 'turn-1' })),
      cancel: vi.fn(async () => undefined),
    };
    const transport = new ImperaTauriChatTransport({
      adapter,
      createTurnId: () => 'turn-1',
      compilePrompt: async () => 'governed prompt',
    });

    const stream = await transport.sendMessages({
      trigger: 'submit-message',
      chatId: 'chat-1',
      messageId: undefined,
      messages: [userMessage()],
      abortSignal: undefined,
    });
    const result = readAll(stream);
    await vi.waitFor(() => expect(adapter.start).toHaveBeenCalledTimes(1));
    handler(event(1, 'text_delta', { text: 'Draft' }));
    handler(
      event(2, 'artifact_committed', {
        artifactId: 'artifact-1',
        revisionId: 'revision-1',
        kind: 'document',
      }),
    );
    handler(event(3, 'final', { final_text: 'Draft' }));

    expect(await result).toEqual([
      { type: 'start', messageId: 'turn-1-assistant' },
      { type: 'text-start', id: 'turn-1-text' },
      {
        type: 'data-status',
        id: 'event-1',
        data: { event: 'text_delta', data: { text: 'Draft' }, sequence: 1 },
      },
      { type: 'text-delta', id: 'turn-1-text', delta: 'Draft' },
      {
        type: 'data-artifact',
        id: 'event-2',
        data: expect.objectContaining({ artifactId: 'artifact-1', revisionId: 'revision-1' }),
      },
      { type: 'text-end', id: 'turn-1-text' },
      { type: 'finish', finishReason: 'stop' },
    ]);
    expect(unlisten).toHaveBeenCalledTimes(1);
    expect(adapter.cancel).not.toHaveBeenCalled();
  });

  it('fails closed on a sequence gap and removes the listener', async () => {
    let handler!: (value: AssistantStreamEvent) => void;
    const unlisten = vi.fn();
    const adapter = {
      listen: vi.fn(async (next) => {
        handler = next;
        return unlisten;
      }),
      start: vi.fn(async () => ({ assistantTurnId: 'turn-1' })),
      cancel: vi.fn(async () => undefined),
    };
    const transport = new ImperaTauriChatTransport({
      adapter,
      createTurnId: () => 'turn-1',
      compilePrompt: async () => 'governed prompt',
    });
    const stream = await transport.sendMessages({
      trigger: 'submit-message',
      chatId: 'chat-1',
      messageId: undefined,
      messages: [userMessage()],
      abortSignal: undefined,
    });
    const result = readAll(stream);
    await vi.waitFor(() => expect(adapter.start).toHaveBeenCalledTimes(1));
    handler(event(2, 'text_delta', { text: 'out of order' }));

    expect(await result).toContainEqual({
      type: 'error',
      errorText: 'ASSISTANT_EVENT_SEQUENCE_GAP',
    });
    expect(unlisten).toHaveBeenCalledTimes(1);
  });

  it('propagates AbortSignal to native cancellation and closes the stream', async () => {
    const adapter = {
      listen: vi.fn(async () => vi.fn()),
      start: vi.fn(async () => ({ assistantTurnId: 'turn-1' })),
      cancel: vi.fn(async () => undefined),
    };
    const controller = new AbortController();
    const transport = new ImperaTauriChatTransport({
      adapter,
      createTurnId: () => 'turn-1',
      compilePrompt: async () => 'governed prompt',
    });
    const stream = await transport.sendMessages({
      trigger: 'submit-message',
      chatId: 'chat-1',
      messageId: undefined,
      messages: [userMessage()],
      abortSignal: controller.signal,
    });
    const result = readAll(stream);
    await vi.waitFor(() => expect(adapter.start).toHaveBeenCalledTimes(1));
    controller.abort();

    expect(await result).toContainEqual({ type: 'abort', reason: 'cancelled' });
    expect(adapter.cancel).toHaveBeenCalledWith('turn-1');
  });
});
