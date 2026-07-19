import type { IconName } from './components/primitives/Icon';
import { PRODUCT_IDENTITY } from './productIdentity';

export type RouteId =
  | 'dashboard'
  | 'agents'
  | 'runs'
  | 'approvals'
  | 'evidence'
  | 'policy'
  | 'surfaces'
  | 'workspace'
  | 'assistant'
  | 'tasks'
  | 'system'
  | 'enterprise-workspace'
  | 'enterprise-users'
  | 'enterprise-roles'
  | 'enterprise-enrollment'
  | 'enterprise-fleet'
  | 'enterprise-identity'
  | 'memory-governance'
  | 'memory-authority'
  | 'memory-runtime'
  | 'memory-semantic'
  | 'governed-pilot-workflow'
  | 'design-partner-field-evidence'
  | 'design-partner-handoff'
  | 'mainline-rc-freeze'
  | 'rc-gate-evidence'
  | 'rc-release-decision'
  | 'operations'
  | 'settings'
  | 'logs'
  | 'reports'
  | 'alerts'
  | 'plans'
  | 'users'
  | 'roles'
  | 'policy-packs';

export type RouteBadgeKey = 'pendingApprovals' | 'warnings';

export type RouteDefinition = {
  id: string;
  routeId: RouteId;
  label: string;
  heading: string;
  icon: IconName;
  badgeKey?: RouteBadgeKey;
};

export type RouteGroup = {
  title: string;
  routes: RouteDefinition[];
};

export const routeGroups: RouteGroup[] = [
  {
    title: 'ÇALIŞMA ALANI',
    routes: [
      { id: 'dashboard', routeId: 'dashboard', label: 'Dashboard', heading: 'Dashboard', icon: 'home' },
      { id: 'agents', routeId: 'agents', label: 'Agents', heading: 'Agents', icon: 'users' },
      { id: 'runs', routeId: 'runs', label: 'Çalıştırmalar', heading: 'Runs', icon: 'terminal' },
      {
        id: 'approvals',
        routeId: 'approvals',
        label: 'Onaylar',
        heading: 'Approvals',
        icon: 'check',
        badgeKey: 'pendingApprovals',
      },
      { id: 'evidence', routeId: 'evidence', label: 'Evidence', heading: 'Signed Evidence', icon: 'archive' },
      { id: 'policy', routeId: 'policy', label: 'Policy', heading: 'Policy Simulation', icon: 'policy' },
      {
        id: 'surfaces',
        routeId: 'surfaces',
        label: 'Execution Surfaces',
        heading: 'Execution Surfaces',
        icon: 'shield',
      },
      { id: 'mission-control', routeId: 'workspace', label: 'Mission Control', heading: 'Mission Control', icon: 'target' },
      {
        id: 'ai-assistant',
        routeId: 'assistant',
        label: 'AI Assistant',
        heading: `${PRODUCT_IDENTITY.displayName} Assistant`,
        icon: 'sparkle',
      },
      { id: 'tasks', routeId: 'tasks', label: 'Görevler', heading: 'Tasks', icon: 'list' },
    ],
  },
  {
    title: 'SİSTEM',
    routes: [
      { id: 'system-health', routeId: 'system', label: 'Sistem Sağlığı', heading: 'System', icon: 'layers' },
      {
        id: 'enterprise-workspace',
        routeId: 'enterprise-workspace',
        label: 'Enterprise Workspace',
        heading: 'Enterprise Workspace',
        icon: 'shield',
      },
      {
        id: 'enterprise-users',
        routeId: 'enterprise-users',
        label: 'Enterprise Users',
        heading: 'Enterprise Users',
        icon: 'users',
      },
      {
        id: 'enterprise-roles',
        routeId: 'enterprise-roles',
        label: 'Enterprise Roles',
        heading: 'Enterprise Roles',
        icon: 'policy',
      },
      {
        id: 'enterprise-enrollment',
        routeId: 'enterprise-enrollment',
        label: 'Agent Enrollment',
        heading: 'Agent Enrollment',
        icon: 'approval',
      },
      {
        id: 'enterprise-fleet',
        routeId: 'enterprise-fleet',
        label: 'Agent Fleet',
        heading: 'Agent Fleet',
        icon: 'monitor',
      },
      {
        id: 'enterprise-identity',
        routeId: 'enterprise-identity',
        label: 'Identity Health',
        heading: 'Identity Health',
        icon: 'health',
      },
      {
        id: 'memory-governance',
        routeId: 'memory-governance',
        label: 'Memory Governance',
        heading: 'Memory Governance',
        icon: 'archive',
      },
      {
        id: 'memory-runtime',
        routeId: 'memory-runtime',
        label: 'Memory Runtime',
        heading: 'Memory Runtime',
        icon: 'layers',
      },
      {
        id: 'memory-authority',
        routeId: 'memory-authority',
        label: 'Memory Authority',
        heading: 'Memory Authority',
        icon: 'shield',
      },
      {
        id: 'memory-semantic',
        routeId: 'memory-semantic',
        label: 'Semantic Memory',
        heading: 'Semantic Memory',
        icon: 'archive',
      },
      {
        id: 'governed-pilot-workflow',
        routeId: 'governed-pilot-workflow',
        label: 'Governed Pilot Workflow',
        heading: 'Governed Pilot Workflow',
        icon: 'target',
      },
      {
        id: 'design-partner-field-evidence',
        routeId: 'design-partner-field-evidence',
        label: 'Design Partner Field Evidence',
        heading: 'Design Partner Field Evidence',
        icon: 'shield',
      },
      {
        id: 'design-partner-handoff',
        routeId: 'design-partner-handoff',
        label: 'Design Partner Handoff',
        heading: 'Design Partner Handoff',
        icon: 'clipboard',
      },
      {
        id: 'mainline-rc-freeze',
        routeId: 'mainline-rc-freeze',
        label: 'Mainline RC Freeze',
        heading: 'Mainline RC Freeze',
        icon: 'shield',
      },
      {
        id: 'rc-gate-evidence',
        routeId: 'rc-gate-evidence',
        label: 'RC Gate Evidence',
        heading: 'RC Gate Evidence',
        icon: 'shield',
      },
      { id: 'operations', routeId: 'operations', label: 'Yürütmeler', heading: 'Operations', icon: 'clipboard' },
      { id: 'settings', routeId: 'settings', label: 'Ayarlar', heading: 'Settings', icon: 'settings' },
    ],
  },
  {
    title: 'OPERASYONLAR',
    routes: [
      { id: 'logs', routeId: 'logs', label: 'Loglar', heading: 'Logs', icon: 'logs' },
      { id: 'reports', routeId: 'reports', label: 'Raporlar', heading: 'Reports', icon: 'report' },
      { id: 'alerts', routeId: 'alerts', label: 'Uyarılar', heading: 'Alerts', icon: 'bell', badgeKey: 'warnings' },
      { id: 'plans', routeId: 'plans', label: 'Planlamalar', heading: 'Plans', icon: 'play' },
    ],
  },
  {
    title: 'YÖNETİM',
    routes: [
      { id: 'users', routeId: 'users', label: 'Kullanıcılar', heading: 'Users', icon: 'users' },
      { id: 'roles', routeId: 'roles', label: 'Roller', heading: 'Roles', icon: 'user' },
      { id: 'policy-packs', routeId: 'policy-packs', label: 'Politikalar', heading: 'Policy Packs', icon: 'policy' },
    ],
  },
];

routeGroups[1]?.routes.splice(routeGroups[1].routes.length - 2, 0, {
  id: 'rc-release-decision',
  routeId: 'rc-release-decision',
  label: 'RC Release Decision',
  heading: 'RC Release Decision',
  icon: 'check',
});

export const routes = routeGroups.flatMap((group) => group.routes);
