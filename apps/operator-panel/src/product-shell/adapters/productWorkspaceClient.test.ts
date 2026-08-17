import { beforeEach, describe, expect, it, vi } from 'vitest';

const invoke = vi.hoisted(() => vi.fn());

vi.mock('@tauri-apps/api/core', () => ({ invoke }));

import { ProductWorkspaceClient, ProductWorkspaceError } from './productWorkspaceClient';

const activeProject = {
  projectId: 'project-operator',
  workspaceId: 'workspace-1',
  title: 'Operator work',
  status: 'active',
  createdAtUtc: '2026-07-24T12:00:00Z',
  updatedAtUtc: '2026-07-24T12:00:00Z',
};

function success(data: unknown) {
  return { ok: true as const, data, error: null };
}

describe('ProductWorkspaceClient default projects', () => {
  beforeEach(() => vi.clearAllMocks());

  it('reuses the existing active operator project for new work', async () => {
    invoke.mockResolvedValueOnce(success({ projects: [activeProject] }));

    await expect(new ProductWorkspaceClient().getOrCreateProject('Operator work')).resolves.toMatchObject(activeProject);

    expect(invoke).toHaveBeenCalledTimes(1);
    expect(invoke).toHaveBeenLastCalledWith('bridge_product_project_list', expect.anything());
  });

  it('creates a project only when no active project has that title', async () => {
    invoke
      .mockResolvedValueOnce(success({ projects: [{ ...activeProject, status: 'archived' }] }))
      .mockResolvedValueOnce(success(activeProject));

    await expect(new ProductWorkspaceClient().getOrCreateProject('Operator work')).resolves.toMatchObject(activeProject);

    expect(invoke).toHaveBeenCalledTimes(2);
    expect(invoke).toHaveBeenLastCalledWith('bridge_product_project_create', expect.objectContaining({
      payload: expect.objectContaining({ params: expect.objectContaining({ title: 'Operator work' }) }),
    }));
  });

  it('sends durable project pin and ordering changes through the governed bridge', async () => {
    invoke.mockResolvedValueOnce(success({ ...activeProject, pinned: true, manualOrder: 3 }));

    await expect(new ProductWorkspaceClient().updateProject('project-operator', {
      pinned: true,
      manualOrder: 3,
    })).resolves.toMatchObject({ projectId: 'project-operator', pinned: true, manualOrder: 3 });

    expect(invoke).toHaveBeenCalledWith('bridge_product_project_update', expect.objectContaining({
      payload: expect.objectContaining({
        params: expect.objectContaining({ projectId: 'project-operator', pinned: true, manualOrder: 3 }),
        idempotencyKey: expect.stringMatching(/^project-update-/),
      }),
    }));
  });

  it('uses the native picker ticket without exposing a local filesystem path', async () => {
    invoke
      .mockResolvedValueOnce(success({ cancelled: false, folderTicket: 'folder-opaque-1', displayName: 'Release workspace' }))
      .mockResolvedValueOnce(success(activeProject));

    await expect(new ProductWorkspaceClient().registerProjectFromFolder()).resolves.toMatchObject(activeProject);

    expect(invoke).toHaveBeenLastCalledWith('bridge_product_project_register', {
      request: expect.objectContaining({ folderTicket: 'folder-opaque-1', name: 'Release workspace', idempotencyKey: expect.stringMatching(/^project-register-/) }),
    });
  });

  it('loads one durable task through the governed task-get bridge', async () => {
    const task = {
      taskId: 'task-release', workspaceId: 'workspace-1', projectId: 'project-operator', title: 'Prepare release',
      status: 'active', reasoningEffort: 'high', speedProfile: 'standard', approvalProfile: 'risk_based',
      assistantSessionId: 'session-release', assistantTurnId: null, teamJobId: null,
      createdAtUtc: '2026-07-24T12:00:00Z', updatedAtUtc: '2026-07-24T12:00:00Z',
    };
    invoke.mockResolvedValueOnce(success(task));

    await expect(new ProductWorkspaceClient().getTask('task-release')).resolves.toMatchObject(task);

    expect(invoke).toHaveBeenCalledWith('bridge_product_task_get', expect.objectContaining({
      payload: expect.objectContaining({ params: { taskId: 'task-release' } }),
    }));
  });

  it('reports a clear desktop-runtime requirement when native invoke is unavailable', async () => {
    invoke.mockRejectedValueOnce(new TypeError("Cannot read properties of undefined (reading 'invoke')"));

    await expect(new ProductWorkspaceClient().listProjects()).rejects.toThrow(
      'Workspace data requires the ImperaOS desktop runtime.',
    );
  });

  it('preserves governed product error codes and retryability for the shell', async () => {
    invoke.mockResolvedValueOnce({
      ok: false,
      data: null,
      error: {
        code: 'PRODUCT_RPC_UNAVAILABLE',
        message: 'The governed product runtime is temporarily unavailable.',
        retryable: true,
      },
    });

    await expect(new ProductWorkspaceClient().listProjects()).rejects.toMatchObject({
      name: 'ProductWorkspaceError',
      code: 'PRODUCT_RPC_UNAVAILABLE',
      retryable: true,
      message: 'The governed product runtime is temporarily unavailable.',
    } satisfies Partial<ProductWorkspaceError>);
  });

  it('archives a task through the governed archive bridge rather than local UI state', async () => {
    const task = {
      taskId: 'task-release', workspaceId: 'workspace-1', projectId: 'project-operator', title: 'Prepare release',
      status: 'archived', priority: 0, pinned: false, manualOrder: 0,
      reasoningEffort: 'medium', speedProfile: 'standard', approvalProfile: 'risk_based',
      assistantSessionId: 'session-release', assistantTurnId: null, teamJobId: null,
      createdAtUtc: '2026-07-24T12:00:00Z', updatedAtUtc: '2026-07-24T12:00:01Z', archivedAtUtc: '2026-07-24T12:00:01Z',
    };
    invoke.mockResolvedValueOnce(success(task));

    await expect(new ProductWorkspaceClient().archiveTask('task-release', 'Completed in sidebar')).resolves.toMatchObject(task);

    expect(invoke).toHaveBeenCalledWith('bridge_product_task_archive', expect.objectContaining({
      payload: expect.objectContaining({
        params: expect.objectContaining({ taskId: 'task-release', reason: 'Completed in sidebar' }),
        idempotencyKey: expect.stringMatching(/^task-archive-/),
      }),
    }));
  });
});
