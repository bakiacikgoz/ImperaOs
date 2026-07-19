import type {
  AssistantApprovalSummary,
  AssistantComposerControls,
  AssistantSessionState,
  AssistantStreamEvent,
  AssistantStreamEventType,
  AssistantTimelineItem,
  AssistantTurn,
  AssistantUiError,
} from './assistantTypes';

type RecordValue = Record<string, unknown>;
const OPERATOR_PANEL_CONTRACT_VERSION = '3.0';

function asRecord(value: unknown): RecordValue {
  return typeof value === 'object' && value !== null ? (value as RecordValue) : {};
}

function unwrapTraceData(value: unknown): RecordValue {
  const outer = asRecord(value);
  if (typeof outer.stage !== 'string' || typeof outer.data !== 'object' || outer.data === null) {
    return outer;
  }
  return { ...outer, ...asRecord(outer.data) };
}

function readString(source: RecordValue, key: string, fallback = ''): string {
  const value = source[key];
  return typeof value === 'string' ? value : fallback;
}

function readArray(source: RecordValue, key: string): unknown[] {
  const value = source[key];
  return Array.isArray(value) ? value : [];
}

function readPositiveInt(source: RecordValue, key: string): number | null {
  const value = source[key];
  return typeof value === 'number' && Number.isInteger(value) && value >= 1 ? value : null;
}

function readProposalStatus(value: unknown): 'pending' | 'approved' | 'rejected' | 'applied' | 'failed' {
  return value === 'approved' || value === 'rejected' || value === 'applied' || value === 'failed' ? value : 'pending';
}

function readRisk(value: unknown): 'low' | 'medium' | 'high' {
  return value === 'high' || value === 'low' || value === 'medium' ? value : 'medium';
}

function nowUtc(): string {
  return new Date().toISOString();
}

function nextId(prefix: string): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return `${prefix}-${crypto.randomUUID()}`;
  }
  return `${prefix}-${Date.now()}-${Math.floor(Math.random() * 10000)}`;
}

export function createAssistantSession(sessionId = nextId('assistant-session')): AssistantSessionState {
  return {
    sessionId,
    turns: [],
    activeTurnId: null,
    status: 'idle',
    selectedRunIds: [],
    referencedArtifacts: [],
    pendingApprovalId: null,
    error: null,
  };
}

export function createAssistantTurn(input: {
  id?: string;
  sessionId: string;
  userMessage: string;
  createdAtUtc?: string;
  controls?: AssistantComposerControls;
}): AssistantTurn {
  const createdAtUtc = input.createdAtUtc ?? nowUtc();
  const id = input.id ?? nextId('assistant-turn');
  return {
    id,
    startedAtUtc: createdAtUtc,
    completedAtUtc: null,
    composerControls: input.controls ?? null,
    status: 'starting',
    eventSequence: 0,
    userMessage: {
      id: `${id}-user`,
      text: input.userMessage,
      createdAtUtc,
    },
    assistantMessage: {
      id: `${id}-assistant`,
      text: '',
      findings: [],
      timeline: [
        {
          id: `${id}-starting`,
          tone: 'info',
          title: 'Starting',
          subtitle: 'Starting assistant turn',
          timestampUtc: createdAtUtc,
        },
      ],
      proposedAction: null,
      approval: null,
      referencedRuns: [],
      referencedArtifacts: [],
      parts: [],
      metrics: null,
      warning: null,
      error: null,
    },
  };
}

export function startAssistantTurnLocally(
  previous: AssistantSessionState,
  turn: AssistantTurn,
): AssistantSessionState {
  return {
    ...previous,
    turns: [...previous.turns, turn].slice(-100),
    activeTurnId: turn.id,
    status: 'starting',
    error: null,
  };
}

function appendTimeline(turn: AssistantTurn, event: AssistantStreamEvent, item: Omit<AssistantTimelineItem, 'id'>) {
  turn.assistantMessage.timeline = [
    ...turn.assistantMessage.timeline,
    {
      id: `${event.assistantTurnId}-${event.sequence}-${event.event}`,
      ...item,
    },
  ];
}

function normalizeEventName(value: unknown): AssistantStreamEventType | null {
  const raw = typeof value === 'string' ? value : '';
  const allowed: AssistantStreamEventType[] = [
    'status',
    'token',
    'delta',
    'text_delta',
    'router_decision',
    'policy_decision',
    'approval_pending',
    'expert_start',
    'expert_end',
    'artifact_proposed',
    'artifact_committed',
    'artifact_patch_proposed',
    'artifact_patch_applied',
    'form_requested',
    'form_submitted',
    'tool_result',
    'audit_artifact',
    'final',
    'warning',
    'error',
    'cancelled',
  ];
  return allowed.includes(raw as AssistantStreamEventType) ? (raw as AssistantStreamEventType) : null;
}

export function normalizeAssistantStreamEvent(value: unknown): AssistantStreamEvent | null {
  const record = asRecord(value);
  const contractVersion = readString(record, 'contractVersion');
  if (contractVersion !== OPERATOR_PANEL_CONTRACT_VERSION) {
    return null;
  }
  const event = normalizeEventName(record.event);
  if (event === null) return null;
  return {
    contractVersion,
    eventId: readString(record, 'eventId') || undefined,
    assistantTurnId: readString(record, 'assistantTurnId'),
    sessionId: readString(record, 'sessionId'),
    event,
    sequence: typeof record.sequence === 'number' ? record.sequence : 0,
    timestampUtc: readString(record, 'timestampUtc', nowUtc()),
    traceId: readString(record, 'traceId') || undefined,
    dataClass:
      record.dataClass === 'public' ||
      record.dataClass === 'internal' ||
      record.dataClass === 'confidential' ||
      record.dataClass === 'regulated'
        ? record.dataClass
        : undefined,
    data: record.data ?? {},
  };
}

export function extractApprovalIdFromEvent(event: AssistantStreamEvent): string | null {
  const data = unwrapTraceData(event.data);
  const approvalId =
    readString(data, 'approval_id') ||
    readString(data, 'approvalId') ||
    readString(asRecord(data.ticket), 'approval_id') ||
    readString(asRecord(data.ticket), 'approvalId');
  return approvalId || null;
}

export function mapCliAssistantEvent(
  rawEvent: unknown,
  previous: AssistantSessionState,
): AssistantSessionState {
  const event = normalizeAssistantStreamEvent(rawEvent);
  if (event === null) {
    return previous;
  }
  const activeTurnId = previous.activeTurnId ?? event.assistantTurnId;
  const turnIndex = previous.turns.findIndex((item) => item.id === activeTurnId || item.id === event.assistantTurnId);
  if (turnIndex < 0) {
    return previous;
  }

  const turns = previous.turns.map((item) => ({
    ...item,
    userMessage: { ...item.userMessage },
    assistantMessage: {
      ...item.assistantMessage,
      findings: [...item.assistantMessage.findings],
      timeline: [...item.assistantMessage.timeline],
      referencedRuns: [...item.assistantMessage.referencedRuns],
      referencedArtifacts: [...item.assistantMessage.referencedArtifacts],
      parts: [...item.assistantMessage.parts],
    },
  }));
  const turn = turns[turnIndex];
  if (event.sequence <= turn.eventSequence) {
    return previous;
  }
  if (event.event !== 'cancelled' && turn.eventSequence > 0 && event.sequence > turn.eventSequence + 1) {
    turn.assistantMessage.warning = 'Assistant event sequence gap detected.';
    return { ...previous, turns, error: null };
  }

  const data = unwrapTraceData(event.data);
  turn.eventSequence = event.sequence;

  switch (event.event) {
    case 'status': {
      turn.status = 'streaming';
      appendTimeline(turn, event, {
        tone: 'info',
        title: readString(data, 'phase', 'Status'),
        subtitle: readString(data, 'message', readString(data, 'status', 'Assistant is working')),
        timestampUtc: event.timestampUtc,
      });
      return { ...previous, turns, status: 'streaming', error: null };
    }
    case 'token':
    case 'delta':
    case 'text_delta': {
      const token = readString(data, 'text') || readString(data, 'token') || readString(data, 'delta');
      turn.status = 'streaming';
      turn.assistantMessage.text += token;
      return { ...previous, turns, status: 'streaming', error: null };
    }
    case 'router_decision':
    case 'expert_start':
    case 'expert_end':
    case 'policy_decision': {
      const title = readString(data, 'title') || event.event.replaceAll('_', ' ');
      const subtitle =
        readString(data, 'summary') ||
        readString(data, 'message') ||
        readString(data, 'reason_code') ||
        readString(data, 'expert') ||
        'Activity recorded';
      appendTimeline(turn, event, {
        tone: event.event === 'policy_decision' ? 'warning' : 'info',
        title,
        subtitle,
        timestampUtc: event.timestampUtc,
      });
      return { ...previous, turns, status: 'streaming', error: null };
    }
    case 'approval_pending': {
      const approvalId = extractApprovalIdFromEvent(event);
      const approval: AssistantApprovalSummary | null = approvalId
        ? {
            approvalId,
            title: readString(data, 'title', readString(data, 'summary', 'Approval required')),
            status: readString(data, 'status', 'pending'),
            risk: readRisk(data.risk ?? data.risk_class),
            detailLoaded: false,
          }
        : null;
      turn.status = 'awaiting_approval';
      turn.assistantMessage.approval = approval;
      turn.assistantMessage.proposedAction = {
        id: readString(data, 'action_id', approvalId ?? `${event.assistantTurnId}-action`),
        title: approval?.title ?? 'Approval required',
        target: readString(data, 'target', readString(data, 'target_ref', 'Governed action')),
        risk: approval?.risk ?? 'medium',
        dryRunSummary: readString(data, 'dry_run_summary', 'Execution is blocked until approval is reviewed.'),
        commandPreview: readString(data, 'command_preview'),
      };
      appendTimeline(turn, event, {
        tone: 'warning',
        title: 'Approval required',
        subtitle: approvalId ?? 'Pending approval id was not provided',
        timestampUtc: event.timestampUtc,
      });
      return {
        ...previous,
        turns,
        status: 'awaiting_approval',
        pendingApprovalId: approvalId,
        error: null,
      };
    }
    case 'audit_artifact': {
      const artifact = {
        name: readString(data, 'name', readString(data, 'artifact', 'artifact')),
        path: readString(data, 'path'),
        summary: readString(data, 'summary'),
      };
      turn.assistantMessage.referencedArtifacts.push(artifact);
      return {
        ...previous,
        turns,
        referencedArtifacts: [...previous.referencedArtifacts, artifact],
        error: null,
      };
    }
    case 'artifact_proposed':
    case 'artifact_committed':
    case 'artifact_patch_proposed':
    case 'artifact_patch_applied': {
      const artifactId = readString(data, 'artifactId') || readString(data, 'artifact_id');
      const revisionId = readString(data, 'revisionId') || readString(data, 'revision_id');
      const kind = readString(data, 'kind');
      const artifact = {
        name: readString(data, 'title', artifactId || kind || 'artifact'),
        artifactId: artifactId || undefined,
        revisionId: revisionId || undefined,
        kind: kind || undefined,
        openable: event.event === 'artifact_committed' || event.event === 'artifact_patch_applied',
        summary: readString(data, 'summary', event.event.replaceAll('_', ' ')),
      };
      turn.assistantMessage.referencedArtifacts.push(artifact);
      if (artifactId) {
        turn.assistantMessage.parts.push({
          type: 'artifact',
          artifactId,
          revisionId: revisionId || null,
          kind: kind || 'unknown',
          title: artifact.name,
          summary: artifact.summary,
          openable: artifact.openable,
        });
      }
      if (event.event === 'artifact_patch_proposed') {
        const proposalId = readString(data, 'proposalId') || readString(data, 'proposal_id');
        const approvalId = readString(data, 'approvalId') || readString(data, 'approval_id');
        const actionHash = readString(data, 'actionHash') || readString(data, 'action_hash');
        const baseRevisionNumber = readPositiveInt(data, 'baseRevisionNumber') ?? readPositiveInt(data, 'base_revision_number');
        if (artifactId && proposalId && approvalId && /^[a-f0-9]{64}$/.test(actionHash) && baseRevisionNumber !== null) {
          const error = readString(data, 'error');
          turn.assistantMessage.parts.push({
            type: 'artifact-proposal',
            proposalId,
            artifactId,
            approvalId,
            actionHash,
            baseRevisionNumber,
            title: artifact.name,
            kind: kind || 'unknown',
            summary: artifact.summary,
            status: readProposalStatus(data.status),
            error: error ? error.slice(0, 500) : null,
          });
        }
      }
      appendTimeline(turn, event, {
        tone: event.event.endsWith('committed') || event.event.endsWith('applied') ? 'success' : 'info',
        title: event.event.replaceAll('_', ' '),
        subtitle: artifactId || artifact.name,
        timestampUtc: event.timestampUtc,
      });
      return {
        ...previous,
        turns,
        referencedArtifacts: [...previous.referencedArtifacts, artifact],
        error: null,
      };
    }
    case 'form_requested':
    case 'form_submitted': {
      const artifactId = readString(data, 'artifactId') || readString(data, 'artifact_id');
      const revisionId = readString(data, 'revisionId') || readString(data, 'revision_id');
      const artifact = {
        name: readString(data, 'title', artifactId || 'form'),
        artifactId: artifactId || undefined,
        revisionId: revisionId || undefined,
        kind: 'form',
        openable: Boolean(artifactId),
        summary: event.event.replaceAll('_', ' '),
      };
      turn.assistantMessage.referencedArtifacts.push(artifact);
      if (artifactId && revisionId) {
        turn.assistantMessage.parts.push({
          type: 'form',
          artifactId,
          revisionId,
          title: artifact.name,
          status: event.event === 'form_requested'
            ? 'requested'
            : (data.status === 'accepted' || data.status === 'rejected' || data.status === 'pending_continuation'
                ? data.status
                : 'rejected'),
        });
      }
      appendTimeline(turn, event, {
        tone: event.event === 'form_submitted' ? 'success' : 'info',
        title: event.event.replaceAll('_', ' '),
        subtitle: artifactId || 'form',
        timestampUtc: event.timestampUtc,
      });
      return {
        ...previous,
        turns,
        referencedArtifacts: [...previous.referencedArtifacts, artifact],
        error: null,
      };
    }
    case 'tool_result': {
      appendTimeline(turn, event, {
        tone: readString(data, 'status') === 'failed' ? 'error' : 'info',
        title: readString(data, 'toolName', 'tool result'),
        subtitle: readString(data, 'status', 'completed'),
        timestampUtc: event.timestampUtc,
      });
      return { ...previous, turns, status: 'streaming', error: null };
    }
    case 'final': {
      const finalText = readString(data, 'finalText') || readString(data, 'final_text') || readString(data, 'text') || readString(data, 'content');
      if (finalText) {
        turn.assistantMessage.text = finalText;
      }
      turn.status = 'completed';
      turn.completedAtUtc = event.timestampUtc;
      turn.assistantMessage.metrics = {
        traceId: readString(data, 'traceId') || readString(data, 'trace_id'),
        usedPath: readString(data, 'usedPath') || readString(data, 'used_path'),
        fallbackEvents: (readArray(data, 'fallbackEvents').length
          ? readArray(data, 'fallbackEvents')
          : readArray(data, 'fallback_events')).filter((item): item is string => typeof item === 'string'),
      };
      return { ...previous, turns, status: 'completed', activeTurnId: null, error: null };
    }
    case 'warning': {
      turn.assistantMessage.warning = readString(data, 'message', 'Assistant stream warning');
      appendTimeline(turn, event, {
        tone: 'warning',
        title: 'Warning',
        subtitle: turn.assistantMessage.warning,
        timestampUtc: event.timestampUtc,
      });
      return { ...previous, turns, error: null };
    }
    case 'error': {
      const error = normalizeAssistantError(data);
      turn.status = 'failed';
      turn.completedAtUtc = event.timestampUtc;
      turn.assistantMessage.error = error;
      return { ...previous, turns, status: 'failed', activeTurnId: null, error };
    }
    case 'cancelled': {
      turn.status = 'cancelled';
      turn.completedAtUtc = event.timestampUtc;
      turn.assistantMessage.warning = readString(data, 'message', 'Assistant turn cancelled.');
      appendTimeline(turn, event, {
        tone: 'warning',
        title: 'Cancelled',
        subtitle: turn.assistantMessage.warning,
        timestampUtc: event.timestampUtc,
      });
      return { ...previous, turns, status: 'cancelled', activeTurnId: null, error: null };
    }
    default: {
      const exhaustive: never = event.event;
      return exhaustive;
    }
  }
}

export function normalizeAssistantError(error: unknown): AssistantUiError {
  const bridgePayload = asRecord(asRecord(error).payload);
  if (bridgePayload.code || bridgePayload.message) {
    return fromBridgePayload(bridgePayload);
  }
  const record = asRecord(error);
  return {
    code: readString(record, 'code', 'ASSISTANT_FAILED'),
    message: readString(record, 'message', 'Assistant turn failed.'),
    retryable: record.retryable === true,
    stderrPreview: readString(record, 'stderrPreview') || readString(record, 'stderr_preview') || undefined,
  };
}

function fromBridgePayload(payload: RecordValue): AssistantUiError {
  return {
    code: readString(payload, 'code', 'ASSISTANT_FAILED'),
    message: readString(payload, 'message', 'Assistant turn failed.'),
    retryable: payload.retryable === true,
    stderrPreview: readString(payload, 'stderrPreview') || undefined,
  };
}
