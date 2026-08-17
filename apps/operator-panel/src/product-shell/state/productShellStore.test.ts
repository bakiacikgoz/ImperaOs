import { beforeEach, describe, expect, it } from 'vitest';

import {
  migrateProductShellPreferences,
  useProductShellStore,
} from './productShellStore';

describe('product shell sidebar preferences', () => {
  beforeEach(() => {
    localStorage.clear();
    useProductShellStore.setState(useProductShellStore.getInitialState(), true);
  });

  it('starts at the approved 260px sidebar proportion', () => {
    expect(useProductShellStore.getState().sidebarWidth).toBe(260);
  });

  it('keeps live resizing inside the usable 220px to 340px range', () => {
    useProductShellStore.getState().setSidebarWidth(180);
    expect(useProductShellStore.getState().sidebarWidth).toBe(220);

    useProductShellStore.getState().setSidebarWidth(380);
    expect(useProductShellStore.getState().sidebarWidth).toBe(340);
  });

  it('preserves valid persisted widths and resets oversized legacy widths', () => {
    expect(migrateProductShellPreferences({ sidebarWidth: 286, theme: 'dark' }, 2)).toEqual({
      sidebarWidth: 286,
      theme: 'dark',
    });
    expect(migrateProductShellPreferences({ sidebarWidth: 414, theme: 'dark' }, 2)).toEqual({
      sidebarWidth: 260,
      theme: 'dark',
    });
  });
});

describe('product shell task lifecycle', () => {
  beforeEach(() => {
    localStorage.clear();
    useProductShellStore.setState(useProductShellStore.getInitialState(), true);
  });

  it('retains an archived task record while clearing its active selection', () => {
    const activeTask = {
      id: 'task-release',
      title: 'Prepare release',
      createdAt: '2026-07-24T12:00:00Z',
      status: 'active' as const,
    };
    useProductShellStore.setState({ tasks: [activeTask], selectedTaskId: activeTask.id });

    useProductShellStore.getState().upsertTasks([{
      ...activeTask,
      status: 'archived',
      archivedAt: '2026-08-07T07:00:00Z',
    }]);

    expect(useProductShellStore.getState().tasks).toEqual([expect.objectContaining({
      id: activeTask.id,
      status: 'archived',
      archivedAt: '2026-08-07T07:00:00Z',
    })]);
    expect(useProductShellStore.getState().selectedTaskId).toBeNull();
  });
});
