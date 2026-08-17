import { ArrowUpRight, Bot, FileText, RefreshCw, ShieldCheck } from 'lucide-react';
import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { useSearchParams } from 'react-router-dom';

import { artifactBridge } from '../../artifact-workspace/artifactBridge';
import { AgentRegistryView } from '../../components/control-plane/AgentRegistryView';
import { decideApproval, fetchApprovals, listControlPlaneAgents, showApproval } from '../../bridge';
import { loadSettings } from '../../settings';

type ApprovalRow = { approvalId: string; targetKind: string; status: string };

function record(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null ? value as Record<string, unknown> : {};
}

function detailText(value: unknown, fallback = '—'): string {
  if (typeof value === 'string' && value) return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  return fallback;
}

function DetailGrid({ rows, empty }: { rows: Array<[string, unknown]>; empty: string }) {
  const visible = rows.filter(([, value]) => value !== undefined && value !== null && value !== '');
  if (!visible.length) return <p className="ps-muted">{empty}</p>;
  return (
    <dl className="collection-detail-grid">
      {visible.map(([label, value]) => (
        <div key={label}><dt>{label}</dt><dd>{detailText(value)}</dd></div>
      ))}
    </dl>
  );
}

function pendingApprovals(value: unknown): ApprovalRow[] {
  const pending = record(value).pending;
  if (!Array.isArray(pending)) return [];
  return pending.flatMap((item) => {
    const row = record(item);
    const approvalId = typeof row.approval_id === 'string' ? row.approval_id : '';
    return approvalId ? [{
      approvalId,
      targetKind: typeof row.target_kind === 'string' ? row.target_kind : 'governed action',
      status: typeof row.status === 'string' ? row.status : 'pending',
    }] : [];
  });
}

function CollectionFrame({
  icon: CollectionIcon,
  eyebrow,
  title,
  description,
  onRefresh,
  error,
  className = '',
  children,
}: {
  icon: typeof FileText;
  eyebrow: string;
  title: string;
  description: string;
  onRefresh: () => void;
  error: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <main className={`collection-page ${className}`.trim()}>
      <header>
        <span className="collection-icon"><CollectionIcon size={21} /></span>
        <p>{eyebrow}</p>
        <h1>{title}</h1>
        <span>{description}</span>
        <button type="button" className="collection-refresh" onClick={onRefresh}><RefreshCw size={15} />Refresh</button>
        {error ? <p className="collection-error" role="alert">{error}</p> : null}
      </header>
      {children}
    </main>
  );
}

export function LibraryPage() {
  const [searchParams] = useSearchParams();
  const [items, setItems] = useState<Array<{ artifactId: string; title: string; kind: string; status: string }>>([]);
  const [selectedArtifactId, setSelectedArtifactId] = useState<string | null>(null);
  const [detail, setDetail] = useState<unknown>(null);
  const [error, setError] = useState('');
  const load = useCallback(() => {
    setError('');
    void artifactBridge.list().then((result) => {
      const next = result.items.map((item) => ({
        artifactId: item.artifactId, title: item.title, kind: item.kind, status: item.status,
      }));
      setItems(next);
      setSelectedArtifactId((current) => next.some((item) => item.artifactId === current) ? current : next[0]?.artifactId ?? null);
    }).catch((cause) => setError(cause instanceof Error ? cause.message : 'Artifact library is unavailable.'));
  }, []);
  useEffect(load, [load]);
  useEffect(() => {
    const requestedArtifactId = searchParams.get('artifact');
    if (requestedArtifactId && items.some((item) => item.artifactId === requestedArtifactId)) {
      setSelectedArtifactId(requestedArtifactId);
    }
  }, [items, searchParams]);
  useEffect(() => {
    if (!selectedArtifactId) { setDetail(null); return; }
    void artifactBridge.get({ artifactId: selectedArtifactId }).then(setDetail)
      .catch((cause) => setError(cause instanceof Error ? cause.message : 'Artifact detail is unavailable.'));
  }, [selectedArtifactId]);

  return (
    <CollectionFrame
      icon={FileText}
      eyebrow="ARTIFACT KÜTÜPHANESİ"
      title="Çalışmaların, tek yerde."
      description="Görevlerde üretilen belgeler, tablolar ve sunumlar."
      onRefresh={load}
      error={error}
    >
      <section className="collection-list">
        {items.map((item) => (
          <button
            type="button"
            key={item.artifactId}
            className={selectedArtifactId === item.artifactId ? 'is-active' : ''}
            onClick={() => setSelectedArtifactId(item.artifactId)}
          >
            <span className="collection-row-icon"><FileText size={18} /></span>
            <div><strong>{item.title}</strong><small>{item.kind} · {item.status}</small></div>
            <em>{item.status}</em>
            <ArrowUpRight size={17} />
          </button>
        ))}
        {!items.length && !error ? <p className="collection-empty">No governed artifacts are available in this workspace.</p> : null}
      </section>
      <article className="collection-detail-panel">
        <h2>{selectedArtifactId ?? 'No artifact selected'}</h2>
        <DetailGrid
          empty="Select an artifact to inspect its canonical detail."
          rows={detail ? (() => {
            const value = record(detail);
            const artifact = record(value.artifact);
            const revision = record(value.revision);
            return [
              ['Title', artifact.title],
              ['Artifact ID', artifact.artifactId],
              ['Kind', artifact.kind],
              ['Status', artifact.status],
              ['Data class', artifact.dataClass],
              ['Revision', revision.revisionId],
              ['Revision number', revision.revisionNumber],
              ['Change summary', revision.changeSummary],
              ['Updated', artifact.updatedAtUtc],
            ] as Array<[string, unknown]>;
          })() : []}
        />
      </article>
    </CollectionFrame>
  );
}

export function ApprovalsPage() {
  const [searchParams] = useSearchParams();
  const [settings] = useState(() => loadSettings());
  const [rows, setRows] = useState<ApprovalRow[]>([]);
  const [selected, setSelected] = useState<ApprovalRow | null>(null);
  const [detail, setDetail] = useState<unknown>(null);
  const [error, setError] = useState('');
  const load = useCallback(() => {
    setError('');
    void fetchApprovals(settings).then((value) => {
      const next = pendingApprovals(value);
      setRows(next);
      const requestedApprovalId = searchParams.get('approval');
      setSelected((current) => next.find((item) => item.approvalId === requestedApprovalId)
        ?? next.find((item) => item.approvalId === current?.approvalId)
        ?? next[0] ?? null);
    }).catch((cause) => setError(cause instanceof Error ? cause.message : 'Approvals are unavailable.'));
  }, [searchParams, settings]);
  useEffect(load, [load]);
  useEffect(() => {
    if (!selected) { setDetail(null); return; }
    void showApproval(settings, selected.approvalId).then(setDetail)
      .catch((cause) => setError(cause instanceof Error ? cause.message : 'Approval detail is unavailable.'));
  }, [selected, settings]);
  const decide = async (approve: boolean) => {
    if (!selected || !settings.operatorId.trim()) return;
    if (!window.confirm(`${approve ? 'Approve' : 'Reject'} ${selected.approvalId}?`)) return;
    try {
      await decideApproval(settings, selected.approvalId, approve, settings.operatorId, 'product shell decision');
      load();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Approval decision failed.');
    }
  };
  const canDecide = Boolean(selected && settings.operatorId.trim());

  return (
    <CollectionFrame
      icon={ShieldCheck}
      eyebrow="GOVERNANCE"
      title="Onaylar"
      description="İnsan kararı gerektiren işlemleri gözden geçirin."
      onRefresh={load}
      error={error}
    >
      <section className="collection-list">
        {rows.map((row) => (
          <button type="button" key={row.approvalId} className={selected?.approvalId === row.approvalId ? 'is-active' : ''} onClick={() => setSelected(row)}>
            <span className="collection-row-icon"><ShieldCheck size={18} /></span>
            <div><strong>{row.approvalId}</strong><small>{row.targetKind}</small></div>
            <em>{row.status}</em>
            <ArrowUpRight size={17} />
          </button>
        ))}
        {!rows.length && !error ? <p className="collection-empty">No pending approvals.</p> : null}
      </section>
      <article className="collection-detail-panel">
        <h2>{selected?.approvalId ?? 'No approval selected'}</h2>
        <DetailGrid
          empty="Select an approval to inspect its governed detail."
          rows={detail ? (() => {
            const value = record(detail);
            const ticket = record(value.ticket);
            const snapshot = record(ticket.snapshot);
            return [
              ['Status', value.status ?? ticket.status],
              ['Execution', value.execution_status ?? ticket.execution_status],
              ['Run', ticket.run_id],
              ['Target kind', ticket.target_kind],
              ['Target', ticket.target_ref],
              ['Risk', snapshot.risk_class],
              ['Category', snapshot.category],
              ['Requested by', ticket.actor],
              ['Decision reason', ticket.decision_reason],
              ['Expires', ticket.expires_at],
              ['Policy hash', ticket.policy_hash],
            ] as Array<[string, unknown]>;
          })() : []}
        />
        <div className="collection-detail-actions">
          <button type="button" disabled={!canDecide} onClick={() => void decide(true)}>Approve</button>
          <button type="button" disabled={!canDecide} onClick={() => void decide(false)}>Reject</button>
        </div>
        {!settings.operatorId.trim() ? <p className="ps-muted">Set an operator identity in Settings before deciding.</p> : null}
      </article>
    </CollectionFrame>
  );
}

export function AgentsPage() {
  const [searchParams] = useSearchParams();
  const [settings] = useState(() => loadSettings());
  const [agents, setAgents] = useState<unknown>({ agents: [] });
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [error, setError] = useState('');
  const load = useCallback(() => {
    setError('');
    void listControlPlaneAgents(settings).then(setAgents).catch((cause) => {
      setAgents({ agents: [] });
      setError(cause instanceof Error ? cause.message : 'Agent registry is unavailable.');
    });
  }, [settings]);
  useEffect(load, [load]);
  const requestedAgentId = searchParams.get('agent');

  return (
    <CollectionFrame
      icon={Bot}
      eyebrow="AJANLAR"
      title="Çalışan ekip"
      description="Uzman ajanlar ve görev durumları."
      onRefresh={load}
      error={error}
      className="agents-collection-page"
    >
      <section className="collection-agent-registry">
        <AgentRegistryView agents={agents} selectedAgentId={selectedAgentId ?? requestedAgentId} onSelectAgent={setSelectedAgentId} />
      </section>
    </CollectionFrame>
  );
}
