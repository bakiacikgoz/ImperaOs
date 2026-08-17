import { Search, X } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { artifactBridge } from '../../artifact-workspace/artifactBridge';
import { asControlPlaneAgentList } from '../../controlPlaneMappers';
import { fetchApprovals, listControlPlaneAgents } from '../../bridge';
import { loadSettings } from '../../settings';
import { PRODUCT_SHELL_SHORTCUTS } from '../shortcuts/shortcutRegistry';
import { useGlobalShortcut } from '../shortcuts/useGlobalShortcut';
import { productWorkspaceClient, type ProductWorkspaceProject, type ProductWorkspaceTask } from '../adapters/productWorkspaceClient';
import { useProductShellStore } from '../state/productShellStore';

type SearchKind = 'project' | 'task' | 'artifact' | 'approval' | 'agent' | 'route' | 'command';
type SearchResult = { id: string; kind: SearchKind; title: string; detail: string; path: string };
type SearchData = {
  projects: ProductWorkspaceProject[];
  tasks: ProductWorkspaceTask[];
  artifacts: Array<{ artifactId: string; title: string; kind: string; status: string }>;
  approvals: Array<{ approvalId: string; targetKind: string; status: string }>;
  agents: Array<{ agentId: string; title: string; detail: string }>;
};
type SearchLoadResult = { data: SearchData; unavailableSources: string[] };

const EMPTY_DATA: SearchData = { projects: [], tasks: [], artifacts: [], approvals: [], agents: [] };
const ROUTES: SearchResult[] = [
  { id: 'route:new', kind: 'route', title: 'Yeni görev', detail: 'Yönetilen çalışma oluştur', path: '/' },
  { id: 'route:library', kind: 'route', title: 'Siteler', detail: 'Yönetilen artifact’lar', path: '/library' },
  { id: 'route:approvals', kind: 'route', title: 'Onaylar', detail: 'Bekleyen yönetilen kararlar', path: '/approvals' },
  { id: 'route:agents', kind: 'route', title: 'Eklentiler', detail: 'Yönetilen ajan kaydı', path: '/agents' },
  { id: 'route:settings', kind: 'route', title: 'Ayarlar', detail: 'Ürün ve runtime ayarları', path: '/settings' },
];

function record(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null ? value as Record<string, unknown> : {};
}

function approvalsFrom(value: unknown): SearchData['approvals'] {
  const pending = record(value).pending;
  if (!Array.isArray(pending)) return [];
  return pending.flatMap((item) => {
    const approval = record(item);
    const approvalId = typeof approval.approval_id === 'string' ? approval.approval_id : '';
    return approvalId ? [{
      approvalId,
      targetKind: typeof approval.target_kind === 'string' ? approval.target_kind : 'governed action',
      status: typeof approval.status === 'string' ? approval.status : 'pending',
    }] : [];
  });
}

async function loadSearchData(): Promise<SearchLoadResult> {
  const settings = loadSettings();
  const [workspace, artifacts, approvals, agents] = await Promise.allSettled([
    productWorkspaceClient.listProjects().then(async ({ projects }) => ({
      projects,
      tasks: (await Promise.all(projects.map((project) => productWorkspaceClient.listTasks(project.projectId)))).flatMap((result) => result.tasks),
    })),
    artifactBridge.list(),
    fetchApprovals(settings),
    listControlPlaneAgents(settings),
  ]);
  const unavailableSources = [
    ...(workspace.status === 'rejected' ? ['çalışma alanı'] : []),
    ...(artifacts.status === 'rejected' ? ['artifact'] : []),
    ...(approvals.status === 'rejected' ? ['onay'] : []),
    ...(agents.status === 'rejected' ? ['ajan'] : []),
  ];
  if (unavailableSources.length === 4) {
    throw new Error(`Arama kaynakları kullanılamıyor: ${unavailableSources.join(', ')}.`);
  }
  const agentRows = agents.status === 'fulfilled' ? asControlPlaneAgentList(agents.value).agents : [];
  return {
    unavailableSources,
    data: {
      projects: workspace.status === 'fulfilled' ? workspace.value.projects : [],
      tasks: workspace.status === 'fulfilled' ? workspace.value.tasks : [],
      artifacts: artifacts.status === 'fulfilled'
        ? artifacts.value.items.map((item) => ({ artifactId: item.artifactId, title: item.title, kind: item.kind, status: item.status }))
        : [],
      approvals: approvals.status === 'fulfilled' ? approvalsFrom(approvals.value) : [],
      agents: agentRows.map((agent) => ({ agentId: agent.agent_id, title: agent.display_name || agent.agent_id, detail: `${agent.agent_type} · ${agent.status}` })),
    },
  };
}

function matchingResults(data: SearchData, query: string): SearchResult[] {
  const projects = data.projects.map((project) => ({
    id: `project:${project.projectId}`, kind: 'project' as const, title: project.title,
    detail: project.status, path: `/?project=${encodeURIComponent(project.projectId)}`,
  }));
  const projectTitles = new Map(data.projects.map((project) => [project.projectId, project.title]));
  const tasks = data.tasks.map((task) => ({
    id: `task:${task.taskId}`, kind: 'task' as const, title: task.title,
    detail: projectTitles.get(task.projectId) ?? task.status, path: `/task/${encodeURIComponent(task.taskId)}`,
  }));
  const artifacts = data.artifacts.map((artifact) => ({
    id: `artifact:${artifact.artifactId}`, kind: 'artifact' as const, title: artifact.title,
    detail: `${artifact.kind} · ${artifact.status}`, path: `/library?artifact=${encodeURIComponent(artifact.artifactId)}`,
  }));
  const approvals = data.approvals.map((approval) => ({
    id: `approval:${approval.approvalId}`, kind: 'approval' as const, title: approval.approvalId,
    detail: `${approval.targetKind} · ${approval.status}`, path: `/approvals?approval=${encodeURIComponent(approval.approvalId)}`,
  }));
  const agents = data.agents.map((agent) => ({
    id: `agent:${agent.agentId}`, kind: 'agent' as const, title: agent.title,
    detail: agent.detail, path: `/agents?agent=${encodeURIComponent(agent.agentId)}`,
  }));
  const candidates = [...tasks, ...projects, ...artifacts, ...approvals, ...agents, ...ROUTES];
  if (!query) return tasks.slice(0, 10);
  return candidates.filter((item) => `${item.title} ${item.detail} ${item.kind}`.toLowerCase().includes(query)).slice(0, 25);
}

export function GlobalSearch() {
  const navigate = useNavigate();
  const open = useProductShellStore((state) => state.searchOpen);
  const setOpen = useProductShellStore((state) => state.setSearchOpen);
  const [query, setQuery] = useState('');
  const [debouncedQuery, setDebouncedQuery] = useState('');
  const [data, setData] = useState<SearchData>(EMPTY_DATA);
  const [status, setStatus] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  useGlobalShortcut('global-search', () => setOpen(true));
  useEffect(() => {
    if (open) window.requestAnimationFrame(() => inputRef.current?.focus());
  }, [open]);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedQuery(query.trim().toLowerCase()), 180);
    return () => window.clearTimeout(timer);
  }, [query]);
  useEffect(() => {
    let active = true;
    setStatus('Yönetilen arama yükleniyor…');
    void loadSearchData().then((next) => {
      if (!active) return;
      setData(next.data);
      setStatus(next.unavailableSources.length
        ? `Kısmi arama · kullanılamayan kaynaklar: ${next.unavailableSources.join(', ')}.`
        : '');
    }).catch((cause) => {
      if (active) setStatus(cause instanceof Error ? cause.message : 'Arama kaynakları kullanılamıyor.');
    });
    return () => { active = false; };
  }, []);
  useEffect(() => {
    if (!open) return;
    const close = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false);
    };
    window.addEventListener('keydown', close);
    return () => window.removeEventListener('keydown', close);
  }, [open, setOpen]);

  const results = useMemo(() => matchingResults(data, debouncedQuery), [data, debouncedQuery]);
  if (!open) return null;
  return (
    <div className="modal-backdrop" onMouseDown={() => setOpen(false)}>
      <section className="search-modal" aria-label="Global search" onMouseDown={(event) => event.stopPropagation()}>
        <label className="search-input">
          <Search size={18} />
          <input
            ref={inputRef}
            autoFocus
            aria-label="Search"
            aria-keyshortcuts={PRODUCT_SHELL_SHORTCUTS['global-search'].ariaKeyShortcuts}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Ara…"
          />
          <button className="icon-button" type="button" aria-label="Aramayı kapat" onClick={() => setOpen(false)}><X size={16} /></button>
        </label>
        <div className="search-group-label">{status || 'SON GÖREVLER'}</div>
        {results.map((result) => (
          <button
            className="search-result"
            type="button"
            key={result.id}
            onClick={() => {
              navigate(result.path);
              setOpen(false);
            }}
          >
            <span>{result.title}</span><small>{result.kind} · {result.detail}</small>
          </button>
        ))}
        {!status && !results.length && <p className="search-result">Yönetilen sonuç bulunamadı.</p>}
        <div className="search-hint"><span>↵ aç</span><span>esc kapat</span></div>
      </section>
    </div>
  );
}
