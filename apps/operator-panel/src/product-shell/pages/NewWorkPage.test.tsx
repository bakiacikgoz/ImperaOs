import { screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const workspace = vi.hoisted(() => ({
  listProjects: vi.fn(),
  getOrCreateProject: vi.fn(),
  createTask: vi.fn(),
  addMessage: vi.fn(),
}));
const navigate = vi.hoisted(() => vi.fn());

vi.mock('../adapters/productWorkspaceClient', () => ({ productWorkspaceClient: workspace }));
vi.mock('../../components/assistant/AssistantComposer', () => ({
  AssistantComposer: ({
    onSend,
    projectControl,
    variant,
  }: {
    onSend: (message: string, settings: unknown, controls: unknown) => void;
    projectControl?: React.ReactNode;
    variant?: string;
  }) => (
    <div data-testid="assistant-composer" data-variant={variant}>
      {projectControl}
      <button type="button" onClick={() => onSend('Prepare a release', {
        assistantProvider: 'ollama', assistantFallbackProvider: '', assistantModel: 'qwen3.5:4b', assistantHfModelId: '',
      }, { contextAttachmentKinds: ['artifact_summary'], toolIntents: ['inspect_run'] })}>Submit composed work</button>
    </div>
  ),
}));
vi.mock('react-router-dom', async (importOriginal) => ({
  ...(await importOriginal<typeof import('react-router-dom')>()),
  useNavigate: () => navigate,
}));

import { renderOperatorPanel } from '../../test/render';
import { useProductShellStore } from '../state/productShellStore';
import { NewWorkPage } from './NewWorkPage';

const existingProject = {
  projectId: 'project-existing', workspaceId: 'workspace-1', title: 'Release work', status: 'active',
  createdAtUtc: '2026-07-24T12:00:00Z', updatedAtUtc: '2026-07-24T12:00:00Z',
};

describe('NewWorkPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useProductShellStore.setState({ tasks: [], selectedTaskId: null });
    workspace.listProjects.mockResolvedValue({ projects: [existingProject] });
    workspace.createTask.mockImplementation(async (projectId, _title, assistantSessionId) => ({
      taskId: 'task-1', projectId, title: 'Prepare a release', status: 'active', assistantSessionId,
      createdAtUtc: '2026-07-24T12:01:00Z', updatedAtUtc: '2026-07-24T12:01:00Z',
    }));
    workspace.addMessage.mockResolvedValue({ messageId: 'message-1' });
  });

  it('creates work in the project the user selected', async () => {
    const { user } = renderOperatorPanel(<MemoryRouter><NewWorkPage /></MemoryRouter>);

    expect(document.querySelector('.new-work-page.codex-home')).toBeInTheDocument();
    expect(document.querySelector('.suggestion-grid.codex-suggestions')).toBeInTheDocument();
    expect(screen.getByTestId('assistant-composer')).toHaveAttribute('data-variant', 'product');
    await screen.findByRole('option', { name: 'Release work' });
    await user.selectOptions(screen.getByRole('combobox', { name: 'Project' }), 'project-existing');
    await user.click(screen.getByRole('button', { name: 'Submit composed work' }));

    expect(workspace.createTask).toHaveBeenCalledWith('project-existing', 'Prepare a release', expect.stringMatching(/^product-session-/), {
      reasoningEffort: 'medium', speedProfile: 'standard', approvalProfile: 'risk_based',
    });
    expect(workspace.addMessage).toHaveBeenCalledWith('task-1', 'user', 'Prepare a release');
    expect(workspace.getOrCreateProject).not.toHaveBeenCalled();
    const persistedSessionId = workspace.createTask.mock.calls[0][2];
    expect(useProductShellStore.getState().tasks).toContainEqual(
      expect.objectContaining({ id: 'task-1', assistantSessionId: persistedSessionId }),
    );
    expect(navigate).toHaveBeenCalledWith('/task/task-1', {
      state: expect.objectContaining({
        initialMessage: 'Prepare a release',
        runtimeSettings: expect.objectContaining({ assistantProvider: 'ollama', assistantModel: 'qwen3.5:4b' }),
        controls: { contextAttachmentKinds: ['artifact_summary'], toolIntents: ['inspect_run'] },
      }),
    });
  });

  it('truthfully labels and creates the fallback project when no durable project exists', async () => {
    workspace.listProjects.mockResolvedValue({ projects: [] });
    workspace.getOrCreateProject.mockResolvedValue({ projectId: 'project-created' });
    const { user } = renderOperatorPanel(<MemoryRouter><NewWorkPage /></MemoryRouter>);

    expect(await screen.findByRole('option', { name: 'Yeni “Operator work” projesi oluştur' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Submit composed work' }));

    expect(workspace.getOrCreateProject).toHaveBeenCalledWith('Operator work');
    expect(workspace.createTask).toHaveBeenCalledWith(
      'project-created',
      'Prepare a release',
      expect.stringMatching(/^product-session-/),
      expect.any(Object),
    );
  });

  it('stays on New Work when the initial message cannot be persisted', async () => {
    workspace.addMessage.mockRejectedValue(new Error('Initial message persistence failed.'));
    const { user } = renderOperatorPanel(<MemoryRouter><NewWorkPage /></MemoryRouter>);

    await screen.findByRole('option', { name: 'Release work' });
    await user.click(screen.getByRole('button', { name: 'Submit composed work' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Initial message persistence failed.');
    expect(navigate).not.toHaveBeenCalled();
    expect(useProductShellStore.getState()).toMatchObject({ tasks: [], selectedTaskId: null });
  });
});
