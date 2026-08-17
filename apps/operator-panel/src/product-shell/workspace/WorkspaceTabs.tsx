import { Database, FileText, FolderTree, Globe2, MonitorPlay, Plus, TerminalSquare, X } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import type { AssistantSessionState } from '../../assistant/assistantTypes';
import { BrowserSurface } from '../browser/BrowserSurface';
import { PreviewSurface } from '../browser/PreviewSurface';
import { TerminalSurface } from '../terminal/TerminalSurface';
import { ProductArtifactWorkspace } from './ProductArtifactWorkspace';
import { DataExplorerSurface } from './DataExplorerSurface';
import { FilesNavigatorSurface } from './FilesNavigatorSurface';
import type { WorkspaceTab } from './workspaceTabState';

const tabIcons = {
  artifacts: FileText,
  terminal: TerminalSquare,
  browser: Globe2,
  preview: MonitorPlay,
  data: Database,
  files: FolderTree,
} as const;

const workspaceActions = [
  { kind: 'artifacts', label: 'Artifacts', shortcut: '⌘P', icon: FileText },
  { kind: 'terminal', label: 'Terminal', shortcut: '⌘T', icon: TerminalSquare },
  { kind: 'browser', label: 'Browser', shortcut: '⌘⇧B', icon: Globe2 },
  { kind: 'preview', label: 'Preview', shortcut: '⌃⇧G', icon: MonitorPlay },
  { kind: 'data', label: 'Data', shortcut: '⌘⇧D', icon: Database },
  { kind: 'files', label: 'Files', shortcut: '⌘⇧F', icon: FolderTree },
] as const;

export function WorkspaceTabs({
  tabs,
  activeTabId,
  assistantState,
  taskId,
  projectRootRef,
  projectRootDisplayName,
  onActivate,
  onClose,
  onUpdate,
  onOpen,
}: {
  tabs: WorkspaceTab[];
  activeTabId: string | null;
  assistantState: AssistantSessionState;
  taskId: string;
  projectRootRef?: string;
  projectRootDisplayName?: string;
  onActivate: (tabId: string) => void;
  onClose: (tabId: string) => void;
  onUpdate: (tabId: string, changes: Partial<WorkspaceTab>) => void;
  onOpen: (kind: WorkspaceTab['kind'], artifactId?: string) => void;
}) {
  const [addMenuOpen, setAddMenuOpen] = useState(false);
  const addMenuRef = useRef<HTMLDivElement>(null);
  const active = tabs.find((tab) => tab.id === activeTabId) ?? tabs[0] ?? null;
  useEffect(() => {
    if (!addMenuOpen) return;
    const closeOnOutside = (event: MouseEvent) => {
      if (!addMenuRef.current?.contains(event.target as Node)) setAddMenuOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setAddMenuOpen(false);
    };
    document.addEventListener('mousedown', closeOnOutside);
    document.addEventListener('keydown', closeOnEscape);
    return () => {
      document.removeEventListener('mousedown', closeOnOutside);
      document.removeEventListener('keydown', closeOnEscape);
    };
  }, [addMenuOpen]);

  return (
    <section className={`workspace-tabs${active ? '' : ' workspace-tabs-empty ps-workspace-tabs'}`} aria-label="Workspace tabs">
      <header className="workspace-tab-strip">
        <div className="workspace-tab-list">
          <div className="workspace-tab-scroll" role="tablist" aria-label="Workspace surfaces">
            {tabs.map((tab) => {
              const TabIcon = tabIcons[tab.kind];
              const isActive = tab.id === active?.id;
              return (
                <div className="workspace-tab-item" key={tab.id}>
                  <button
                    type="button"
                    role="tab"
                    aria-selected={isActive}
                    className={`workspace-tab${isActive ? ' is-active' : ''}`}
                    onClick={() => onActivate(tab.id)}
                  >
                    <TabIcon size={14} />
                    <span>{tab.title}</span>
                  </button>
                  <button
                    type="button"
                    className="workspace-tab-close"
                    aria-label={`Close ${tab.title}`}
                    onClick={() => onClose(tab.id)}
                  >
                    <X size={13} />
                  </button>
                </div>
              );
            })}
          </div>
          <div className="workspace-add-wrap" ref={addMenuRef}>
            <button
              type="button"
              className="workspace-add-button"
              aria-label="New workspace tab"
              aria-expanded={addMenuOpen}
              aria-haspopup="menu"
              onClick={() => setAddMenuOpen((open) => !open)}
            >
              <Plus size={16} />
            </button>
            {addMenuOpen ? (
              <div className="workspace-add-menu" role="menu" aria-label="New workspace surface">
                {workspaceActions.map(({ kind, label, shortcut, icon: ActionIcon }) => (
                  <button
                    type="button"
                    role="menuitem"
                    key={kind}
                    onClick={() => {
                      onOpen(kind);
                      setAddMenuOpen(false);
                    }}
                  >
                    <ActionIcon size={15} />
                    <span>{label}</span>
                    <kbd>{shortcut}</kbd>
                  </button>
                ))}
              </div>
            ) : null}
          </div>
        </div>
      </header>
      {active ? <div className="surface-content" role="tabpanel">
        {tabs.map((tab) => {
          const isActive = tab.id === active?.id;
          return (
            <div className="workspace-runtime-surface" key={tab.id} hidden={!isActive} aria-hidden={!isActive}>
              {tab.kind === 'artifacts' ? <ProductArtifactWorkspace state={assistantState} openRequest={1} requestedArtifactId={tab.artifactId} /> : null}
              {tab.kind === 'terminal' ? <TerminalSurface active={isActive} onClose={() => onClose(tab.id)} projectRootRef={projectRootRef} projectRootDisplayName={projectRootDisplayName} /> : null}
              {tab.kind === 'browser' ? <BrowserSurface active={isActive} onClose={() => onClose(tab.id)} sessionLabel={tab.nativeSessionLabel} onSessionChange={(nativeSessionLabel) => onUpdate(tab.id, { nativeSessionLabel: nativeSessionLabel ?? undefined })} /> : null}
              {tab.kind === 'preview' ? <PreviewSurface taskId={taskId} active={isActive} onClose={() => onClose(tab.id)} sessionLabel={tab.nativeSessionLabel} onSessionChange={(nativeSessionLabel) => onUpdate(tab.id, { nativeSessionLabel: nativeSessionLabel ?? undefined })} /> : null}
              {tab.kind === 'data' ? <DataExplorerSurface taskId={taskId} /> : null}
              {tab.kind === 'files' ? <FilesNavigatorSurface onOpenArtifact={(artifactId) => onOpen('artifacts', artifactId)} /> : null}
            </div>
          );
        })}
      </div> : <p className="ps-muted">Open an artifact or runtime surface to create a governed workspace tab.</p>}
    </section>
  );
}
