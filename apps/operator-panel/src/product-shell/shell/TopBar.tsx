import {
  ChevronLeft,
  ChevronRight,
  PanelBottomOpen,
  PanelLeftOpen,
  PanelRightOpen,
  Plus,
  SlidersHorizontal,
  SquarePen,
} from 'lucide-react';
import { useLocation, useNavigate, useParams } from 'react-router-dom';

import { useProductShellStore } from '../state/productShellStore';

export function TopBar() {
  const location = useLocation();
  const navigate = useNavigate();
  const { taskId } = useParams();
  const task = useProductShellStore((state) => state.tasks.find((item) => item.id === taskId));
  const sidebarCollapsed = useProductShellStore((state) => state.sidebarCollapsed);
  const setSidebarCollapsed = useProductShellStore((state) => state.setSidebarCollapsed);
  const contextRailOpen = useProductShellStore((state) => state.contextRailOpen);
  const setContextRailOpen = useProductShellStore((state) => state.setContextRailOpen);
  const dockOpen = useProductShellStore((state) => state.dockOpen);
  const setDockOpen = useProductShellStore((state) => state.setDockOpen);
  const isWorkspace = location.pathname.endsWith('/workspace');

  if (sidebarCollapsed) {
    return (
      <header className="topbar closed-panels-topbar">
        <div className="closed-panels-leading">
          <button className="icon-button" type="button" onClick={() => setSidebarCollapsed(false)} title="Kenar çubuğunu aç" aria-label="Kenar çubuğunu aç">
            <PanelLeftOpen size={18} />
          </button>
          <button className="icon-button subdued" type="button" onClick={() => navigate(-1)} title="Geri">
            <ChevronLeft size={18} />
          </button>
          <button className="icon-button subdued" type="button" onClick={() => navigate(1)} title="İleri">
            <ChevronRight size={18} />
          </button>
          <button className="icon-button closed-panels-new-work" type="button" onClick={() => navigate('/')} title="Yeni görev">
            <SquarePen size={17} />
          </button>
        </div>
        <div className="closed-panels-actions">
          {taskId ? (
            <>
              <button className={`icon-button ${isWorkspace ? 'is-active' : ''}`} type="button" onClick={() => navigate(isWorkspace ? `/task/${taskId}` : `/task/${taskId}/workspace`)} title="Çalışma alanı">
                <SlidersHorizontal size={18} />
              </button>
            </>
          ) : null}
          {taskId ? <>
              <button className={`icon-button ${dockOpen ? 'is-active' : ''}`} type="button" onClick={() => setDockOpen(!dockOpen)} title="Utility dock">
                <PanelBottomOpen size={17} />
              </button>
              <button className={`icon-button ${contextRailOpen ? 'is-active' : ''}`} type="button" onClick={() => setContextRailOpen(!contextRailOpen)} title="Bağlam paneli">
                <PanelRightOpen size={17} />
              </button>
            </> : <>
              <span className="icon-button" aria-disabled="true" title="Alt panel bir görev açıldığında kullanılabilir." data-disabled-reason="TASK_CONTEXT_REQUIRED"><PanelBottomOpen size={17} /></span>
              <span className="icon-button" aria-disabled="true" title="Bağlam paneli bir görev açıldığında kullanılabilir." data-disabled-reason="TASK_CONTEXT_REQUIRED"><PanelRightOpen size={17} /></span>
            </>}
        </div>
      </header>
    );
  }

  return (
    <header className={`topbar ${taskId ? 'task-reference-header' : ''}`}>
      <div className="topbar-leading task-header-title">
        <span className="task-status-dot" aria-hidden="true" />
        <span className="task-crumb">{task?.title ?? 'ImperaOS'}</span>
      </div>
      <div className="topbar-actions task-header-actions">
        <button className="topbar-new" type="button" onClick={() => navigate('/')}>
          <Plus size={15} /> Yeni görev
        </button>
        {taskId && (
          <>
            <button className={`icon-button ${isWorkspace ? 'is-active' : ''}`} type="button" onClick={() => navigate(isWorkspace ? `/task/${taskId}` : `/task/${taskId}/workspace`)} title="Çalışma alanı">
              <SlidersHorizontal size={16} />
            </button>
            <button className={`icon-button ${contextRailOpen ? 'is-active' : ''}`} type="button" onClick={() => setContextRailOpen(!contextRailOpen)} title="Bağlam">
              <PanelRightOpen size={16} />
            </button>
            <button className={`icon-button ${dockOpen ? 'is-active' : ''}`} type="button" onClick={() => setDockOpen(!dockOpen)} title="Alt panel">
              <PanelBottomOpen size={16} />
            </button>
          </>
        )}
      </div>
    </header>
  );
}
