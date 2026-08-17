import { Activity, Bot, ChevronUp, ClipboardCheck, TerminalSquare, X } from 'lucide-react';
import {
  useEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from 'react';

import type { AssistantSessionState } from '../../assistant/assistantTypes';
import { useProductShellStore } from '../state/productShellStore';

const tabs = [
  { id: 'activity', label: 'Aktivite', icon: Activity },
  { id: 'agents', label: 'Ajan Çalışması', icon: Bot },
  { id: 'terminal', label: 'Terminal', icon: TerminalSquare },
  { id: 'logs', label: 'Loglar', icon: ChevronUp },
  { id: 'evidence', label: 'Evidence', icon: ClipboardCheck },
] as const;

export function BottomDock({ state, onOpenTerminal }: { state: AssistantSessionState; onOpenTerminal: () => void }) {
  const setDockOpen = useProductShellStore((shellState) => shellState.setDockOpen);
  const height = useProductShellStore((shellState) => shellState.dockHeight);
  const setHeight = useProductShellStore((shellState) => shellState.setDockHeight);
  const [activeTab, setActiveTab] = useState<(typeof tabs)[number]['id']>('activity');
  const completedTurns = state.turns.filter((turn) => turn.status === 'completed').length;
  const timeline = state.turns.flatMap((turn) => turn.assistantMessage.timeline);
  const runRefs = Array.from(new Map(
    state.turns.flatMap((turn) => turn.assistantMessage.referencedRuns).map((run) => [run.id, run]),
  ).values());
  const cleanupResize = useRef<() => void>(() => undefined);
  useEffect(() => () => cleanupResize.current(), []);
  const resize = (event: ReactPointerEvent<HTMLDivElement>) => {
    const startY = event.clientY;
    const startHeight = height;
    const move = (moveEvent: PointerEvent) => setHeight(Math.min(520, Math.max(140, startHeight + startY - moveEvent.clientY)));
    const end = () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', end);
      window.removeEventListener('pointercancel', end);
    };
    cleanupResize.current();
    cleanupResize.current = end;
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', end);
    window.addEventListener('pointercancel', end);
  };
  const resizeWithKeyboard = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    const step = event.shiftKey ? 40 : 10;
    if (event.key === 'ArrowUp') setHeight(height + step);
    else if (event.key === 'ArrowDown') setHeight(height - step);
    else if (event.key === 'Home') setHeight(140);
    else if (event.key === 'End') setHeight(520);
    else return;
    event.preventDefault();
  };

  return (
    <section className="bottom-dock" style={{ height }} aria-label="Activity and evidence">
      <div
        className="dock-resize"
        role="separator"
        tabIndex={0}
        aria-label="Dock height"
        aria-orientation="horizontal"
        aria-valuemin={140}
        aria-valuemax={520}
        aria-valuenow={height}
        onPointerDown={resize}
        onKeyDown={resizeWithKeyboard}
      />
      <header>
        <div className="dock-tabs">
          {tabs.map(({ id, label, icon: TabIcon }) => (
            <button
              type="button"
              key={id}
              className={id === activeTab ? 'is-active' : ''}
              onClick={() => {
                setActiveTab(id);
                if (id === 'terminal') onOpenTerminal();
              }}
            >
              <TabIcon size={15} /> {label}
            </button>
          ))}
        </div>
        <button type="button" className="icon-button" onClick={() => setDockOpen(false)} title="Dock'u kapat"><X size={17} /></button>
      </header>
      {activeTab === 'activity' ? <div className="activity-view">
          <div><i className="accent" /><span>{state.status === 'idle' ? 'No active run' : `Assistant ${state.status.replace('_', ' ')}`}</span></div>
          <div><i /><span>{state.turns.length} recorded turn{state.turns.length === 1 ? '' : 's'} · {completedTurns} complete</span></div>
          <div><i /><span>{state.referencedArtifacts.length} artifact reference{state.referencedArtifacts.length === 1 ? '' : 's'}</span></div>
          <div><i /><span>{runRefs.length} governed run reference{runRefs.length === 1 ? '' : 's'} · {timeline.length} timeline item{timeline.length === 1 ? '' : 's'}</span></div>
          <div><i /><span>{state.pendingApprovalId ? `Approval pending: ${state.pendingApprovalId}` : 'No pending approval'}</span></div>
        </div> : null}
      {activeTab === 'agents' ? <div className="activity-view" role="region" aria-label="Governed run work">
          {runRefs.length
            ? runRefs.map((run) => <div key={run.id}><i className="accent" /><span>{run.id} · {run.status || run.summary || 'Governed run'}</span></div>)
            : <div><i /><span>No governed agent or run references</span></div>}
        </div> : null}
      {activeTab === 'terminal' ? <div className="activity-view" role="region" aria-label="Governed terminal attachment">
          <div><i className="accent" /><span>This dock is attached to the active workspace terminal; reopening focuses the same live PTY session.</span></div>
        </div> : null}
      {activeTab === 'logs' ? <div className="activity-view" role="region" aria-label="Assistant timeline logs">
          {timeline.length
            ? timeline.map((item) => <div key={item.id}><i className={item.tone === 'success' ? 'accent' : ''} /><span>{item.title} · {item.subtitle}</span></div>)
            : <div><i /><span>No assistant timeline events</span></div>}
        </div> : null}
      {activeTab === 'evidence' ? <div className="activity-view" role="region" aria-label="Governed evidence">
          {state.referencedArtifacts.map((artifact) => <div key={`${artifact.artifactId}:${artifact.revisionId}`}><i className="accent" /><span>{artifact.name} · {artifact.artifactId || 'reference pending'}</span></div>)}
          <div><i /><span>{state.pendingApprovalId ? `Approval evidence pending: ${state.pendingApprovalId}` : 'No pending approval evidence'}</span></div>
        </div> : null}
    </section>
  );
}
