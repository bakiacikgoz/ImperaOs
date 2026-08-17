import { fireEvent, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const navigate = vi.hoisted(() => vi.fn());
const workspace = vi.hoisted(() => ({ listProjects: vi.fn(), listTasks: vi.fn() }));
const artifactBridge = vi.hoisted(() => ({ list: vi.fn() }));
const bridge = vi.hoisted(() => ({ fetchApprovals: vi.fn(), listControlPlaneAgents: vi.fn() }));

vi.mock('../adapters/productWorkspaceClient', () => ({ productWorkspaceClient: workspace }));
vi.mock('../../artifact-workspace/artifactBridge', () => ({ artifactBridge }));
vi.mock('../../bridge', () => bridge);
vi.mock('react-router-dom', async (importOriginal) => ({
  ...(await importOriginal<typeof import('react-router-dom')>()),
  useNavigate: () => navigate,
}));

import { renderOperatorPanel } from '../../test/render';
import { GlobalSearch } from './GlobalSearch';

describe('GlobalSearch', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    workspace.listProjects.mockResolvedValue({ projects: [{
      projectId: 'project-1', workspaceId: 'workspace-1', title: 'Release', status: 'active',
      createdAtUtc: '2026-07-24T12:00:00Z', updatedAtUtc: '2026-07-24T12:00:00Z',
    }] });
    workspace.listTasks.mockResolvedValue({ tasks: [{
      taskId: 'task-1', workspaceId: 'workspace-1', projectId: 'project-1', title: 'Quarterly release plan', status: 'active',
      assistantSessionId: null, assistantTurnId: null, teamJobId: null, createdAtUtc: '2026-07-24T12:00:00Z', updatedAtUtc: '2026-07-24T12:00:00Z',
    }] });
    artifactBridge.list.mockResolvedValue({ items: [], nextCursor: null });
    bridge.fetchApprovals.mockResolvedValue({ pending: [] });
    bridge.listControlPlaneAgents.mockResolvedValue({ agents: [] });
  });

  it('opens a matching durable task route', async () => {
    const { user } = renderOperatorPanel(<MemoryRouter><GlobalSearch /></MemoryRouter>);

    fireEvent.keyDown(window, { key: 'k', metaKey: true });
    await user.type(screen.getByRole('textbox', { name: 'Search' }), 'quarterly');
    expect(document.querySelector('.modal-backdrop .search-modal')).not.toBeNull();
    const result = await screen.findByRole('button', { name: /Quarterly release plan/ });
    await user.click(result);

    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/task/task-1'));
  });

  it('focuses global search through the centralized platform shortcut', () => {
    renderOperatorPanel(<MemoryRouter><GlobalSearch /></MemoryRouter>);

    fireEvent.keyDown(window, { key: 'k', metaKey: true });

    const search = screen.getByRole('textbox', { name: 'Search' });
    expect(search).toHaveFocus();
  });

  it('reports an unavailable search instead of a normal empty result when every bridge fails', async () => {
    workspace.listProjects.mockRejectedValue(new Error('workspace offline'));
    artifactBridge.list.mockRejectedValue(new Error('artifact offline'));
    bridge.fetchApprovals.mockRejectedValue(new Error('approvals offline'));
    bridge.listControlPlaneAgents.mockRejectedValue(new Error('agents offline'));
    renderOperatorPanel(<MemoryRouter><GlobalSearch /></MemoryRouter>);

    fireEvent.keyDown(window, { key: 'k', metaKey: true });

    expect(await screen.findByText(/Arama kaynakları kullanılamıyor: çalışma alanı, artifact, onay, ajan/)).toBeInTheDocument();
    expect(screen.queryByText('Yönetilen sonuç bulunamadı.')).not.toBeInTheDocument();
  });

  it('keeps available results and identifies missing sources during a partial bridge failure', async () => {
    workspace.listProjects.mockRejectedValue(new Error('workspace offline'));
    artifactBridge.list.mockResolvedValue({
      items: [{ artifactId: 'artifact-design', title: 'Design system', kind: 'document', status: 'ready' }],
      nextCursor: null,
    });
    const { user } = renderOperatorPanel(<MemoryRouter><GlobalSearch /></MemoryRouter>);

    fireEvent.keyDown(window, { key: 'k', metaKey: true });
    expect(await screen.findByText(/Kısmi arama · kullanılamayan kaynaklar: çalışma alanı/)).toBeInTheDocument();
    await user.type(screen.getByRole('textbox', { name: 'Search' }), 'design');
    expect(await screen.findByRole('button', { name: /Design system/ })).toBeInTheDocument();
  });
});
