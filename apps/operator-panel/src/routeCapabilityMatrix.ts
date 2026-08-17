import type { RouteId } from './routeRegistry';
import { routes } from './routeRegistry';

export type RouteActionState = 'working' | 'disabled_with_reason' | 'preview_only';

export type RouteCapability = {
  routeId: RouteId;
  title: string;
  dataSource: 'bridge' | 'snapshot' | 'preview_only';
  primaryActions: Array<{
    actionId: string;
    label: string;
    state: RouteActionState;
    bridgeCommand?: string;
    cliCommand?: string;
    requiredPermission?: string;
    disabledReasonCode?: string;
    noShipIfInert: boolean;
  }>;
};

const bridgeActions: Partial<Record<RouteId, RouteCapability['primaryActions']>> = {
  assistant: [
    {
      actionId: 'assistant.start_turn',
      label: 'Send',
      state: 'working',
      bridgeCommand: 'bridge_assistant_start_turn',
      requiredPermission: 'runtime.run',
      noShipIfInert: true,
    },
    {
      actionId: 'assistant.cancel_turn',
      label: 'Stop',
      state: 'working',
      bridgeCommand: 'bridge_assistant_cancel_turn',
      requiredPermission: 'runtime.run',
      noShipIfInert: true,
    },
  ],
  agents: [
    {
      actionId: 'agent.register',
      label: 'Register agent',
      state: 'working',
      bridgeCommand: 'bridge_control_plane_agent_register',
      cliCommand: 'imperaos control-plane agent register',
      requiredPermission: 'agent.registry.write',
      noShipIfInert: true,
    },
  ],
  runs: [
    {
      actionId: 'run.submit',
      label: 'Submit run',
      state: 'working',
      bridgeCommand: 'bridge_control_plane_run_submit',
      cliCommand: 'imperaos control-plane run submit',
      requiredPermission: 'runtime.run',
      noShipIfInert: true,
    },
  ],
  approvals: [
    {
      actionId: 'approval.decide',
      label: 'Approve',
      state: 'working',
      bridgeCommand: 'bridge_approval_decide',
      cliCommand: 'imperaos approval decide',
      requiredPermission: 'approval.decide',
      noShipIfInert: true,
    },
    {
      actionId: 'approval.execute',
      label: 'Execute approved action',
      state: 'working',
      bridgeCommand: 'bridge_approval_execute',
      cliCommand: 'imperaos approval execute',
      requiredPermission: 'approval.execute',
      noShipIfInert: true,
    },
  ],
  evidence: [
    {
      actionId: 'evidence.verify_latest',
      label: 'Verify latest',
      state: 'working',
      bridgeCommand: 'bridge_control_plane_evidence_verify',
      cliCommand: 'imperaos control-plane evidence verify',
      requiredPermission: 'evidence.verify',
      noShipIfInert: true,
    },
  ],
  'enterprise-workspace': [
    {
      actionId: 'workspace.bootstrap',
      label: 'Bootstrap workspace',
      state: 'disabled_with_reason',
      cliCommand: 'imperaos enterprise workspace bootstrap',
      requiredPermission: 'workspace.bootstrap',
      disabledReasonCode: 'BRIDGE_COMMAND_NOT_REGISTERED',
      noShipIfInert: true,
    },
  ],
  'enterprise-enrollment': [
    {
      actionId: 'enrollment.token_create',
      label: 'Create token',
      state: 'disabled_with_reason',
      cliCommand: 'imperaos enterprise enrollment token create',
      requiredPermission: 'agent.enrollment.create',
      disabledReasonCode: 'BRIDGE_COMMAND_NOT_REGISTERED',
      noShipIfInert: true,
    },
  ],
  'memory-authority': [
    {
      actionId: 'memory.query',
      label: 'Query memory',
      state: 'disabled_with_reason',
      cliCommand: 'imperaos memory workspace authority query',
      requiredPermission: 'memory.read',
      disabledReasonCode: 'BRIDGE_COMMAND_NOT_REGISTERED',
      noShipIfInert: true,
    },
  ],
  'governed-pilot-workflow': [
    {
      actionId: 'workflow.run',
      label: 'Run workflow',
      state: 'disabled_with_reason',
      cliCommand: 'imperaos pilot workflow run',
      requiredPermission: 'runtime.run',
      disabledReasonCode: 'BRIDGE_COMMAND_NOT_REGISTERED',
      noShipIfInert: true,
    },
  ],
  surfaces: [
    {
      actionId: 'computer_use.live_execute',
      label: 'Live execute',
      state: 'disabled_with_reason',
      disabledReasonCode: 'COMPUTER_USE_NOT_QUALIFIED',
      requiredPermission: 'computer_use.execute',
      noShipIfInert: true,
    },
  ],
  settings: [
    {
      actionId: 'settings.bridge_handshake',
      label: 'Bridge handshake',
      state: 'working',
      bridgeCommand: 'bridge_handshake',
      cliCommand: 'imperaos operator snapshot',
      noShipIfInert: true,
    },
  ],
};

const snapshotOnlyRoutes = new Set<RouteId>([
  'dashboard',
  'workspace',
  'tasks',
  'system',
  'enterprise-users',
  'enterprise-roles',
  'enterprise-fleet',
  'enterprise-identity',
  'memory-governance',
  'memory-runtime',
  'memory-semantic',
  'policy',
  'operations',
  'logs',
  'reports',
  'alerts',
  'plans',
  'users',
  'roles',
  'policy-packs',
  'design-partner-field-evidence',
  'design-partner-handoff',
  'mainline-rc-freeze',
  'rc-gate-evidence',
  'rc-release-decision',
]);

export const routeCapabilityMatrix: RouteCapability[] = routes.map((route) => ({
  routeId: route.routeId,
  title: route.heading,
  dataSource: snapshotOnlyRoutes.has(route.routeId) ? 'snapshot' : 'bridge',
  primaryActions: bridgeActions[route.routeId] ?? [],
}));
