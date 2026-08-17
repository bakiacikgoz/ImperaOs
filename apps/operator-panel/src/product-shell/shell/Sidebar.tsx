import {
  Archive,
  ArrowUp,
  Blocks,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CirclePlus,
  Clock3,
  Folder,
  GitPullRequest,
  MoreHorizontal,
  Orbit,
  PanelLeftClose,
  PanelLeftOpen,
  Pin,
  Plus,
  Search,
  Settings,
  SquarePen,
} from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';

import { productWorkspaceClient, type ProductWorkspaceProject } from '../adapters/productWorkspaceClient';
import { useProductShellStore } from '../state/productShellStore';

type ProjectSort = 'updated_desc' | 'manual' | 'priority';

const primaryLinks = [
  { label: 'Yeni görev', icon: SquarePen, to: '/', trailingIcon: CirclePlus },
  { label: "Pull request'ler", icon: GitPullRequest, to: '/approvals' },
  { label: 'Siteler', icon: Blocks, to: '/library' },
  { label: 'Zamanlananlar', icon: Clock3, to: '/automations' },
  { label: 'Eklentiler', icon: Orbit, to: '/agents' },
];

function shellTask(task: Awaited<ReturnType<typeof productWorkspaceClient.getTask>>) {
  return {
    id: task.taskId,
    projectId: task.projectId,
    title: task.title,
    createdAt: task.createdAtUtc,
    updatedAt: task.updatedAtUtc,
    status: task.status,
    priority: task.priority,
    pinned: task.pinned,
    manualOrder: task.manualOrder,
    archivedAt: task.archivedAtUtc,
    assistantSessionId: task.assistantSessionId ?? undefined,
    reasoningEffort: task.reasoningEffort,
    speedProfile: task.speedProfile,
    approvalProfile: task.approvalProfile,
  };
}

function SidebarRowActions({
  title,
  pinned,
  busy,
  canMoveUp,
  onPin,
  onMoveUp,
  onArchive,
}: {
  title: string;
  pinned: boolean;
  busy: boolean;
  canMoveUp: boolean;
  onPin: () => void;
  onMoveUp: () => void;
  onArchive: () => void;
}) {
  return (
    <span className="sidebar-row-actions">
      <button
        className={`sidebar-row-action ${pinned ? 'is-pinned' : ''}`}
        type="button"
        disabled={busy}
        aria-label={`${pinned ? 'Unpin' : 'Pin'} ${title}`}
        title={pinned ? 'Sabitlemeyi kaldır' : 'Sabitle'}
        onClick={onPin}
      >
        <Pin size={12} />
      </button>
      <button
        className="sidebar-row-action"
        type="button"
        disabled={busy || !canMoveUp}
        aria-label={`Move ${title} up`}
        title="Yukarı taşı"
        onClick={onMoveUp}
      >
        <ArrowUp size={12} />
      </button>
      <button
        className="sidebar-row-action"
        type="button"
        disabled={busy}
        aria-label={`Archive ${title}`}
        title="Arşivle"
        onClick={onArchive}
      >
        <Archive size={12} />
      </button>
    </span>
  );
}

export function Sidebar() {
  const navigate = useNavigate();
  const tasks = useProductShellStore((state) => state.tasks);
  const selectedTaskId = useProductShellStore((state) => state.selectedTaskId);
  const selectTask = useProductShellStore((state) => state.selectTask);
  const collapsed = useProductShellStore((state) => state.sidebarCollapsed);
  const setCollapsed = useProductShellStore((state) => state.setSidebarCollapsed);
  const setSearchOpen = useProductShellStore((state) => state.setSearchOpen);
  const upsertTasks = useProductShellStore((state) => state.upsertTasks);
  const upsertProjects = useProductShellStore((state) => state.upsertProjects);
  const sidebarWidth = useProductShellStore((state) => state.sidebarWidth);
  const setSidebarWidth = useProductShellStore((state) => state.setSidebarWidth);
  const [projects, setProjects] = useState<ProductWorkspaceProject[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [sort, setSort] = useState<ProjectSort>('manual');
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [organizeOpen, setOrganizeOpen] = useState(false);
  const [resizing, setResizing] = useState(false);

  const loadProjects = useCallback(async (cursor?: string, append = false) => {
    try {
      setError('');
      const page = await productWorkspaceClient.listProjects({ cursor, limit: 25, status: 'active', sort });
      setProjects((current) => append ? [...current, ...page.projects] : page.projects);
      setExpanded((current) => ({
        ...Object.fromEntries(page.projects.map((project) => [project.projectId, current[project.projectId] ?? true])),
        ...current,
      }));
      upsertProjects(page.projects.map((project) => ({
        projectId: project.projectId,
        rootRef: project.rootRef,
        rootDisplayName: project.rootDisplayName,
      })));
      setNextCursor(page.nextCursor);
      const groups = await Promise.all(page.projects.map((project) => productWorkspaceClient.listTasks(project.projectId)));
      upsertTasks(groups.flatMap((group) => group.tasks.map(shellTask)));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not load governed projects.');
    }
  }, [sort, upsertProjects, upsertTasks]);

  useEffect(() => { void loadProjects(); }, [loadProjects]);

  const mutate = async (action: () => Promise<unknown>) => {
    try {
      setBusy(true);
      setError('');
      await action();
      await loadProjects();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not update governed workspace records.');
    } finally {
      setBusy(false);
    }
  };

  const archiveTask = (taskId: string) => mutate(async () => {
    const changed = await productWorkspaceClient.archiveTask(taskId, 'Archived from sidebar');
    const archivedSelectedTask = useProductShellStore.getState().selectedTaskId === taskId;
    upsertTasks([shellTask(changed)]);
    if (archivedSelectedTask) navigate('/', { replace: true });
  });

  const resizeSidebar = (event: React.PointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = sidebarWidth;
    setResizing(true);
    const move = (moveEvent: PointerEvent) => setSidebarWidth(startWidth + moveEvent.clientX - startX);
    const end = () => {
      setResizing(false);
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', end);
      window.removeEventListener('pointercancel', end);
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', end);
    window.addEventListener('pointercancel', end);
  };

  const activeTasks = tasks.filter((task) => task.status !== 'archived');
  return (
    <aside
      className={`sidebar codex-sidebar ${collapsed ? 'is-collapsed' : ''} ${resizing ? 'is-resizing' : ''}`}
      style={{ width: collapsed ? undefined : sidebarWidth }}
      aria-label="Product navigation"
    >
      <div className="sidebar-utility">
        <button
          className="sidebar-toggle"
          type="button"
          aria-label={collapsed ? 'Kenar çubuğunu aç' : 'Kenar çubuğunu kapat'}
          title={collapsed ? 'Kenar çubuğunu aç' : 'Kenar çubuğunu kapat'}
          onClick={() => setCollapsed(!collapsed)}
        >
          {collapsed ? <PanelLeftOpen size={14} /> : <PanelLeftClose size={14} />}
        </button>
        {!collapsed && (
          <>
            <button className="sidebar-history" type="button" onClick={() => navigate(-1)} title="Geri"><ChevronLeft size={16} /></button>
            <button className="sidebar-history is-muted" type="button" onClick={() => navigate(1)} title="İleri"><ChevronRight size={16} /></button>
          </>
        )}
      </div>

      <div className="sidebar-content">
        <div className="sidebar-top">
          <button className="brand brand-dropdown" type="button" onClick={() => navigate('/')} title="ImperaOS">
            <span className="brand-text">ImperaOS</span><ChevronDown className="brand-chevron" size={13} />
          </button>
          <button className="icon-button" type="button" onClick={() => setSearchOpen(true)} title="Ara" aria-label="Ara">
            <Search size={14} />
          </button>
        </div>

        <nav className="sidebar-nav" aria-label="Ana navigasyon">
          {primaryLinks.map(({ label, icon: Icon, to, trailingIcon: TrailingIcon }) => (
            <NavLink
              key={label}
              to={to}
              end={to === '/'}
              className={({ isActive }) => `sidebar-link ${to === '/' ? 'sidebar-primary-action' : ''} ${isActive ? 'is-active' : ''}`}
            >
              <Icon size={14} strokeWidth={1.75} /><span>{label}</span>
              {TrailingIcon && <TrailingIcon className="sidebar-link-action" size={14} strokeWidth={1.7} />}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-scroll">
          <div className="sidebar-section-header">
            <span>Projeler</span>
            <div className="sidebar-section-actions">
              <button className={`section-action ${organizeOpen ? 'is-active' : ''}`} type="button" title="Projeleri düzenle" onClick={() => setOrganizeOpen(!organizeOpen)}>
                <MoreHorizontal size={15} />
              </button>
              <button className="section-action" type="button" disabled={busy} title="Yeni proje" onClick={() => void mutate(() => productWorkspaceClient.registerProjectFromFolder())}>
                <Plus size={16} />
              </button>
            </div>
          </div>
          {organizeOpen && (
            <div className="section-organize-menu" role="menu">
              <label className="section-menu-option">Sıralama
                <select aria-label="Sort projects" value={sort} onChange={(event) => setSort(event.target.value as ProjectSort)}>
                  <option value="manual">El ile</option>
                  <option value="updated_desc">Son güncellenen</option>
                  <option value="priority">Sabitlenenler</option>
                </select>
              </label>
            </div>
          )}
          {error && (
            <p className={`sidebar-error ${error.includes('desktop runtime') ? 'sidebar-runtime-notice' : ''}`} role="alert">
              {error}
            </p>
          )}
          <div className="project-list">
            {projects.map((project) => {
              const projectTasks = activeTasks.filter((task) => task.projectId === project.projectId);
              return (
                <div className="project-group" key={project.projectId}>
                  <div className="sidebar-row-shell">
                    <button
                      className="project-row"
                      type="button"
                      onClick={() => {
                        setExpanded((current) => ({ ...current, [project.projectId]: !current[project.projectId] }));
                        navigate(`/?project=${encodeURIComponent(project.projectId)}`);
                      }}
                    >
                      <Folder size={14} strokeWidth={1.75} /><span>{project.title}</span>
                    </button>
                    <SidebarRowActions
                      title={project.title}
                      pinned={project.pinned}
                      busy={busy}
                      canMoveUp={project.manualOrder > 0}
                      onPin={() => void mutate(() => productWorkspaceClient.updateProject(project.projectId, { pinned: !project.pinned }))}
                      onMoveUp={() => void mutate(() => productWorkspaceClient.updateProject(project.projectId, { manualOrder: Math.max(0, project.manualOrder - 1) }))}
                      onArchive={() => void mutate(() => productWorkspaceClient.archiveProject(project.projectId, 'Archived from sidebar'))}
                    />
                  </div>
                  {expanded[project.projectId] && projectTasks.map((task) => (
                    <div className="sidebar-row-shell" key={`${project.projectId}:${task.id}`}>
                      <NavLink
                        className={`project-task ${selectedTaskId === task.id ? 'is-selected' : ''}`}
                        to={`/task/${task.id}`}
                        onClick={() => selectTask(task.id)}
                      >
                        <span className="sidebar-task-title"><span className="sidebar-task-title-track">{task.title}</span></span>
                        {task.status === 'active' && <span className="project-task-dot" />}
                      </NavLink>
                      <SidebarRowActions
                        title={task.title}
                        pinned={Boolean(task.pinned)}
                        busy={busy}
                        canMoveUp={(task.manualOrder ?? 0) > 0}
                        onPin={() => void mutate(async () => {
                          const changed = await productWorkspaceClient.updateTask(task.id, { pinned: !task.pinned });
                          upsertTasks([shellTask(changed)]);
                        })}
                        onMoveUp={() => void mutate(async () => {
                          const changed = await productWorkspaceClient.updateTask(task.id, { manualOrder: Math.max(0, (task.manualOrder ?? 0) - 1) });
                          upsertTasks([shellTask(changed)]);
                        })}
                        onArchive={() => void archiveTask(task.id)}
                      />
                    </div>
                  ))}
                </div>
              );
            })}
            {!projects.length && !error && <p className="sidebar-empty">Yönetilen proje eklemek için bir klasör seçin.</p>}
            {nextCursor && <button className="sidebar-more" type="button" disabled={busy} onClick={() => void loadProjects(nextCursor, true)}>Daha fazla göster</button>}
          </div>

          <div className="sidebar-section-header recent-section-header">
            <span>Görevler</span>
            <div className="sidebar-section-actions">
              <span
                className="section-action"
                aria-disabled="true"
                title="Görev sıralaması satır eylemlerinden yönetilir."
                data-disabled-reason="TASK_COLLECTION_ACTIONS_UNAVAILABLE"
              >
                <MoreHorizontal size={15} />
              </span>
              <button className="section-action section-create-task" type="button" title="Yeni görev" onClick={() => navigate('/')}><SquarePen size={12} /></button>
            </div>
          </div>
          <div className="recent-list">
            {activeTasks.map((task) => (
              <div className="sidebar-row-shell" key={`recent:${task.id}`}>
                <NavLink
                  className={`recent-task ${selectedTaskId === task.id ? 'is-current' : ''}`}
                  to={`/task/${task.id}`}
                  onClick={() => selectTask(task.id)}
                >
                  <span className="sidebar-task-title"><span className="sidebar-task-title-track">{task.title}</span></span>
                  {task.status === 'active' && <span className="recent-task-dot" />}
                </NavLink>
                <SidebarRowActions
                  title={task.title}
                  pinned={Boolean(task.pinned)}
                  busy={busy}
                  canMoveUp={(task.manualOrder ?? 0) > 0}
                  onPin={() => void mutate(async () => {
                    const changed = await productWorkspaceClient.updateTask(task.id, { pinned: !task.pinned });
                    upsertTasks([shellTask(changed)]);
                  })}
                  onMoveUp={() => void mutate(async () => {
                    const changed = await productWorkspaceClient.updateTask(task.id, { manualOrder: Math.max(0, (task.manualOrder ?? 0) - 1) });
                    upsertTasks([shellTask(changed)]);
                  })}
                  onArchive={() => void archiveTask(task.id)}
                />
              </div>
            ))}
            {!activeTasks.length && <p className="sidebar-empty">Görevler çalışmaya başladığında burada görünür.</p>}
          </div>
        </div>

        <div className="sidebar-user-wrap">
          <div className="sidebar-user-row">
            <button className="sidebar-user" type="button" onClick={() => setProfileOpen(!profileOpen)}>
              <span className="avatar">BA</span><span className="user-copy"><strong>bakiacikgoz</strong><small>ImperaOS</small></span><ChevronDown size={13} />
            </button>
            <button className="icon-button" type="button" onClick={() => navigate('/settings')} title="Ayarlar"><Settings size={14} /></button>
          </div>
          {profileOpen && <div className="user-menu"><button type="button" onClick={() => navigate('/settings')}><Settings size={14} /> Ayarlar</button></div>}
        </div>
      </div>
      {!collapsed && <div className="sidebar-resize" role="separator" aria-label="Kenar çubuğu genişliği" tabIndex={0} onPointerDown={resizeSidebar} />}
    </aside>
  );
}
