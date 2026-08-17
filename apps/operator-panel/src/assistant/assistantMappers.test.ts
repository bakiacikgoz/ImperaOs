import { describe, expect, it } from 'vitest';

import assistantRuntimeGolden from '../../../../contracts/operator_panel/fixtures/assistant_runtime_v3_golden.json';

import {
  createAssistantSession,
  createAssistantTurn,
  extractApprovalIdFromEvent,
  mapCliAssistantEvent,
  normalizeAssistantStreamEvent,
  startAssistantTurnLocally,
} from './assistantMappers';

function started() {
  const session = createAssistantSession('session-test');
  const turn = createAssistantTurn({
    id: 'turn-test',
    sessionId: session.sessionId,
    userMessage: 'inspect failed run',
    createdAtUtc: '2026-03-08T09:00:00Z',
  });
  return startAssistantTurnLocally(session, turn);
}

function startedFor(sessionId: string, turnId: string) {
  const session = createAssistantSession(sessionId);
  const turn = createAssistantTurn({
    id: turnId,
    sessionId,
    userMessage: 'golden parity scenario',
    createdAtUtc: '2026-07-16T07:00:00Z',
  });
  return startAssistantTurnLocally(session, turn);
}

describe('assistant mappers', () => {
  it.each([
    ['missing', undefined],
    ['former', ['2', '0'].join('.')],
  ])('drops %s contract versions without mutating state', (_label, contractVersion) => {
    const state = started();
    const rawEvent = {
      ...(contractVersion ? { contractVersion } : {}),
      assistantTurnId: 'turn-test',
      sessionId: 'session-test',
      event: 'token',
      sequence: 1,
      timestampUtc: '2026-03-08T09:00:01Z',
      data: { text: 'must not be appended' },
    };

    expect(normalizeAssistantStreamEvent(rawEvent)).toBeNull();
    expect(mapCliAssistantEvent(rawEvent as never, state)).toBe(state);
    expect(state.turns[0].assistantMessage.text).toBe('');
    expect(state.turns[0].eventSequence).toBe(0);
  });

  it('drops unknown event names instead of coercing them to status', () => {
    const state = started();
    const spoofed = {
      contractVersion: '3.0',
      assistantTurnId: 'turn-test',
      sessionId: 'session-test',
      event: 'artifact_patch_applied_without_approval',
      sequence: 1,
      timestampUtc: '2026-03-08T09:00:01Z',
      data: { status: 'completed' },
    };

    expect(normalizeAssistantStreamEvent(spoofed)).toBeNull();
    expect(mapCliAssistantEvent(spoofed, state)).toBe(state);
  });

  it('holds sequence gaps until the missing event arrives', () => {
    const first = mapCliAssistantEvent(
      {
        contractVersion: '3.0', assistantTurnId: 'turn-test', sessionId: 'session-test',
        event: 'token', sequence: 1, timestampUtc: '2026-03-08T09:00:01Z', data: { text: 'A' },
      },
      started(),
    );
    const gap = mapCliAssistantEvent(
      {
        contractVersion: '3.0', assistantTurnId: 'turn-test', sessionId: 'session-test',
        event: 'token', sequence: 3, timestampUtc: '2026-03-08T09:00:03Z', data: { text: 'C' },
      },
      first,
    );

    expect(gap.turns[0].assistantMessage.text).toBe('A');
    expect(gap.turns[0].eventSequence).toBe(1);
    expect(gap.turns[0].assistantMessage.warning).toBe('Assistant event sequence gap detected.');

    const recovered = mapCliAssistantEvent(
      {
        contractVersion: '3.0', assistantTurnId: 'turn-test', sessionId: 'session-test',
        event: 'token', sequence: 2, timestampUtc: '2026-03-08T09:00:02Z', data: { text: 'B' },
      },
      gap,
    );
    expect(recovered.turns[0].assistantMessage.text).toBe('AB');
    expect(recovered.turns[0].eventSequence).toBe(2);
  });

  it('appends token events and ignores duplicate sequences', () => {
    const state = started();
    const withToken = mapCliAssistantEvent(
      {
        contractVersion: '3.0',
        assistantTurnId: 'turn-test',
        sessionId: 'session-test',
        event: 'token',
        sequence: 1,
        timestampUtc: '2026-03-08T09:00:01Z',
        data: { text: 'Hello' },
      },
      state,
    );
    const duplicate = mapCliAssistantEvent(
      {
        contractVersion: '3.0',
        assistantTurnId: 'turn-test',
        sessionId: 'session-test',
        event: 'token',
        sequence: 1,
        timestampUtc: '2026-03-08T09:00:01Z',
        data: { text: ' again' },
      },
      withToken,
    );

    expect(duplicate.turns[0].assistantMessage.text).toBe('Hello');
  });

  it('maps v3 text, artifact, and form events while preserving v2 token support', () => {
    const withText = mapCliAssistantEvent(
      {
        contractVersion: '3.0',
        eventId: 'event-1',
        assistantTurnId: 'turn-test',
        sessionId: 'session-test',
        event: 'text_delta',
        sequence: 1,
        timestampUtc: '2026-07-16T08:00:00Z',
        traceId: 'trace-1',
        dataClass: 'internal',
        data: { text: 'Draft' },
      },
      started(),
    );
    const withArtifact = mapCliAssistantEvent(
      {
        contractVersion: '3.0',
        eventId: 'event-2',
        assistantTurnId: 'turn-test',
        sessionId: 'session-test',
        event: 'artifact_committed',
        sequence: 2,
        timestampUtc: '2026-07-16T08:00:01Z',
        traceId: 'trace-1',
        dataClass: 'internal',
        data: { artifactId: 'artifact-1', revisionId: 'revision-1', kind: 'document' },
      },
      withText,
    );
    const withProposal = mapCliAssistantEvent(
      {
        contractVersion: '3.0',
        eventId: 'event-2b',
        assistantTurnId: 'turn-test',
        sessionId: 'session-test',
        event: 'artifact_proposed',
        sequence: 3,
        timestampUtc: '2026-07-16T08:00:02Z',
        traceId: 'trace-1',
        dataClass: 'internal',
        data: { artifactId: 'artifact-proposal', kind: 'document' },
      },
      withArtifact,
    );
    const withForm = mapCliAssistantEvent(
      {
        contractVersion: '3.0',
        eventId: 'event-3',
        assistantTurnId: 'turn-test',
        sessionId: 'session-test',
        event: 'form_requested',
        sequence: 4,
        timestampUtc: '2026-07-16T08:00:02Z',
        traceId: 'trace-1',
        dataClass: 'confidential',
        data: { artifactId: 'form-1', revisionId: 'revision-form-1', schema: { type: 'object' } },
      },
      withProposal,
    );

    expect(withForm.turns[0].assistantMessage.text).toBe('Draft');
    expect(withForm.referencedArtifacts).toEqual([
      expect.objectContaining({ artifactId: 'artifact-1', revisionId: 'revision-1', kind: 'document', openable: true }),
      expect.objectContaining({ artifactId: 'artifact-proposal', kind: 'document', openable: false }),
      expect.objectContaining({ artifactId: 'form-1', revisionId: 'revision-form-1', kind: 'form', openable: true }),
    ]);
  });

  it('marks final events as completed with metrics', () => {
    const completed = mapCliAssistantEvent(
      {
        contractVersion: '3.0',
        assistantTurnId: 'turn-test',
        sessionId: 'session-test',
        event: 'final',
        sequence: 1,
        timestampUtc: '2026-03-08T09:00:02Z',
        data: {
          finalText: 'Done',
          traceId: 'trace-1',
          usedPath: 'governed_artifact_tools',
          fallbackEvents: [],
        },
      },
      started(),
    );

    expect(completed.status).toBe('completed');
    expect(completed.activeTurnId).toBeNull();
    expect(completed.turns[0].assistantMessage.text).toBe('Done');
    expect(completed.turns[0].assistantMessage.metrics?.traceId).toBe('trace-1');
    expect(completed.turns[0].assistantMessage.metrics?.usedPath).toBe('governed_artifact_tools');
  });

  it('maps approval pending events into guarded approval state', () => {
    const event = {
      contractVersion: '3.0',
      assistantTurnId: 'turn-test',
      sessionId: 'session-test',
      event: 'approval_pending' as const,
      sequence: 1,
      timestampUtc: '2026-03-08T09:00:03Z',
      data: { approval_id: 'apr_1', title: 'Run action', risk: 'medium' },
    };
    const awaitingApproval = mapCliAssistantEvent(event, started());

    expect(extractApprovalIdFromEvent(event)).toBe('apr_1');
    expect(awaitingApproval.status).toBe('awaiting_approval');
    expect(awaitingApproval.pendingApprovalId).toBe('apr_1');
    expect(awaitingApproval.turns[0].assistantMessage.approval?.detailLoaded).toBe(false);
  });

  it('maps only fully bound artifact patch proposals to typed inline parts', () => {
    const proposed = mapCliAssistantEvent(
      {
        contractVersion: '3.0',
        eventId: 'event-proposal',
        assistantTurnId: 'turn-test',
        sessionId: 'session-test',
        event: 'artifact_patch_proposed',
        sequence: 1,
        timestampUtc: '2026-07-16T08:00:00Z',
        traceId: 'trace-1',
        dataClass: 'internal',
        data: {
          artifactId: 'artifact-1',
          proposalId: 'proposal-1',
          approvalId: 'approval-1',
          actionHash: 'a'.repeat(64),
          baseRevisionNumber: 3,
          kind: 'document',
          title: 'Brief update',
          summary: 'Update the opening paragraph',
          status: 'pending',
        },
      },
      started(),
    );

    expect(proposed.turns[0].assistantMessage.parts).toEqual([
      expect.objectContaining({ type: 'artifact', artifactId: 'artifact-1', openable: false }),
      expect.objectContaining({
        type: 'artifact-proposal',
        proposalId: 'proposal-1',
        approvalId: 'approval-1',
        actionHash: 'a'.repeat(64),
        baseRevisionNumber: 3,
      }),
    ]);
  });

  it('unwraps legacy nested trace data for approvals and audit artifacts', () => {
    const awaitingApproval = mapCliAssistantEvent(
      {
        contractVersion: '3.0',
        assistantTurnId: 'turn-test',
        sessionId: 'session-test',
        event: 'approval_pending',
        sequence: 1,
        timestampUtc: '2026-03-08T09:00:03Z',
        data: {
          stage: 'approval_pending',
          request_id: 'request-1',
          data: { approval_id: 'apr_nested', title: 'Nested approval', risk: 'high' },
        },
      },
      started(),
    );
    const withArtifact = mapCliAssistantEvent(
      {
        contractVersion: '3.0',
        assistantTurnId: 'turn-test',
        sessionId: 'session-test',
        event: 'audit_artifact',
        sequence: 2,
        timestampUtc: '2026-03-08T09:00:04Z',
        data: {
          stage: 'audit_artifact',
          request_id: 'request-1',
          data: { path: 'artifacts/job-1/audit.json', summary: 'Nested evidence' },
        },
      },
      awaitingApproval,
    );

    expect(awaitingApproval.pendingApprovalId).toBe('apr_nested');
    expect(awaitingApproval.turns[0].assistantMessage.approval?.title).toBe('Nested approval');
    expect(withArtifact.referencedArtifacts).toEqual([
      { name: 'artifact', path: 'artifacts/job-1/audit.json', summary: 'Nested evidence' },
    ]);
  });

  it('keeps warning events non-blocking', () => {
    const warned = mapCliAssistantEvent(
      {
        contractVersion: '3.0',
        assistantTurnId: 'turn-test',
        sessionId: 'session-test',
        event: 'warning',
        sequence: 1,
        timestampUtc: '2026-03-08T09:00:04Z',
        data: { message: 'ignored malformed stdout line' },
      },
      started(),
    );

    expect(warned.status).toBe('starting');
    expect(warned.turns[0].assistantMessage.warning).toBe('ignored malformed stdout line');
  });

  it('maps cancelled events into a non-error terminal state', () => {
    const cancelled = mapCliAssistantEvent(
      {
        contractVersion: '3.0',
        assistantTurnId: 'turn-test',
        sessionId: 'session-test',
        event: 'cancelled',
        sequence: 1,
        timestampUtc: '2026-03-08T09:00:05Z',
        data: { message: 'Assistant turn cancelled by operator.' },
      },
      started(),
    );

    expect(cancelled.status).toBe('cancelled');
    expect(cancelled.activeTurnId).toBeNull();
    expect(cancelled.error).toBeNull();
    expect(cancelled.turns[0].status).toBe('cancelled');
  });

  it('projects every assistant runtime golden scenario into the expected session state', () => {
    for (const scenario of assistantRuntimeGolden.scenarios) {
      const firstEvent = scenario.events[0];
      const projected = scenario.events.reduce(
        (state, event) => mapCliAssistantEvent(event, state),
        startedFor(firstEvent.sessionId, firstEvent.assistantTurnId),
      );
      const expected = scenario.expectedSession as unknown as Record<string, string | number | null>;
      const turn = projected.turns[0];

      expect(projected.status, scenario.id).toBe(expected.status);
      expect(turn.assistantMessage.text, scenario.id).toBe(expected.text);
      expect(projected.pendingApprovalId, scenario.id).toBe(expected.pendingApprovalId);
      if (typeof expected.timelineCount === 'number') {
        expect(turn.assistantMessage.timeline.length - 1, scenario.id).toBe(expected.timelineCount);
      }
      if (typeof expected.referencedArtifactCount === 'number') {
        expect(projected.referencedArtifacts, scenario.id).toHaveLength(expected.referencedArtifactCount);
      }
      if (typeof expected.errorCode === 'string') {
        expect(projected.error?.code, scenario.id).toBe(expected.errorCode);
      }
      if (typeof expected.approvalStatus === 'string') {
        expect(turn.assistantMessage.approval?.status, scenario.id).toBe(expected.approvalStatus);
      }
    }
  });
});
