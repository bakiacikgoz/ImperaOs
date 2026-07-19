import { useChat } from '@ai-sdk/react';
import { useCallback, useMemo, useState } from 'react';

import {
  cancelAssistantTurn,
  isBridgePreviewMode,
  listenAssistantEvents,
  startAssistantTurn,
} from '../bridge';
import {
  assistantRuntimeOptionsFromSettings,
  type AssistantRuntimeSettings,
  type PanelSettings,
} from '../settings';
import { buildAssistantPrompt } from './assistantPromptBuilder';
import { previewAssistantEvents } from './assistantFixtures';
import {
  createAssistantSession,
  createAssistantTurn,
  mapCliAssistantEvent,
  normalizeAssistantError,
} from './assistantMappers';
import {
  ImperaTauriChatTransport,
  type ImperaTauriTransportAdapter,
  type ImperaUIMessage,
} from './imperaTauriChatTransport';
import type {
  AssistantComposerControls,
  AssistantSessionState,
  AssistantStreamEvent,
  AssistantTurnStatus,
} from './assistantTypes';
import {
  useAssistantSession,
  type AssistantContextSnapshot,
  type AssistantSessionActions,
} from './useAssistantSession';

type ChatStatus = 'submitted' | 'streaming' | 'ready' | 'error';

type ApprovalOverride = {
  status?: string;
  detailLoaded?: boolean;
  detail?: unknown;
};

type RuntimeSessionOptions = {
  enabled?: boolean;
};

class PendingAssistantTurnContext {
  private runtimeSettings: AssistantRuntimeSettings | undefined;
  private controls: AssistantComposerControls | undefined;
  private previewHandler: ((event: AssistantStreamEvent) => void) | null = null;

  setOptions(runtimeSettings?: AssistantRuntimeSettings, controls?: AssistantComposerControls): void {
    this.runtimeSettings = runtimeSettings;
    this.controls = controls;
  }

  getRuntimeSettings(): AssistantRuntimeSettings | undefined {
    return this.runtimeSettings;
  }

  getControls(): AssistantComposerControls | undefined {
    return this.controls;
  }

  attachPreviewHandler(handler: (event: AssistantStreamEvent) => void): void {
    this.previewHandler = handler;
  }

  detachPreviewHandler(handler: (event: AssistantStreamEvent) => void): void {
    if (this.previewHandler === handler) this.previewHandler = null;
  }

  emitPreview(event: AssistantStreamEvent): void {
    this.previewHandler?.(event);
  }
}

function nextId(prefix: string): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return `${prefix}-${crypto.randomUUID()}`;
  }
  return `${prefix}-${Date.now()}-${Math.floor(Math.random() * 10_000)}`;
}

function textFromMessage(message: ImperaUIMessage): string {
  return message.parts
    .map((part) => (part.type === 'text' ? part.text : ''))
    .join('')
    .trim();
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null ? (value as Record<string, unknown>) : {};
}

function eventFromDataPart(
  part: ImperaUIMessage['parts'][number],
  turnId: string,
  sessionId: string,
): AssistantStreamEvent | null {
  if (!part.type.startsWith('data-') || !('data' in part)) {
    return null;
  }
  const payload = asRecord(part.data);
  const event = typeof payload.event === 'string' ? payload.event : '';
  const sequence = typeof payload.sequence === 'number' ? payload.sequence : 0;
  if (!event || sequence <= 0) {
    return null;
  }
  const nestedData = payload.data;
  const data = nestedData === undefined
    ? Object.fromEntries(Object.entries(payload).filter(([key]) => !['event', 'sequence'].includes(key)))
    : nestedData;
  return {
    contractVersion: '3.0',
    eventId: 'id' in part && typeof part.id === 'string' ? part.id : `${turnId}-${sequence}`,
    assistantTurnId: turnId,
    sessionId,
    event: event as AssistantStreamEvent['event'],
    sequence,
    timestampUtc: new Date().toISOString(),
    data,
  };
}

function statusFromChat(status: ChatStatus, hasTurns: boolean): AssistantTurnStatus {
  if (!hasTurns) return 'idle';
  if (status === 'submitted') return 'starting';
  if (status === 'streaming') return 'streaming';
  if (status === 'error') return 'failed';
  return 'completed';
}

export function projectAiSdkChatToLegacySession(input: {
  id: string;
  messages: ImperaUIMessage[];
  status: ChatStatus;
  error?: Error;
}): AssistantSessionState {
  let session = createAssistantSession(input.id);
  const assistantMessages = new Map<number, ImperaUIMessage>();

  for (const message of input.messages) {
    if (message.role === 'user') {
      const turnId = message.metadata?.turnId ?? `assistant-turn-${message.id}`;
      const turn = createAssistantTurn({
        id: turnId,
        sessionId: input.id,
        userMessage: textFromMessage(message),
        createdAtUtc: message.metadata?.createdAtUtc,
        controls: message.metadata?.controls,
      });
      session = {
        ...session,
        turns: [...session.turns, turn],
        selectedRunIds: message.metadata?.selectedRunId
          ? Array.from(new Set([...session.selectedRunIds, message.metadata.selectedRunId]))
          : session.selectedRunIds,
      };
      continue;
    }
    if (message.role === 'assistant' && session.turns.length > 0) {
      assistantMessages.set(session.turns.length - 1, message);
    }
  }

  session.turns.forEach((turn, index) => {
    const message = assistantMessages.get(index);
    if (!message) return;
    turn.assistantMessage.id = message.id;
    for (const part of message.parts) {
      const event = eventFromDataPart(part, turn.id, session.sessionId);
      if (event) session = mapCliAssistantEvent(event, session);
    }
    const current = session.turns[index];
    current.assistantMessage.text = textFromMessage(message);
  });

  const status = statusFromChat(input.status, session.turns.length > 0);
  const activeIndex = session.turns.length - 1;
  session.turns = session.turns.map((turn, index) => ({
    ...turn,
    status: index < activeIndex || status === 'completed' ? 'completed' : status,
    completedAtUtc:
      index < activeIndex || status === 'completed'
        ? turn.completedAtUtc ?? new Date().toISOString()
        : turn.completedAtUtc,
  }));
  const error = input.error ? normalizeAssistantError(input.error) : session.error;
  return {
    ...session,
    activeTurnId: status === 'starting' || status === 'streaming' ? session.turns.at(-1)?.id ?? null : null,
    status,
    error,
  };
}

function applyOverlays(
  state: AssistantSessionState,
  approvals: Record<string, ApprovalOverride>,
  systemMessages: Array<{ turnId: string; message: string; timestampUtc: string }>,
  manualEvents: AssistantStreamEvent[],
): AssistantSessionState {
  let next = manualEvents.reduce((current, event) => mapCliAssistantEvent(event, current), state);
  next = {
    ...next,
    turns: next.turns.map((turn) => {
      const approval = turn.assistantMessage.approval;
      const override = approval ? approvals[approval.approvalId] : undefined;
      const notes = systemMessages.filter((item) => item.turnId === turn.id);
      return {
        ...turn,
        assistantMessage: {
          ...turn.assistantMessage,
          approval: approval && override ? { ...approval, ...override } : approval,
          parts: turn.assistantMessage.parts.map((part) => {
            if (part.type !== 'artifact-proposal') return part;
            const proposalOverride = approvals[part.approvalId]?.status;
            if (proposalOverride === 'executed') return { ...part, status: 'applied' as const };
            if (proposalOverride === 'approved' || proposalOverride === 'rejected' || proposalOverride === 'failed') {
              return { ...part, status: proposalOverride };
            }
            return part;
          }),
          timeline: [
            ...turn.assistantMessage.timeline,
            ...notes.map((item, index) => ({
              id: `${turn.id}-system-${index}-${item.timestampUtc}`,
              tone: 'info' as const,
              title: 'Operator update',
              subtitle: item.message,
              timestampUtc: item.timestampUtc,
            })),
          ],
        },
      };
    }),
  };
  const resolvedPending = next.pendingApprovalId
    ? approvals[next.pendingApprovalId]?.status
    : undefined;
  if (resolvedPending && resolvedPending !== 'pending') {
    next = { ...next, pendingApprovalId: null, status: 'completed', activeTurnId: null };
  }
  return next;
}

export function isAiSdkAssistantRuntimeEnabled(value: string | undefined): boolean {
  return value === '1' || value?.toLowerCase() === 'true';
}

export function useAssistantRuntimeSession(
  settings: PanelSettings,
  getContext: () => AssistantContextSnapshot,
  options: RuntimeSessionOptions = {},
): { state: AssistantSessionState; actions: AssistantSessionActions } {
  const enabled = options.enabled ?? isAiSdkAssistantRuntimeEnabled(import.meta.env.VITE_ASSISTANT_AI_SDK_RUNTIME);
  const legacy = useAssistantSession(settings, getContext, { enabled: !enabled });
  const [chatId, setChatId] = useState(() => createAssistantSession().sessionId);
  const [approvalOverrides, setApprovalOverrides] = useState<Record<string, ApprovalOverride>>({});
  const [systemMessages, setSystemMessages] = useState<
    Array<{ turnId: string; message: string; timestampUtc: string }>
  >([]);
  const [manualEvents, setManualEvents] = useState<AssistantStreamEvent[]>([]);
  const [pendingTurn] = useState(() => new PendingAssistantTurnContext());

  const listen = useCallback<ImperaTauriTransportAdapter['listen']>(async (handler) => {
    pendingTurn.attachPreviewHandler(handler);
    const unlisten = isBridgePreviewMode()
      ? () => undefined
      : await listenAssistantEvents(handler);
    return () => {
      pendingTurn.detachPreviewHandler(handler);
      unlisten();
    };
  }, [pendingTurn]);

  const start = useCallback<ImperaTauriTransportAdapter['start']>(
    async (request) => {
      const response = await startAssistantTurn(settings, {
        assistantTurnId: request.assistantTurnId,
        sessionId: request.sessionId,
        userMessage: request.userMessage,
        compiledPrompt: request.compiledPrompt,
        profile: settings.profile,
        ...assistantRuntimeOptionsFromSettings({
          ...settings,
          ...pendingTurn.getRuntimeSettings(),
        }),
      });
      if (isBridgePreviewMode()) {
        previewAssistantEvents(request.assistantTurnId, request.sessionId).forEach((event) =>
          pendingTurn.emitPreview(event),
        );
      }
      return response;
    },
    [pendingTurn, settings],
  );

  const cancelNative = useCallback<ImperaTauriTransportAdapter['cancel']>(
    (turnId) => cancelAssistantTurn(settings, turnId),
    [settings],
  );

  const compilePrompt = useCallback(
    async (messages: ImperaUIMessage[]) => {
      const context = getContext();
      const projected = projectAiSdkChatToLegacySession({
        id: chatId,
        messages,
        status: 'submitted',
      });
      const userMessage = [...messages].reverse().find((message) => message.role === 'user');
      return buildAssistantPrompt({
        userMessage: userMessage ? textFromMessage(userMessage) : '',
        session: projected,
        selectedRunStatus: context.selectedRunStatus,
        selectedRunEvents: context.selectedRunEvents,
        selectedArtifacts: context.selectedArtifacts,
        artifactContextRequest: context.artifactContextRequest,
        pendingApproval: context.pendingApproval,
        systemHealth: context.systemHealth,
        controls: pendingTurn.getControls(),
      }).compiledPrompt;
    },
    [chatId, getContext, pendingTurn],
  );

  const transport = useMemo(
    () =>
      new ImperaTauriChatTransport({
        adapter: { listen, start, cancel: cancelNative },
        compilePrompt,
      }),
    [cancelNative, compilePrompt, listen, start],
  );

  const chat = useChat<ImperaUIMessage>({ id: chatId, transport, experimental_throttle: 25 });
  const projected = useMemo(
    () =>
      applyOverlays(
        projectAiSdkChatToLegacySession({
          id: chat.id,
          messages: chat.messages,
          status: chat.status,
          error: chat.error,
        }),
        approvalOverrides,
        systemMessages,
        manualEvents,
      ),
    [approvalOverrides, chat.error, chat.id, chat.messages, chat.status, manualEvents, systemMessages],
  );

  const send = useCallback(
    async (
      message: string,
      runtimeSettings?: AssistantRuntimeSettings,
      controls?: AssistantComposerControls,
    ) => {
      const text = message.trim();
      if (!text || chat.status === 'submitted' || chat.status === 'streaming') return;
      pendingTurn.setOptions(runtimeSettings, controls);
      const context = getContext();
      await chat.sendMessage({
        text,
        metadata: {
          turnId: nextId('assistant-turn'),
          createdAtUtc: new Date().toISOString(),
          selectedRunId: context.selectedRunId || undefined,
          controls,
        },
      });
    },
    [chat, getContext, pendingTurn],
  );

  const newChat = useCallback(() => {
    setApprovalOverrides({});
    setSystemMessages([]);
    setManualEvents([]);
    setChatId(createAssistantSession().sessionId);
  }, []);

  const regenerate = useCallback(
    async (turnId: string, runtimeSettings?: AssistantRuntimeSettings) => {
      const turn = projected.turns.find((item) => item.id === turnId);
      if (!turn) return;
      pendingTurn.setOptions(runtimeSettings, turn.composerControls ?? undefined);
      await chat.regenerate({ messageId: turn.assistantMessage.id });
    },
    [chat, pendingTurn, projected.turns],
  );

  const cancel = useCallback(async () => {
    if (chat.status === 'submitted' || chat.status === 'streaming') await chat.stop();
  }, [chat]);

  const applyEvent = useCallback((event: AssistantStreamEvent) => {
    setManualEvents((previous) => [...previous, event].slice(-100));
  }, []);

  const markApprovalDetailLoaded = useCallback((approvalId: string, detail: unknown) => {
    setApprovalOverrides((previous) => ({
      ...previous,
      [approvalId]: { ...previous[approvalId], detailLoaded: true, detail },
    }));
  }, []);

  const updateApprovalStatus = useCallback((approvalId: string, status: string) => {
    setApprovalOverrides((previous) => ({
      ...previous,
      [approvalId]: { ...previous[approvalId], status },
    }));
  }, []);

  const appendSystemMessage = useCallback(
    (message: string) => {
      const turnId = projected.turns.at(-1)?.id;
      if (!turnId) return;
      setSystemMessages((previous) => [
        ...previous,
        { turnId, message, timestampUtc: new Date().toISOString() },
      ]);
    },
    [projected.turns],
  );

  const actions = useMemo<AssistantSessionActions>(
    () => ({
      send,
      newChat,
      regenerate,
      cancel,
      applyEvent,
      markApprovalDetailLoaded,
      updateApprovalStatus,
      appendSystemMessage,
    }),
    [
      appendSystemMessage,
      applyEvent,
      cancel,
      markApprovalDetailLoaded,
      newChat,
      regenerate,
      send,
      updateApprovalStatus,
    ],
  );

  return enabled ? { state: projected, actions } : legacy;
}
