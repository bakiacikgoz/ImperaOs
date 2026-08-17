import { screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const bridge = vi.hoisted(() => ({
  fetchControlPlaneSnapshot: vi.fn(),
  tailEvents: vi.fn(),
}));
const workspace = vi.hoisted(() => ({ listLinks: vi.fn() }));

vi.mock('../../bridge', () => bridge);
vi.mock('../adapters/productWorkspaceClient', () => ({ productWorkspaceClient: workspace }));

import { renderOperatorPanel } from '../../test/render';
import { DataExplorerSurface } from './DataExplorerSurface';

describe('DataExplorerSurface', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    workspace.listLinks.mockResolvedValue({
      links: [
        { linkId: 'link-run', taskId: 'task-1', targetType: 'run', targetId: 'run-17' },
        { linkId: 'link-artifact', taskId: 'task-1', targetType: 'artifact', targetId: 'artifact-release' },
      ],
    });
    bridge.fetchControlPlaneSnapshot.mockResolvedValue({
      generatedAtUtc: '2026-07-29T12:00:00Z',
      dataSource: { mode: 'native_bridge', sourceReason: 'governed control-plane snapshot' },
      runs: [{ runId: 'run-17' }],
      approvals: [{ approvalId: 'approval-1' }],
      evidencePacks: [{ evidencePackId: 'evidence-1' }],
      logs: [{ eventId: 'log-1', level: 'info', message: 'Runtime ready', timestampUtc: '2026-07-29T12:00:00Z' }],
      alerts: [],
      agents: [{ agentId: 'agent-1' }],
    });
    bridge.tailEvents.mockResolvedValue({
      contractVersion: 'events/v1',
      events: [{ event_type: 'task.completed', message: 'Run completed', timestamp_utc: '2026-07-29T12:01:00Z' }],
      nextCursor: 1,
      reset: false,
      truncated: false,
      badLineCount: 0,
    });
  });

  it('projects real task links, control-plane counts, logs, and bounded run events', async () => {
    renderOperatorPanel(<DataExplorerSurface taskId="task-1" />);

    expect(await screen.findByText('Run completed')).toBeInTheDocument();
    expect(screen.getAllByText('run-17')).toHaveLength(2);
    expect(screen.getByText('Runtime ready')).toBeInTheDocument();
    expect(screen.getByText('1 linked artifact')).toBeInTheDocument();
    expect(workspace.listLinks).toHaveBeenCalledWith('task-1');
    expect(bridge.tailEvents).toHaveBeenCalledWith(expect.anything(), 'run-17', 0, 64 * 1024, 100);
  });

  it('reports partial source failures while preserving successful governed data', async () => {
    workspace.listLinks.mockRejectedValue(new Error('Task links unavailable'));

    renderOperatorPanel(<DataExplorerSurface taskId="task-1" />);

    expect(await screen.findByText('Runtime ready')).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('Task links unavailable');
  });
});
