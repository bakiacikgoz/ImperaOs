import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { getAssistantFixture } from '../../assistant/assistantFixtures';
import { renderOperatorPanel } from '../../test/render';
import { ContextRail } from './ContextRail';

describe('ContextRail', () => {
  it('renders real runtime references and makes a pending approval navigable', () => {
    const state = getAssistantFixture('approval_required');
    state.pendingApprovalId = 'apr-release';
    state.turns[0].assistantMessage.referencedRuns = [{ id: 'run-release', status: 'blocked' }];
    state.turns[0].composerControls = {
      contextAttachmentKinds: ['active_run'],
      toolIntents: ['inspect_run'],
    };

    const { container } = renderOperatorPanel(<ContextRail task={{ id: 'task-release', title: 'Release approval', createdAt: '2026-07-25T00:00:00Z', status: 'awaiting_approval' }} state={state} />);

    expect(container.querySelector('.context-rail.reference-environment-rail')).toBeInTheDocument();
    expect(container.querySelector('.environment-rows')).toBeInTheDocument();
    expect(container.querySelector('.environment-section')).toBeInTheDocument();
    expect(screen.getByText('run-release')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open approval apr-release' })).toHaveAttribute('href', '#/approvals');
    expect(screen.getByText('attachment · active_run')).toBeInTheDocument();
    expect(screen.getByText('safe intent · inspect_run')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Branch context unavailable' })).toBeDisabled();
  });
});
