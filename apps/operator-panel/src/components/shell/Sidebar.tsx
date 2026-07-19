import { Icon, type IconName } from '../primitives/Icon';
import { StatusDot } from '../primitives/StatusDot';
import { routeGroups, type RouteId } from '../../routeRegistry';
import type { ThemeMode } from '../../settings';
import type { UiLocale } from '../../i18n';
import { PRODUCT_IDENTITY } from '../../productIdentity';

export type ShellViewKey = RouteId;

function nextThemeMode(themeMode: ThemeMode): ThemeMode {
  if (themeMode === 'system') return 'light';
  if (themeMode === 'light') return 'dark';
  return 'system';
}

function themeIcon(themeMode: ThemeMode): Extract<IconName, 'monitor' | 'sun' | 'moon'> {
  if (themeMode === 'light') return 'sun';
  if (themeMode === 'dark') return 'moon';
  return 'monitor';
}

function themeLabel(themeMode: ThemeMode): string {
  if (themeMode === 'light') return 'Açık';
  if (themeMode === 'dark') return 'Koyu';
  return 'Sistem';
}

const routeLabelTr: Partial<Record<RouteId, string>> = {
  dashboard: 'Gösterge paneli',
  agents: 'Agentlar',
  runs: 'Çalıştırmalar',
  approvals: 'Onaylar',
  evidence: 'Kanıtlar',
  policy: 'Politika',
  surfaces: 'Yürütme yüzeyleri',
  workspace: 'Mission Control',
  assistant: 'AI Asistan',
  tasks: 'Görevler',
  system: 'Sistem sağlığı',
  'memory-governance': 'Memory yönetişimi',
  'enterprise-workspace': 'Enterprise workspace',
  'enterprise-users': 'Enterprise kullanicilar',
  'enterprise-roles': 'Enterprise roller',
  'enterprise-enrollment': 'Agent enrollment',
  'enterprise-fleet': 'Agent filosu',
  'enterprise-identity': 'Identity health',
  'memory-authority': 'Memory authority',
  'memory-runtime': 'Memory runtime',
  'memory-semantic': 'Semantic memory',
  'mainline-rc-freeze': 'Mainline RC freeze',
  'rc-gate-evidence': 'RC gate evidence',
  'rc-release-decision': 'RC release decision',
  operations: 'Yürütmeler',
  settings: 'Ayarlar',
  logs: 'Loglar',
  reports: 'Raporlar',
  alerts: 'Uyarılar',
  plans: 'Planlamalar',
  users: 'Kullanıcılar',
  roles: 'Roller',
  'policy-packs': 'Politikalar',
};

function routeLabel(label: string, routeId: RouteId, locale: UiLocale): string {
  if (locale !== 'tr') {
    return label;
  }
  return routeLabelTr[routeId] ?? label;
}

export type SidebarGroup = {
  title: string;
  items: Array<{
    id: string;
    key: ShellViewKey;
    label: string;
    icon: IconName;
    badgeCount?: number;
  }>;
};

export function Sidebar({
  activeView,
  open,
  collapsed,
  operatorId,
  pendingApprovalCount,
  warningCount,
  themeMode = 'system',
  locale = 'en',
  onClose,
  onToggleCollapse,
  onNavigate,
  onThemeChange,
}: {
  activeView: ShellViewKey;
  open: boolean;
  collapsed: boolean;
  operatorId: string;
  pendingApprovalCount: number;
  warningCount: number;
  themeMode?: ThemeMode;
  locale?: UiLocale;
  onClose: () => void;
  onToggleCollapse: () => void;
  onNavigate: (view: ShellViewKey) => void;
  onThemeChange: (theme: ThemeMode) => void;
}) {
  const assistantEnabled = import.meta.env.VITE_OPERATOR_PANEL_ASSISTANT !== '0';
  const groups: SidebarGroup[] = routeGroups.map((group) => ({
    title: group.title,
    items: group.routes
      .filter((item) => assistantEnabled || item.routeId !== 'assistant')
      .map((item) => ({
        id: item.id,
        key: item.routeId,
        label: routeLabel(item.label, item.routeId, locale),
        icon: item.icon,
        badgeCount:
          item.badgeKey === 'pendingApprovals'
            ? pendingApprovalCount
            : item.badgeKey === 'warnings'
              ? warningCount
              : undefined,
      })),
  }));

  const sidebarClassName = [
    'sidebar',
    'premium-sidebar',
    open ? 'sidebar-open' : '',
    collapsed ? 'premium-sidebar-collapsed' : '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <aside className={sidebarClassName}>
      <div className="premium-brand">
        <div className="brand-mark">
          <Icon name="hex" />
        </div>
        <div>
          <h1>{PRODUCT_IDENTITY.displayName}</h1>
          <p>Agent Control Plane</p>
        </div>
        <button
          type="button"
          aria-label={collapsed ? 'Menüyü genişlet' : 'Menüyü daralt'}
          title={collapsed ? 'Menüyü genişlet' : 'Menüyü daralt'}
          onClick={open ? onClose : onToggleCollapse}
        >
          <Icon name="chevron" />
        </button>
      </div>

      <nav className="premium-nav" aria-label="Ana navigasyon">
        {groups.map((group) => (
          <div className="premium-nav-group" key={group.title}>
            <span>{group.title}</span>
            {group.items.map((item) => {
              const isActive = item.key === activeView;
              const badge = item.badgeCount && item.badgeCount > 0 ? String(item.badgeCount) : '';
              return (
                <button
                  key={item.id}
                  type="button"
                  aria-label={item.label}
                  title={collapsed ? item.label : undefined}
                  className={isActive ? 'premium-nav-item premium-nav-item-active' : 'premium-nav-item'}
                  onClick={() => {
                    onNavigate(item.key);
                    onClose();
                  }}
                >
                  <Icon name={item.icon} />
                  <span>{item.label}</span>
                  {badge ? <em>{badge}</em> : null}
                </button>
              );
            })}
          </div>
        ))}
      </nav>

      <div className="operator-identity">
        <div className="operator-avatar">OP</div>
        <StatusDot tone="success" />
        <div>
          <strong>{operatorId || 'operator'}</strong>
          <span>Administrator</span>
        </div>
        <button
          type="button"
          className="operator-theme-cycle-btn"
          aria-label={`Tema değiştir. Şu an: ${themeLabel(themeMode)}`}
          title={`Tema: ${themeLabel(themeMode)}`}
          onClick={() => onThemeChange(nextThemeMode(themeMode))}
        >
          <Icon name={themeIcon(themeMode)} />
        </button>
      </div>
    </aside>
  );
}
