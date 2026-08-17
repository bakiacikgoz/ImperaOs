export type WorkspaceTabKind = 'artifacts' | 'terminal' | 'browser' | 'preview' | 'data' | 'files';
export type WorkspaceTab = {
  id: string;
  kind: WorkspaceTabKind;
  title: string;
  artifactId?: string;
  nativeSessionLabel?: string;
};

const labels: Record<WorkspaceTabKind, string> = {
  artifacts: 'Artifacts',
  terminal: 'Terminal',
  browser: 'Browser',
  preview: 'Preview',
  data: 'Data',
  files: 'Files',
};

type WorkspaceTabStorage = Pick<Storage, 'getItem' | 'setItem'> | Map<string, string>;

function workspaceStorageKey(taskId: string): string {
  return `imperaos.workspace-tabs.${encodeURIComponent(taskId)}`;
}

function storageGet(storage: WorkspaceTabStorage, key: string): string | null {
  return storage instanceof Map ? storage.get(key) ?? null : storage.getItem(key);
}

function storageSet(storage: WorkspaceTabStorage, key: string, value: string): void {
  if (storage instanceof Map) storage.set(key, value);
  else storage.setItem(key, value);
}

function isWorkspaceTabKind(value: unknown): value is WorkspaceTabKind {
  return value === 'artifacts'
    || value === 'terminal'
    || value === 'browser'
    || value === 'preview'
    || value === 'data'
    || value === 'files';
}

export function createWorkspaceTab(kind: WorkspaceTabKind, artifactId?: string): WorkspaceTab {
  const id = `${kind}-${globalThis.crypto?.randomUUID?.() ?? `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`}`;
  return { id, kind, title: labels[kind], ...(kind === 'artifacts' && artifactId ? { artifactId } : {}) };
}

export function saveWorkspaceTabSnapshot(
  storage: WorkspaceTabStorage,
  taskId: string,
  tabs: WorkspaceTab[],
  activeTabId: string | null,
): void {
  try {
    storageSet(storage, workspaceStorageKey(taskId), JSON.stringify({
      tabs: tabs.map(({ id, kind, title, artifactId }) => ({
        id,
        kind,
        title,
        ...(artifactId ? { artifactId } : {}),
      })),
      activeTabId,
    }));
  } catch {
    // Workspace persistence is a convenience boundary; runtime surfaces
    // remain usable when browser storage is denied or exhausted.
  }
}

export function loadWorkspaceTabSnapshot(
  storage: WorkspaceTabStorage,
  taskId: string,
): { tabs: WorkspaceTab[]; activeTabId: string | null } {
  try {
    const raw = storageGet(storage, workspaceStorageKey(taskId));
    if (!raw) return { tabs: [], activeTabId: null };
    const parsed = JSON.parse(raw) as unknown;
    if (typeof parsed !== 'object' || parsed === null) throw new Error('invalid snapshot');
    const record = parsed as Record<string, unknown>;
    if (!Array.isArray(record.tabs)) throw new Error('invalid tabs');
    const ids = new Set<string>();
    const tabs = record.tabs.map((value) => {
      if (typeof value !== 'object' || value === null) throw new Error('invalid tab');
      const tab = value as Record<string, unknown>;
      if (typeof tab.id !== 'string' || !tab.id || ids.has(tab.id)
        || !isWorkspaceTabKind(tab.kind) || typeof tab.title !== 'string' || !tab.title) {
        throw new Error('invalid tab');
      }
      if (tab.artifactId !== undefined && typeof tab.artifactId !== 'string') {
        throw new Error('invalid artifact');
      }
      ids.add(tab.id);
      return {
        id: tab.id,
        kind: tab.kind,
        title: tab.title,
        ...(typeof tab.artifactId === 'string' ? { artifactId: tab.artifactId } : {}),
      };
    });
    const activeTabId = typeof record.activeTabId === 'string' && ids.has(record.activeTabId)
      ? record.activeTabId
      : tabs[0]?.id ?? null;
    return { tabs, activeTabId };
  } catch {
    return { tabs: [], activeTabId: null };
  }
}
