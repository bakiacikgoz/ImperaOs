import type { CSSProperties, ReactNode } from 'react';
import { useLocation } from 'react-router-dom';

import { BrowserApprovalInbox } from '../browser/BrowserApprovalInbox';
import { Sidebar } from './Sidebar';
import { useProductShellStore } from '../state/productShellStore';
import { ProductTheme } from '../styles/ProductTheme';
import { GlobalSearch } from './GlobalSearch';
import { TopBar } from './TopBar';

export function AppShell({ children }: { children: ReactNode }) {
  const location = useLocation();
  const theme = useProductShellStore((state) => state.theme);
  const sidebarWidth = useProductShellStore((state) => state.sidebarWidth);
  const sidebarCollapsed = useProductShellStore((state) => state.sidebarCollapsed);
  const isHome = location.pathname === '/';
  return (
    <div
      className={`imperaos-product-shell-v2 app-shell ${isHome ? 'is-home' : ''} ${sidebarCollapsed ? 'has-closed-panels' : ''}`}
      style={{ '--sidebar-width': `${sidebarWidth}px` } as CSSProperties}
    >
      <ProductTheme theme={theme} />
      <Sidebar />
      <section className="app-frame">
        {(!isHome || sidebarCollapsed) && <TopBar />}
        {children}
      </section>
      <GlobalSearch />
      <BrowserApprovalInbox />
    </div>
  );
}
