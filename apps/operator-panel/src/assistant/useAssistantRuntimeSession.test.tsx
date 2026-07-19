import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { DEFAULT_SETTINGS } from '../settings';
import type { AssistantStreamEvent } from './assistantTypes';
import {
  isAiSdkAssistantRuntimeEnabled,
  useAssistantRuntimeSession,
} from './useAssistantRuntimeSession';

const bridgeMocks = vi.hoisted(() => ({
  startAssistantTurn: vi.fn(),
  cancelAssistantTurn: vi.fn(),
  listenAssistantEvents: vi.fn(),
  isBridgePreviewMode: vi.fn(),
}));

const legacySession = vi.hoisted(() => ({
  state: {
    sessionId: 'legacy-session',
    turns: [],
    activeTurnId: null,
    status: 'idle' as const,
    selectedRunIds: [],
    referencedArtifacts: [],
    pendingApprovalId: null,
    error: null,
  },
  actions: {
    send: vi.fn(),
    newChat: vi.fn(),
    regenerate: vi.fn(),
    cancel: vi.fn(),
    applyEvent: vi.fn(),
    markApprovalDetailLoaded: vi.fn(),
    updateApprovalStatus: vi.fn(),
    appendSystemMessage: vi.fn(),
  },
}));

vi.mock('../bridge', () => ({
  startAssistantTurn: bridgeMocks.startAssistantTurn,
  cancelAssistantTurn: bridgeMocks.cancelAssistantTurn,
  listenAssistantEvents: bridgeMocks.listenAssistantEvents,
  isBridgePreviewMode: bridgeMocks.isBridgePreviewMode,
}));

vi.mock('./useAssistantSession', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./useAssistantSession')>();
  return {
    ...actual,
    useAssistantSession: vi.fn(() => legacySession),
  };
});

const emptyContext = {
  selectedRunId: '',
  selectedRunStatus: null,
  selectedRunEvents: [],
  selectedArtifacts: {},
  pendingApproval: null,
  systemHealth: null,
};

function event(
  turnId: string,
  sessionId: string,
  sequence: number,
  type: AssistantStreamEvent['event'],
  data: unknown,
): AssistantStreamEvent {
  return {
    contractVersion: '3.0',
    eventId: `event-${sequence}`,
    assistantTurnId: turnId,
    sessionId,
    event: type,
    sequence,
    timestampUtc: `2026-07-16T09:00:0${sequence}Z`,
    traceId: 'trace-runtime-cutover',
    dataClass: 'internal',
    data,
  };
}

describe('AI SDK assistant runtime cutover', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    bridgeMocks.isBridgePreviewMode.mockReturnValue(false);
    bridgeMocks.cancelAssistantTurn.mockResolvedValue(undefined);
    bridgeMocks.startAssistantTurn.mockResolvedValue({ status: 'started' });
  });

  it('enables only explicit rollback-safe feature flag values', () => {
    expect(isAiSdkAssistantRuntimeEnabled(undefined)).toBe(false);
    expect(isAiSdkAssistantRuntimeEnabled('0')).toBe(false);
    expect(isAiSdkAssistantRuntimeEnabled('false')).toBe(false);
    expect(isAiSdkAssistantRuntimeEnabled('1')).toBe(true);
    expect(isAiSdkAssistantRuntimeEnabled('TRUE')).toBe(true);
  });

  it('returns the legacy session unchanged while the feature flag is disabled', () => {
    const { result } = renderHook(() =>
      useAssistantRuntimeSession(DEFAULT_SETTINGS, () => emptyContext, { enabled: false }),
    );

    expect(result.current).toBe(legacySession);
    expect(bridgeMocks.listenAssistantEvents).not.toHaveBeenCalled();
  });

  it('uses the Tauri transport and projects AI SDK messages into the legacy view model', async () => {
    let handler!: (value: AssistantStreamEvent) => void;
    const unlisten = vi.fn();
    bridgeMocks.listenAssistantEvents.mockImplementation(async (next) => {
      handler = next;
      return unlisten;
    });
    const { result } = renderHook(() =>
      useAssistantRuntimeSession(DEFAULT_SETTINGS, () => emptyContext, { enabled: true }),
    );

    let sendPromise!: Promise<void>;
    act(() => {
      sendPromise = result.current.actions.send('Create a governed document.');
    });
    await waitFor(() => expect(bridgeMocks.startAssistantTurn).toHaveBeenCalledTimes(1));
    const options = bridgeMocks.startAssistantTurn.mock.calls[0][1];

    act(() => {
      handler(event(options.assistantTurnId, options.sessionId, 1, 'text_delta', { text: 'Draft ready.' }));
      handler(
        event(options.assistantTurnId, options.sessionId, 2, 'artifact_committed', {
          artifactId: 'artifact-1',
          revisionId: 'revision-1',
          kind: 'document',
        }),
      );
      handler(event(options.assistantTurnId, options.sessionId, 3, 'final', { final_text: 'Draft ready.' }));
    });

    await act(async () => sendPromise);

    await waitFor(() => expect(result.current.state.status).toBe('completed'));
    expect(result.current.state.turns).toHaveLength(1);
    expect(result.current.state.turns[0].userMessage.text).toBe('Create a governed document.');
    expect(result.current.state.turns[0].assistantMessage.text).toBe('Draft ready.');
    expect(result.current.state.referencedArtifacts[0]).toMatchObject({
      artifactId: 'artifact-1',
      revisionId: 'revision-1',
      kind: 'document',
    });
    expect(unlisten).toHaveBeenCalledTimes(1);
  });
});
