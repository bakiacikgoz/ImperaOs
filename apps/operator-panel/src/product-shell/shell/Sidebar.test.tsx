import { screen, waitFor } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const workspace = vi.hoisted(() => ({
  listProjects: vi.fn(), listTasks: vi.fn(), updateProject: vi.fn(), updateTask: vi.fn(),
  archiveProject: vi.fn(), archiveTask: vi.fn(), registerProjectFromFolder: vi.fn(),
}));

vi.mock('../adapters/productWorkspaceClient', () => ({ productWorkspaceClient: workspace }));
vi.mock('./GlobalSearch', () => ({ GlobalSearch: () => <div /> }));

import { renderOperatorPanel } from '../../test/render';
import { useProductShellStore } from '../state/productShellStore';
import { Sidebar } from './Sidebar';

const project = {
  projectId: 'project-release', workspaceId: 'workspace-1', title: 'Release workspace',
  rootRef: 'root-release', rootDisplayName: 'Release workspace', status: 'active' as const,
  pinned: false, manualOrder: 2, createdAtUtc: '2026-07-24T12:00:00Z', updatedAtUtc: '2026-07-24T12:00:00Z', archivedAtUtc: null,
};
const task = {
  taskId: 'task-release', workspaceId: 'workspace-1', projectId: 'project-release',
  title: 'Prepare release', status: 'active' as const, priority: 1, pinned: false, manualOrder: 3,
  reasoningEffort: 'high' as const, speedProfile: 'standard' as const, approvalProfile: 'risk_based' as const,
  assistantSessionId: 'session-release', assistantTurnId: null, teamJobId: null,
  createdAtUtc: '2026-07-24T12:00:00Z', updatedAtUtc: '2026-07-24T12:00:00Z', archivedAtUtc: null,
};
const archivedTask = {
  ...task,
  status: 'archived' as const,
  updatedAtUtc: '2026-08-07T07:00:00Z',
  archivedAtUtc: '2026-08-07T07:00:00Z',
};

function LocationProbe() {
  return <p>Current route: {useLocation().pathname}</p>;
}

describe('Sidebar project lifecycle', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    useProductShellStore.setState(useProductShellStore.getInitialState(), true);
    workspace.listProjects.mockResolvedValue({ projects: [project], nextCursor: null });
    workspace.listTasks.mockResolvedValue({ tasks: [task] });
    workspace.updateProject.mockResolvedValue({ ...project, pinned: true });
    workspace.updateTask.mockResolvedValue({ ...task, manualOrder: 2 });
  });

  it('renders durable projects and persists a pin action through the workspace client', async () => {
    const { user } = renderOperatorPanel(<MemoryRouter><Sidebar /></MemoryRouter>);

    expect(screen.getByRole('complementary', { name: 'Product navigation' }))
      .toHaveClass('sidebar', 'codex-sidebar');
    expect(screen.getByRole('button', { name: /kenar çubuğunu/i })).toBeVisible();
    await user.click(await screen.findByRole('button', { name: 'Pin Release workspace' }));

    await waitFor(() => expect(workspace.updateProject).toHaveBeenCalledWith('project-release', { pinned: true }));
  });

  it('preserves governed project and task manual-order mutations', async () => {
    const { user } = renderOperatorPanel(<MemoryRouter><Sidebar /></MemoryRouter>);

    await user.click(await screen.findByRole('button', { name: 'Move Release workspace up' }));
    await user.click((await screen.findAllByRole('button', { name: 'Move Prepare release up' }))[0]);

    await waitFor(() => expect(workspace.updateProject).toHaveBeenCalledWith('project-release', { manualOrder: 1 }));
    expect(workspace.updateTask).toHaveBeenCalledWith('task-release', { manualOrder: 2 });
  });

  it('renders the unavailable task-collection action as non-interactive truth', async () => {
    const { container } = renderOperatorPanel(<MemoryRouter><Sidebar /></MemoryRouter>);

    await screen.findAllByText('Prepare release');
    expect(container.querySelector('[data-disabled-reason="TASK_COLLECTION_ACTIONS_UNAVAILABLE"]'))
      .toHaveAttribute('aria-disabled', 'true');
    expect(screen.queryByRole('button', { name: /Görevleri düzenle/i })).not.toBeInTheDocument();
  });

  it('distinguishes the primary create route and keeps desktop-only data truth compact', async () => {
    workspace.listProjects.mockRejectedValueOnce(new Error(
      'Workspace data requires the ImperaOS desktop runtime. Open this screen in the desktop app.',
    ));

    const { container } = renderOperatorPanel(<MemoryRouter><Sidebar /></MemoryRouter>);

    expect(screen.getByRole('link', { name: /Yeni görev/i })).toHaveClass('sidebar-primary-action');
    expect(await screen.findByRole('alert')).toHaveClass('sidebar-runtime-notice');
    expect(container.querySelector('.sidebar-runtime-notice')).toHaveTextContent(/desktop runtime/i);
  });

  it('archives a selected task only after success, removes it from active navigation, and leaves its record retained', async () => {
    useProductShellStore.setState({ selectedTaskId: task.taskId });
    workspace.archiveTask.mockImplementation(async () => {
      workspace.listTasks.mockResolvedValue({ tasks: [archivedTask] });
      return archivedTask;
    });
    const { user } = renderOperatorPanel(
      <MemoryRouter initialEntries={[`/task/${task.taskId}/workspace`]}>
        <Sidebar />
        <LocationProbe />
      </MemoryRouter>,
    );

    await user.click((await screen.findAllByRole('button', { name: `Archive ${task.title}` }))[0]);

    await waitFor(() => expect(screen.getByText('Current route: /')).toBeInTheDocument());
    expect(screen.queryByText(task.title)).not.toBeInTheDocument();
    expect(useProductShellStore.getState().selectedTaskId).toBeNull();
    expect(useProductShellStore.getState().tasks).toEqual([
      expect.objectContaining({ id: task.taskId, status: 'archived' }),
    ]);
  });

  it('leaves the active row, task route, and selection unchanged when archive fails', async () => {
    useProductShellStore.setState({ selectedTaskId: task.taskId });
    workspace.archiveTask.mockRejectedValue(new Error('Archive denied'));
    const { user } = renderOperatorPanel(
      <MemoryRouter initialEntries={[`/task/${task.taskId}`]}>
        <Sidebar />
        <LocationProbe />
      </MemoryRouter>,
    );

    await user.click((await screen.findAllByRole('button', { name: `Archive ${task.title}` }))[0]);

    expect(await screen.findByRole('alert')).toHaveTextContent('Archive denied');
    expect(screen.getByText(`Current route: /task/${task.taskId}`)).toBeInTheDocument();
    expect(screen.getAllByText(task.title)).toHaveLength(2);
    expect(useProductShellStore.getState().selectedTaskId).toBe(task.taskId);
    expect(useProductShellStore.getState().tasks).toEqual([
      expect.objectContaining({ id: task.taskId, status: 'active' }),
    ]);
  });
});
