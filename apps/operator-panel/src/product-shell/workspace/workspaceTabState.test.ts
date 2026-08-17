import { describe, expect, it } from 'vitest';

import {
  createWorkspaceTab,
  loadWorkspaceTabSnapshot,
  saveWorkspaceTabSnapshot,
} from './workspaceTabState';

describe('workspace tab persistence', () => {
  it('restores task-scoped tab focus without trusting stale native session labels', () => {
    const storage = new Map<string, string>();
    const browser = {
      ...createWorkspaceTab('browser'),
      nativeSessionLabel: 'stale-native-session',
    };
    const terminal = createWorkspaceTab('terminal');

    saveWorkspaceTabSnapshot(storage, 'task-1', [browser, terminal], terminal.id);
    const restored = loadWorkspaceTabSnapshot(storage, 'task-1');

    expect(restored.tabs).toEqual([
      { id: browser.id, kind: 'browser', title: 'Browser' },
      { id: terminal.id, kind: 'terminal', title: 'Terminal' },
    ]);
    expect(restored.activeTabId).toBe(terminal.id);
  });

  it('fails closed when persisted workspace data is malformed', () => {
    const storage = new Map<string, string>([
      ['imperaos.workspace-tabs.task-1', '{"tabs":[{"kind":"unknown"}]}'],
    ]);

    expect(loadWorkspaceTabSnapshot(storage, 'task-1')).toEqual({
      tabs: [],
      activeTabId: null,
    });
  });

  it('recovers the first valid tab when a persisted active id is stale', () => {
    const storage = new Map<string, string>();
    const terminal = createWorkspaceTab('terminal');

    saveWorkspaceTabSnapshot(storage, 'task-stale-active', [terminal], 'removed-tab');

    expect(loadWorkspaceTabSnapshot(storage, 'task-stale-active')).toEqual({
      tabs: [terminal],
      activeTabId: terminal.id,
    });
  });

  it('persists the governed files and data explorer surfaces', () => {
    const storage = new Map<string, string>();
    const files = createWorkspaceTab('files');
    const data = createWorkspaceTab('data');

    saveWorkspaceTabSnapshot(storage, 'task-data', [files, data], data.id);

    expect(loadWorkspaceTabSnapshot(storage, 'task-data')).toEqual({
      tabs: [files, data],
      activeTabId: data.id,
    });
  });
});
