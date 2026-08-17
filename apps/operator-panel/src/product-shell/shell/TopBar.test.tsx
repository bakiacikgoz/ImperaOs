import { screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it } from 'vitest';

import { renderOperatorPanel } from '../../test/render';
import { useProductShellStore } from '../state/productShellStore';
import { TopBar } from './TopBar';

describe('TopBar capability truth', () => {
  beforeEach(() => {
    useProductShellStore.setState({
      tasks: [],
      sidebarCollapsed: true,
      contextRailOpen: false,
      dockOpen: false,
    });
  });

  it('does not expose dock or context controls as buttons without a task context', () => {
    const { container } = renderOperatorPanel(
      <MemoryRouter initialEntries={['/']}>
        <TopBar />
      </MemoryRouter>,
    );

    expect(screen.queryByRole('button', { name: 'Utility dock' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Bağlam paneli' })).not.toBeInTheDocument();
    expect(container.querySelectorAll('[data-disabled-reason="TASK_CONTEXT_REQUIRED"]')).toHaveLength(2);
  });

  it('exposes functional dock and context controls for a durable task route', async () => {
    useProductShellStore.setState({
      tasks: [{
        id: 'task-1',
        title: 'Release',
        createdAt: '2026-07-25T12:00:00Z',
        status: 'active',
      }],
    });
    const { user } = renderOperatorPanel(
      <MemoryRouter initialEntries={['/task/task-1']}>
        <Routes>
          <Route path="/task/:taskId" element={<TopBar />} />
        </Routes>
      </MemoryRouter>,
    );

    await user.click(screen.getByTitle('Utility dock'));
    await user.click(screen.getByTitle('Bağlam paneli'));

    expect(useProductShellStore.getState().dockOpen).toBe(true);
    expect(useProductShellStore.getState().contextRailOpen).toBe(true);
  });
});
