import { screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

const workspace = vi.hoisted(() => ({ listMessages: vi.fn(), listLinks: vi.fn() }));

vi.mock('../adapters/productWorkspaceClient', () => ({ productWorkspaceClient: workspace }));

import { getAssistantFixture } from '../../assistant/assistantFixtures';
import { renderOperatorPanel } from '../../test/render';
import { ProductConversationView } from './ProductConversationView';

describe('ProductConversationView artifacts', () => {
  it('renders durable turns with the UI Lab conversation hierarchy', async () => {
    workspace.listMessages.mockResolvedValue({
      messages: [
        { messageId: 'message-user', role: 'user', body: 'Prepare release', createdAtUtc: '2026-07-25T00:00:00Z' },
        { messageId: 'message-assistant', role: 'assistant', body: 'Release prepared', createdAtUtc: '2026-07-25T00:00:01Z' },
      ],
    });
    workspace.listLinks.mockResolvedValue({ links: [] });
    const { container } = renderOperatorPanel(
      <ProductConversationView state={getAssistantFixture('welcome')} taskId="task-1" />,
    );

    expect(await screen.findByText('Prepare release')).toBeInTheDocument();
    expect(container.querySelector('.conversation-view .conversation-inner')).toBeInTheDocument();
    expect(container.querySelector('.user-message')).toBeInTheDocument();
    expect(container.querySelector('.completion-message')).toBeInTheDocument();
    expect(container.querySelector('.message-feedback')).toBeInTheDocument();
  });

  it('opens an assistant-produced artifact in the governed workspace', async () => {
    workspace.listMessages.mockResolvedValue({ messages: [] });
    workspace.listLinks.mockResolvedValue({ links: [] });
    const state = getAssistantFixture('running');
    state.referencedArtifacts = [{
      name: 'Release plan', artifactId: 'artifact-release-plan', revisionId: 'revision-1', kind: 'document',
      openable: true, summary: 'Governed release document',
    }];
    const onOpenArtifacts = vi.fn();
    const { user } = renderOperatorPanel(<ProductConversationView state={state} taskId="task-1" onOpenArtifacts={onOpenArtifacts} />);

    await user.click(await screen.findByRole('button', { name: 'Open in workspace' }));

    expect(onOpenArtifacts).toHaveBeenCalledWith('artifact-release-plan');
  });

  it('routes a governed assistant approval to its canonical detail', async () => {
    workspace.listMessages.mockResolvedValue({ messages: [] });
    workspace.listLinks.mockResolvedValue({ links: [] });
    const state = getAssistantFixture('running');
    state.turns[0].assistantMessage.approval = {
      approvalId: 'approval-release', title: 'Release', status: 'pending', risk: 'medium', detailLoaded: false,
    };
    const onOpenApproval = vi.fn();
    const { user } = renderOperatorPanel(<ProductConversationView state={state} taskId="task-1" onOpenApproval={onOpenApproval} />);

    await user.click(await screen.findByRole('button', { name: 'Open approval' }));

    expect(onOpenApproval).toHaveBeenCalledWith('approval-release');
    expect(screen.getByRole('button', { name: 'Feedback unavailable' })).toHaveAttribute(
      'data-disabled-reason',
      'ASSISTANT_FEEDBACK_CAPABILITY_UNAVAILABLE',
    );
  });

  it('keeps durable artifact and approval actions available after a task reload', async () => {
    workspace.listMessages.mockResolvedValue({ messages: [{ messageId: 'message-1', role: 'assistant', body: 'Release ready', createdAtUtc: '2026-07-25T00:00:00Z' }] });
    workspace.listLinks.mockResolvedValue({ links: [
      { linkId: 'link-artifact', workspaceId: 'workspace-1', taskId: 'task-1', targetType: 'artifact', targetId: 'artifact-release', createdAtUtc: '2026-07-25T00:00:00Z' },
      { linkId: 'link-approval', workspaceId: 'workspace-1', taskId: 'task-1', targetType: 'approval', targetId: 'approval-release', createdAtUtc: '2026-07-25T00:00:00Z' },
    ] });
    const onOpenArtifacts = vi.fn();
    const onOpenApproval = vi.fn();
    const { user } = renderOperatorPanel(<ProductConversationView state={getAssistantFixture('welcome')} taskId="task-1" onOpenArtifacts={onOpenArtifacts} onOpenApproval={onOpenApproval} />);

    await user.click(await screen.findByRole('button', { name: 'Open artifact artifact-release' }));
    await user.click(screen.getByRole('button', { name: 'Open approval approval-release' }));

    expect(onOpenArtifacts).toHaveBeenCalledWith('artifact-release');
    expect(onOpenApproval).toHaveBeenCalledWith('approval-release');
  });

  it('surfaces durable conversation bridge failures instead of presenting a normal empty state', async () => {
    workspace.listMessages.mockRejectedValue(new Error('Product workspace bridge unavailable'));
    workspace.listLinks.mockResolvedValue({ links: [] });

    renderOperatorPanel(<ProductConversationView state={getAssistantFixture('welcome')} taskId="task-1" />);

    expect(await screen.findByRole('alert')).toHaveTextContent('Product workspace bridge unavailable');
    expect(screen.queryByRole('heading', { name: 'Start governed work' })).not.toBeInTheDocument();
  });
});
