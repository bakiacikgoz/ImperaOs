import {
  ChevronDown,
  CircleDot,
  FileText,
  GitBranch,
  GitPullRequest,
  Laptop,
  Plus,
  SquarePlus,
  Terminal,
} from 'lucide-react';

import type { AssistantSessionState } from '../../assistant/assistantTypes';
import { useProductShellStore, type ProductTask } from '../state/productShellStore';

function unique(values: string[]): string[] {
  return [...new Set(values.filter(Boolean))];
}

export function ContextRail({ task, state }: { task?: ProductTask; state: AssistantSessionState }) {
  const setContextRailOpen = useProductShellStore((shellState) => shellState.setContextRailOpen);
  const runs = unique(state.turns.flatMap((turn) => turn.assistantMessage.referencedRuns.map((run) => run.id)));
  const attachments = unique(state.turns.flatMap((turn) => turn.composerControls?.contextAttachmentKinds ?? []));
  const toolIntents = unique(state.turns.flatMap((turn) => turn.composerControls?.toolIntents ?? []));

  return (
    <aside className="context-rail reference-environment-rail" aria-label="Task context">
      <header>
        <span>Ortam</span>
        <button type="button" className="icon-button" title="Paneli kapat" onClick={() => setContextRailOpen(false)}>
          <Plus size={20} />
        </button>
      </header>
      <div className="environment-rows">
        <div className="environment-row"><SquarePlus size={18} /><span>{task?.title ?? 'No task selected'}</span></div>
        <div className="environment-row"><Laptop size={18} /><span>{state.sessionId || 'Not started'}</span><ChevronDown size={18} /></div>
        <div className="environment-row"><GitBranch size={18} /><span>{task?.status ?? '—'}</span><ChevronDown size={18} /></div>
        <div className="environment-row"><CircleDot size={18} /><span>{state.status.replace('_', ' ')}</span></div>
        <div className="environment-row is-muted"><GitPullRequest size={18} /><span>{state.pendingApprovalId ? `Approval ${state.pendingApprovalId}` : 'No pending approval'}</span></div>
      </div>
      <section className="environment-section">
        <h2>Arka plan işlemleri</h2>
        {runs.length ? runs.map((runId) => <div className="background-job" key={runId}><Terminal size={18} /><span>{runId}</span></div>) : <p className="ps-muted">No governed run references yet.</p>}
        {state.pendingApprovalId ? <p><a href="#/approvals">Open approval {state.pendingApprovalId}</a></p> : null}
      </section>
      <section className="environment-section environment-sources">
        <header><h2>Kaynaklar</h2><Plus size={18} /></header>
        {attachments.map((item) => <div className="environment-source" key={`attachment:${item}`}><FileText size={18} /><span>attachment · {item}</span></div>)}
        {toolIntents.map((item) => <div className="environment-source" key={`intent:${item}`}><FileText size={18} /><span>safe intent · {item}</span></div>)}
        {!attachments.length && !toolIntents.length ? <p className="ps-muted">No explicit safe prompt controls recorded.</p> : null}
      </section>
      <button type="button" className="environment-row is-muted" disabled title="No governed branch context is available for this task.">Branch context unavailable</button>
    </aside>
  );
}
