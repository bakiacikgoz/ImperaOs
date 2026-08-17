import { screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { AssistantTurn } from '../../assistant/assistantTypes';
import { renderOperatorPanel } from '../../test/render';
import { AssistantMessage } from './AssistantMessage';

const noop = () => undefined;

function turnWithText(userText: string, assistantText: string): AssistantTurn {
  return {
    id: 'turn-1',
    startedAtUtc: '2026-03-08T09:20:00Z',
    completedAtUtc: '2026-03-08T09:20:05Z',
    composerControls: null,
    status: 'completed',
    eventSequence: 3,
    userMessage: {
      id: 'turn-1-user',
      text: userText,
      createdAtUtc: '2026-03-08T09:20:00Z',
    },
    assistantMessage: {
      id: 'turn-1-assistant',
      text: assistantText,
      findings: [],
      timeline: [],
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

function renderMessage(turn: AssistantTurn, onOpenArtifact = noop) {
  return renderOperatorPanel(
    <AssistantMessage
      turn={turn}
      approvalDisabled={false}
      approvalDisabledReason=""
      emptyRunLabel="No run"
      debugRawEnabled={false}
      onReviewApproval={noop}
      onApprove={noop}
      onReject={noop}
      onExecute={noop}
      onRegenerate={noop}
      onOpenArtifact={onOpenArtifact}
    />,
  );
}

describe('AssistantMessage', () => {
  it('renders structured assistant markdown', () => {
    renderMessage(
      turnWithText(
        'Prepare a plan.',
        [
          '## Plan',
          '- Inspect `status.json`',
          '- Open [docs](https://example.com)',
          '',
          '| Step | State |',
          '| --- | --- |',
          '| Build | Pass |',
          '',
          '```ts',
          'const status = "pass";',
          '```',
        ].join('\n'),
      ),
    );

    expect(screen.getByRole('heading', { name: 'Plan' })).toBeInTheDocument();
    expect(screen.getByText('Inspect')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'docs' })).toHaveAttribute('href', 'https://example.com');
    expect(screen.getByRole('columnheader', { name: 'Step' })).toBeInTheDocument();
    expect(screen.getByText('const status = "pass";')).toBeInTheDocument();
  });

  it('collapses very long user messages without hiding the assistant response', async () => {
    const longUserText = Array(40).fill('Long diagnostic context with logs and repeated failure details.').join(' ');
    const { user } = renderMessage(turnWithText(longUserText, 'Short answer.'));

    expect(screen.getByRole('button', { name: 'Show more' })).toBeInTheDocument();
    expect(screen.getByText('Short answer.')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Show more' }));

    expect(screen.getByRole('button', { name: 'Collapse' })).toBeInTheDocument();
  });

  it('does not render operational timeline chips in the chat message', () => {
    const turn = turnWithText('Write a function.', 'Here is the function.');
    turn.assistantMessage.timeline = [
      {
        id: 'event-1',
        tone: 'warning',
        title: 'policy decision',
        subtitle: 'Approval required',
        timestampUtc: '2026-03-08T09:20:01Z',
      },
      {
        id: 'event-2',
        tone: 'info',
        title: 'Status',
        subtitle: 'Streaming response',
        timestampUtc: '2026-03-08T09:20:02Z',
      },
    ];

    renderMessage(turn);

    expect(screen.getByText('Here is the function.')).toBeInTheDocument();
    expect(screen.queryByText('policy decision')).not.toBeInTheDocument();
    expect(screen.queryByText('Approval required')).not.toBeInTheDocument();
    expect(screen.queryByText('Status')).not.toBeInTheDocument();
    expect(screen.queryByText('Streaming response')).not.toBeInTheDocument();
  });

  it('opens committed workspace artifacts by id and keeps audit references read-only', async () => {
    const turn = turnWithText('Create a project brief.', 'The draft is ready.');
    turn.assistantMessage.referencedArtifacts = [
      {
        name: 'Project brief',
        artifactId: 'artifact-project-brief',
        revisionId: 'revision-1',
        kind: 'document',
        summary: 'artifact committed',
        openable: true,
      },
      {
        name: 'Project brief proposal',
        artifactId: 'artifact-project-brief-proposal',
        kind: 'document',
        summary: 'artifact proposed',
        openable: false,
      },
      {
        name: 'status.json',
        path: 'runs/run-1/status.json',
        summary: 'Immutable audit artifact',
      },
    ];
    const onOpenArtifact = vi.fn();
    const { user } = renderMessage(turn, onOpenArtifact);

    await user.click(screen.getByRole('button', { name: 'Open Project brief' }));

    expect(onOpenArtifact).toHaveBeenCalledOnce();
    expect(onOpenArtifact).toHaveBeenCalledWith('artifact-project-brief');
    expect(screen.queryByRole('button', { name: 'Open Project brief proposal' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Open status.json' })).not.toBeInTheDocument();
  });

  it('renders governed artifact proposal parts through approval callbacks', async () => {
    const turn = turnWithText('Update the brief.', 'I prepared a governed proposal.');
    turn.assistantMessage.parts = [{
      type: 'artifact-proposal',
      proposalId: 'proposal-1',
      artifactId: 'artifact-1',
      approvalId: 'approval-1',
      actionHash: 'a'.repeat(64),
      baseRevisionNumber: 1,
      title: 'Brief update',
      kind: 'document',
      summary: 'Update the opening paragraph',
      status: 'pending',
      error: null,
    }];
    const onApprove = vi.fn();
    const { user } = renderOperatorPanel(
      <AssistantMessage
        turn={turn}
        approvalDisabled={false}
        approvalDisabledReason=""
        emptyRunLabel="No run"
        debugRawEnabled={false}
        onReviewApproval={noop}
        onApprove={onApprove}
        onReject={noop}
        onExecute={noop}
        onRegenerate={noop}
      />,
    );

    await user.click(screen.getByRole('button', { name: 'Approve proposal' }));

    expect(onApprove).toHaveBeenCalledWith('approval-1');
    expect(screen.getByRole('region', { name: 'Artifact proposal' })).toHaveTextContent('Update the opening paragraph');
    expect(screen.queryByText(/actionHash/)).not.toBeInTheDocument();
  });
});
