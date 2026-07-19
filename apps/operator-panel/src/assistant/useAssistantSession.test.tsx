import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { DEFAULT_SETTINGS } from '../settings';
import { useAssistantSession, type AssistantContextSnapshot } from './useAssistantSession';

const bridgeMocks = vi.hoisted(() => ({
  startAssistantTurn: vi.fn(),
  cancelAssistantTurn: vi.fn(),
  listenAssistantEvents: vi.fn(),
  isBridgePreviewMode: vi.fn(),
}));

vi.mock('../bridge', () => ({
  startAssistantTurn: bridgeMocks.startAssistantTurn,
  cancelAssistantTurn: bridgeMocks.cancelAssistantTurn,
  listenAssistantEvents: bridgeMocks.listenAssistantEvents,
  isBridgePreviewMode: bridgeMocks.isBridgePreviewMode,
}));

const emptyContext: AssistantContextSnapshot = {
  selectedRunId: '',
  selectedRunStatus: null,
  selectedRunEvents: [],
  selectedArtifacts: {},
  pendingApproval: null,
  systemHealth: null,
};

describe('useAssistantSession runtime metadata', () => {
  beforeEach(() => {
    bridgeMocks.startAssistantTurn.mockResolvedValue({
      contractVersion: '3.0',
      assistantTurnId: 'turn-test',
      sessionId: 'session-test',
      processId: null,
      status: 'started',
    });
    bridgeMocks.listenAssistantEvents.mockResolvedValue(() => undefined);
    bridgeMocks.cancelAssistantTurn.mockResolvedValue({
      contractVersion: '3.0',
      assistantTurnId: 'turn-test',
      sessionId: 'session-test',
      processId: null,
      status: 'cancelled',
    });
    bridgeMocks.isBridgePreviewMode.mockReturnValue(false);
    vi.clearAllMocks();
  });

  it('passes selected provider and model settings into startAssistantTurn', async () => {
    const settings = {
      ...DEFAULT_SETTINGS,
      assistantProvider: 'ollama',
      assistantFallbackProvider: 'transformers',
      assistantModel: 'qwen3.5:4b',
      assistantHfModelId: '',
    };
    const { result } = renderHook(() => useAssistantSession(settings, () => emptyContext));

    await act(async () => {
      await result.current.actions.send('Summarize the active run.');
    });

    await waitFor(() => expect(bridgeMocks.startAssistantTurn).toHaveBeenCalledTimes(1));
    expect(bridgeMocks.startAssistantTurn).toHaveBeenCalledWith(
      expect.objectContaining(settings),
      expect.objectContaining({
        profile: 'balanced',
        provider: 'ollama',
        fallbackProvider: 'transformers',
        model: 'qwen3.5:4b',
        hfModelId: undefined,
      }),
    );
  });

  it('passes undefined runtime overrides when profile defaults are selected', async () => {
    const { result } = renderHook(() => useAssistantSession({ ...DEFAULT_SETTINGS }, () => emptyContext));

    await act(async () => {
      await result.current.actions.send('Use profile defaults.');
    });

    await waitFor(() => expect(bridgeMocks.startAssistantTurn).toHaveBeenCalledTimes(1));
    expect(bridgeMocks.startAssistantTurn).toHaveBeenCalledWith(
      expect.any(Object),
      expect.objectContaining({
        profile: 'balanced',
        provider: undefined,
        fallbackProvider: undefined,
        model: undefined,
        hfModelId: undefined,
      }),
    );
  });

  it('applies preview assistant events through the reducer and reaches a final state', async () => {
    bridgeMocks.isBridgePreviewMode.mockReturnValue(true);
    const { result } = renderHook(() => useAssistantSession({ ...DEFAULT_SETTINGS }, () => emptyContext));

    await act(async () => {
      await result.current.actions.send('Preview assistant response.');
    });

    await waitFor(() => expect(result.current.state.status).toBe('completed'));
    expect(result.current.state.turns[0]?.assistantMessage.text).toContain('approval gate');
    expect(result.current.state.turns[0]?.completedAtUtc).toBeTruthy();
  });

  it('cancels the active assistant turn without surfacing an error', async () => {
    const { result } = renderHook(() => useAssistantSession({ ...DEFAULT_SETTINGS }, () => emptyContext));

    await act(async () => {
      await result.current.actions.send('Start a long response.');
    });

    await waitFor(() => expect(result.current.state.status).toBe('starting'));

    await act(async () => {
      await result.current.actions.cancel();
    });

    await waitFor(() => expect(result.current.state.status).toBe('cancelled'));
    expect(bridgeMocks.cancelAssistantTurn).toHaveBeenCalledWith(expect.any(Object), expect.stringMatching(/^assistant-turn-/));
    expect(result.current.state.error).toBeNull();
  });

  it('synchronizes a decided approval into the canonical assistant session', async () => {
    const { result } = renderHook(() => useAssistantSession({ ...DEFAULT_SETTINGS }, () => emptyContext));

    await act(async () => {
      await result.current.actions.send('Propose a governed action.');
    });
    const turn = result.current.state.turns[0];
    act(() => {
      result.current.actions.applyEvent({
        contractVersion: '3.0',
        assistantTurnId: turn.id,
        sessionId: result.current.state.sessionId,
        event: 'approval_pending',
        sequence: 1,
        timestampUtc: '2026-07-16T07:00:00Z',
        data: { approval_id: 'approval-sync', title: 'Approval required' },
      });
    });
    await waitFor(() => expect(result.current.state.pendingApprovalId).toBe('approval-sync'));

    act(() => result.current.actions.updateApprovalStatus('approval-sync', 'approved'));

    expect(result.current.state.pendingApprovalId).toBeNull();
    expect(result.current.state.status).toBe('completed');
    expect(result.current.state.turns[0].status).toBe('completed');
    expect(result.current.state.turns[0].assistantMessage.approval?.status).toBe('approved');
  });

  it('synchronizes proposal approval and execution without a renderer grant boolean', async () => {
    const { result } = renderHook(() => useAssistantSession({ ...DEFAULT_SETTINGS }, () => emptyContext));

    await act(async () => {
      await result.current.actions.send('Propose an artifact patch.');
    });
    const turn = result.current.state.turns[0];
    act(() => {
      result.current.actions.applyEvent({
        contractVersion: '3.0',
        eventId: 'event-proposal',
        assistantTurnId: turn.id,
        sessionId: result.current.state.sessionId,
        event: 'artifact_patch_proposed',
        sequence: 1,
        timestampUtc: '2026-07-16T07:00:00Z',
        traceId: 'trace-proposal',
        dataClass: 'internal',
        data: {
          artifactId: 'artifact-1',
          proposalId: 'proposal-1',
          approvalId: 'approval-proposal',
          actionHash: 'a'.repeat(64),
          baseRevisionNumber: 1,
          kind: 'document',
        },
      });
    });
    await waitFor(() => expect(result.current.state.turns[0].assistantMessage.parts).toHaveLength(2));

    act(() => result.current.actions.updateApprovalStatus('approval-proposal', 'approved'));
    expect(result.current.state.turns[0].assistantMessage.parts[1]).toEqual(
      expect.objectContaining({ type: 'artifact-proposal', status: 'approved' }),
    );

    act(() => result.current.actions.updateApprovalStatus('approval-proposal', 'executed'));
    expect(result.current.state.turns[0].assistantMessage.parts[1]).toEqual(
      expect.objectContaining({ type: 'artifact-proposal', status: 'applied' }),
    );
  });
});
