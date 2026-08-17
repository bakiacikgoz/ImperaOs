import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export const DEFAULT_SIDEBAR_WIDTH = 260;
export const MIN_SIDEBAR_WIDTH = 220;
export const MAX_SIDEBAR_WIDTH = 340;

export function clampSidebarWidth(sidebarWidth: number): number {
  return Math.min(MAX_SIDEBAR_WIDTH, Math.max(MIN_SIDEBAR_WIDTH, sidebarWidth));
}

export function migrateProductShellPreferences(persistedState: unknown, _version: number): unknown {
  if (!persistedState || typeof persistedState !== 'object') return persistedState;
  const preferences = persistedState as Record<string, unknown>;
  const sidebarWidth = preferences.sidebarWidth;
  const hasValidSidebarWidth = typeof sidebarWidth === 'number'
    && Number.isFinite(sidebarWidth)
    && sidebarWidth >= MIN_SIDEBAR_WIDTH
    && sidebarWidth <= MAX_SIDEBAR_WIDTH;
  return {
    ...preferences,
    sidebarWidth: hasValidSidebarWidth ? sidebarWidth : DEFAULT_SIDEBAR_WIDTH,
  };
}

export type ProductTask = {
  id: string;
  projectId?: string;
  title: string;
  createdAt: string;
  updatedAt?: string;
  status: 'draft' | 'active' | 'awaiting_approval' | 'completed' | 'failed' | 'cancelled' | 'archived';
  priority?: number;
  pinned?: boolean;
  manualOrder?: number;
  archivedAt?: string | null;
  assistantSessionId?: string;
  reasoningEffort?: 'low' | 'medium' | 'high' | 'very_high';
  speedProfile?: 'standard' | 'fast';
  approvalProfile?: 'always_ask' | 'risk_based' | 'policy_automatic';
};

export type ProductProjectRoot = {
  projectId: string;
  rootRef: string;
  rootDisplayName: string;
};

type ProductShellState = {
  tasks: ProductTask[];
  projects: ProductProjectRoot[];
  selectedTaskId: string | null;
  contextRailOpen: boolean;
  dockOpen: boolean;
  dockHeight: number;
  sidebarCollapsed: boolean;
  sidebarWidth: number;
  theme: 'dark' | 'light';
  searchOpen: boolean;
  upsertTasks: (tasks: ProductTask[]) => void;
  upsertProjects: (projects: ProductProjectRoot[]) => void;
  selectTask: (taskId: string | null) => void;
  setContextRailOpen: (open: boolean) => void;
  setDockOpen: (open: boolean) => void;
  setDockHeight: (height: number) => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  setSidebarWidth: (width: number) => void;
  setTheme: (theme: 'dark' | 'light') => void;
  setSearchOpen: (open: boolean) => void;
};

/** UI-only navigation state. Product records are deliberately not fabricated here. */
export const useProductShellStore = create<ProductShellState>()(persist((set) => ({
  tasks: [],
  projects: [],
  selectedTaskId: null,
  contextRailOpen: false,
  dockOpen: false,
  dockHeight: 240,
  sidebarCollapsed: true,
  sidebarWidth: DEFAULT_SIDEBAR_WIDTH,
  theme: 'dark',
  searchOpen: false,
  upsertTasks: (tasks) => set((state) => {
    const next = new Map(state.tasks.map((task) => [task.id, task]));
    tasks.forEach((task) => next.set(task.id, task));
    const selectedTaskArchived = tasks.some((task) => task.id === state.selectedTaskId && task.status === 'archived');
    return {
      tasks: [...next.values()].sort((left, right) => Number(right.pinned) - Number(left.pinned)
        || (left.manualOrder ?? 0) - (right.manualOrder ?? 0)
        || (right.priority ?? 0) - (left.priority ?? 0)
        || (right.updatedAt ?? right.createdAt).localeCompare(left.updatedAt ?? left.createdAt)),
      ...(selectedTaskArchived ? { selectedTaskId: null } : {}),
    };
  }),
  upsertProjects: (projects) => set((state) => {
    const next = new Map(state.projects.map((project) => [project.projectId, project]));
    projects.forEach((project) => next.set(project.projectId, project));
    return { projects: [...next.values()] };
  }),
  selectTask: (selectedTaskId) => set({ selectedTaskId }),
  setContextRailOpen: (contextRailOpen) => set({ contextRailOpen }),
  setDockOpen: (dockOpen) => set({ dockOpen }),
  setDockHeight: (dockHeight) => set({ dockHeight: Math.min(520, Math.max(140, dockHeight)) }),
  setSidebarCollapsed: (sidebarCollapsed) => set({ sidebarCollapsed }),
  setSidebarWidth: (sidebarWidth) => set({ sidebarWidth: clampSidebarWidth(sidebarWidth) }),
  setTheme: (theme) => set({ theme }),
  setSearchOpen: (searchOpen) => set({ searchOpen }),
}), {
  name: 'imperaos-product-shell-preferences-v2',
  version: 3,
  migrate: (persistedState, version) => migrateProductShellPreferences(persistedState, version) as ProductShellState,
  // Tasks and conversations remain owned by the future Product Workspace domain,
  // never by this UI preference store.
  partialize: (state) => ({
    contextRailOpen: state.contextRailOpen,
    dockOpen: state.dockOpen,
    dockHeight: state.dockHeight,
    sidebarCollapsed: state.sidebarCollapsed,
    sidebarWidth: state.sidebarWidth,
    theme: state.theme,
  }),
}));
