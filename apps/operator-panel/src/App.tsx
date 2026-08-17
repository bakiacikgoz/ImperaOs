import { useEffect, useMemo, useRef, useState } from 'react';

import type { AssistantArtifactProposalPart } from './assistant/assistantTypes';
import type { ArtifactSelection } from './artifact-workspace/editors/ArtifactEditorHost';

import {
  type BridgeErrorPayload,
  BridgeError,
  checkPermission,
  createBackup,
  decideApproval,
  dryRunMigration,
  executeApproval,
  exportRunArtifacts,
  exportSupportBundle,
  fetchControlPlaneDoctor,
  fetchControlPlaneSnapshot,
  fetchApprovals,
  getComputerUseSummary,
  getComputerUseSessionState,
  fetchGaReadiness,
  fetchIdentity,
  fetchKeysStatus,
  fetchSecurityBaseline,
  generateSecurityReview,
  getRunReplay,
  getRunStatus,
  listControlPlaneAgents,
  handshake,
  isBridgePreviewMode,
  listRuns,
  pauseComputerUseSession,
  planMigration,
  readArtifact,
  resolveConfig,
  resumeComputerUseSession,
  resumeTeamRun,
  rotateKeyPlan,
  runInstallRehearsal,
  runQualification,
  simulateControlPlanePolicy,
  snapshotMetrics,
  stopComputerUseSession,
  submitComputerUseRun,
  submitTeamRun,
  tailEvents,
  verifyControlPlaneEvidence,
  verifyBackup,
  verifyRestore,
  verifySignedArtifact,
  verifyControlPlaneClaims,
  showApproval,
} from './bridge';
import {
  getComputerUseCapability,
  getComputerUseVisionRuntimeBlockers,
  getComputerUseVisionRuntimeCapability,
  hasContractMismatch,
  isComputerUseSessionStartAllowed,
  type ComputerUseRuntimeChoice,
} from './capabilities';
import { ThemeProvider } from './context/ThemeContext';
import { dictionaries } from './i18n';
import { actorForOperator, canMutateWithOperatorId } from './operator';
import {
  type PanelSettings,
  type LocaleMode,
  assistantRuntimeOptionsFromSettings,
  getAssistantRuntimeSettings,
  isOperatorIdValid,
  loadSettings,
  resolveLocale,
  saveSettings,
  validateAssistantRuntimeSettings,
} from './settings';
import {
  buildWorkspaceSnapshot,
  readWorkspaceProgress,
  type WorkspaceStageKey,
} from './workspace';
import {
  buildActivityItems,
  buildNotificationItems,
  buildPendingApprovalSummaries,
  buildRuntimeSummaryItems,
  buildSessionEventItems,
  buildSystemHealthSummary,
  mapWorkspaceStageToMissionStage,
} from './missionMappers';
import { useAssistantRuntimeSession } from './assistant/useAssistantRuntimeSession';
import { useAssistantArtifactWorkspaceController } from './artifact-workspace/useAssistantArtifactWorkspaceController';
import { AssistantInlineFormPart } from './artifact-workspace/AssistantInlineFormPart';
import { resolveArtifactFeatureFlags, resolveEffectiveArtifactFeatureFlags } from './artifact-workspace/artifactFeatureFlags';
import { artifactBridge } from './artifact-workspace/artifactBridge';
import type { ArtifactRuntimeCapabilitySnapshot } from './artifact-workspace/artifactContracts';
import { useAssistantModels } from './assistant/useAssistantModels';
import type { AssistantProviderKind } from './assistant/modelDiscovery';
import { MissionControlView } from './components/mission/MissionControlView';
import type { SessionEventFilter, SessionEventItem } from './components/mission/SessionEventsCard';
import { ComputerUseOperationsCard } from './components/mission/ComputerUseOperationsCard';
import { ComputerUseBlockerChecklist } from './components/mission/ComputerUseBlockerChecklist';
import { AssistantView, type AssistantViewCopy } from './components/assistant/AssistantView';
import { AssistantWorkbench } from './components/assistant/AssistantWorkbench';
import {
  AssistantRightRail,
  type AssistantComplianceSummary,
  type AssistantRailSession,
  type AssistantRuntimeSummary,
} from './components/assistant/AssistantRightRail';
import { AgentRegistryView } from './components/control-plane/AgentRegistryView';
import { ClaimBoundaryBanner } from './components/control-plane/ClaimBoundaryBanner';
import { ControlPlaneDashboard } from './components/control-plane/ControlPlaneDashboard';
import { DesignPartnerBetaReadinessCard } from './components/control-plane/DesignPartnerBetaReadinessCard';
import { EvidencePackView } from './components/control-plane/EvidencePackView';
import { ExecutionSurfacesView } from './components/control-plane/ExecutionSurfacesView';
import { PolicySimulationView } from './components/control-plane/PolicySimulationView';
import { OperationCommandList } from './components/control-plane/OperationCommandCard';
import { RawInspector } from './components/control-plane/RawInspector';
import { OperatorPageShell } from './components/operator-page/OperatorPage';
import { operatorToneFromStatus } from './components/operator-page/operatorPageUtils';
import {
  AlertsPage,
  LogsPage,
  PlansPage,
  PolicyPacksPage,
  ReportsPage,
  RolesPage,
  UsersPage,
} from './components/product-pages/ProductizedPages';
import { AppShell } from './components/shell/AppShell';
import { ExportArtifactsModal } from './components/shell/ExportArtifactsModal';
import { RightRail } from './components/shell/RightRail';
import { loadControlPlaneSnapshot } from './control-plane/snapshot';
import type { ControlPlaneSnapshot, EvidencePackSummary, OperationDescriptor, PageViewModel } from './control-plane/types';
import { asControlPlaneClaimMatrix } from './controlPlaneMappers';
import { MemoryAuthorityView } from './memory-authority/MemoryAuthorityView';
import { GovernedPilotWorkflowView } from './governed-pilot-workflow/GovernedPilotWorkflowView';
import { DesignPartnerHandoffView } from './design-partner-handoff/DesignPartnerHandoffView';
import { AgentEnrollmentView } from './enterprise-workspace/AgentEnrollmentView';
import { AgentFleetView } from './enterprise-workspace/AgentFleetView';
import { EnterpriseWorkspaceOverview } from './enterprise-workspace/EnterpriseWorkspaceOverview';
import { IdentityHealthView } from './enterprise-workspace/IdentityHealthView';
import { RolesPermissionsView } from './enterprise-workspace/RolesPermissionsView';
import { UsersMembershipsView } from './enterprise-workspace/UsersMembershipsView';
import { MainlineRcFreezeView } from './mainline-rc-freeze/MainlineRcFreezeView';
import { RcGateEvidenceView } from './rc-gate-evidence/RcGateEvidenceView';
import { ReleaseDecisionView } from './release-decision/ReleaseDecisionView';
import { MemoryGovernanceView } from './memory/MemoryGovernanceView';
import { MemoryRuntimeView } from './memory-runtime/MemoryRuntimeView';
import { MemoryRuntimePolicyView } from './memory-runtime/MemoryRuntimePolicyView';
import { MemorySemanticIndexView } from './memory-semantic/MemorySemanticIndexView';
import { DesignPartnerFieldEvidenceView } from './provider-governance/DesignPartnerFieldEvidenceView';
import type { ShellViewKey } from './components/shell/Sidebar';
import type { RouteId } from './routeRegistry';

type ViewKey = RouteId;
type RunTabKey = 'overview' | 'stream' | 'approvals' | 'artifacts' | 'replay' | 'diagnostics';
type OperationTabKey = 'identity' | 'qualification' | 'security' | 'keys' | 'support' | 'maintenance';
type AutomationMode = 'assisted' | 'supervised';

type Toast = {
  id: number;
  kind: 'ok' | 'error';
  text: string;
};

type AppContentProps = {
  settings: PanelSettings;
  updateSettings: (next: Partial<PanelSettings>) => void;
};

type PayloadSummaryRow = {
  path: string;
  value: string;
};

type TaskFormState = {
  request: string;
  specPath: string;
  caseId: string;
  jobId: string;
  provider: string;
  fallbackProvider: string;
  model: string;
  hfModelId: string;
};

type OperationsFormState = {
  permission: string;
  verifyPath: string;
  supportOutput: string;
  backupOutputDir: string;
  backupVerifyDir: string;
  restoreVerifyDir: string;
  readinessReport: string;
  readinessQualificationReport: string;
  qualificationMode: string;
  qualificationOutputRoot: string;
  qualificationWorkloads: string;
  qualificationMergeFromReport: string;
  qualificationSoakHours: string;
  keyNextKeyId: string;
  keyActivateAt: string;
  keyRetireAfter: string;
};

const ARTIFACT_NAMES = ['status.json', 'tasks.json', 'handoffs.json', 'audit_envelope.json'] as const;
function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null ? (value as Record<string, unknown>) : {};
}

function readString(source: Record<string, unknown>, key: string, fallback = ''): string {
  const value = source[key];
  return typeof value === 'string' ? value : fallback;
}

function readArray(source: Record<string, unknown>, key: string): unknown[] {
  const value = source[key];
  return Array.isArray(value) ? value : [];
}

function readBool(source: Record<string, unknown>, key: string): boolean {
  return source[key] === true;
}

function humanizeCode(value: string): string {
  return value
    .replaceAll('.', ' ')
    .replaceAll('_', ' ')
    .trim()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function extractJobId(payload: unknown): string {
  const record = asRecord(payload);
  return readString(record, 'jobId') || readString(record, 'job_id');
}

function getErrorPayload(error: unknown): BridgeErrorPayload | null {
  if (error instanceof BridgeError) {
    return error.payload;
  }
  return null;
}

function JsonPanel({ value }: { value: unknown }) {
  return <RawInspector value={value} />;
}

function PayloadSummary({
  value,
  title = 'Summary',
  maxItems = 14,
  testId,
}: {
  value: unknown;
  title?: string;
  maxItems?: number;
  testId?: string;
}) {
  const rows = flattenPayloadSummary(value, maxItems);

  return (
    <div className="payload-summary" data-testid={testId}>
      <p className="card-label">{title}</p>
      {rows.length > 0 ? (
        <dl className="metric-list payload-summary-list">
          {rows.map((row) => (
            <div className="metric-row" key={row.path}>
              <dt>{row.path}</dt>
              <dd>{row.value}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="supporting">No summary fields available.</p>
      )}
    </div>
  );
}

function flattenPayloadSummary(value: unknown, maxItems: number): PayloadSummaryRow[] {
  const rows: PayloadSummaryRow[] = [];
  const seen = new WeakSet<object>();

  function visit(current: unknown, path: string, depth: number) {
    if (rows.length >= maxItems || depth > 5) {
      return;
    }

    const scalar = formatPayloadScalar(current);
    if (scalar !== null) {
      if (path) {
        rows.push({ path, value: scalar });
      }
      return;
    }

    if (Array.isArray(current)) {
      const scalarItems = current.map(formatPayloadScalar).filter((item): item is string => item !== null);
      if (scalarItems.length === current.length && path) {
        rows.push({ path, value: truncateSummaryValue(scalarItems.slice(0, 6).join(', ')) });
        return;
      }
      current.slice(0, 4).forEach((item, index) => visit(item, path ? `${path}[${index}]` : `[${index}]`, depth + 1));
      return;
    }

    if (current && typeof current === 'object') {
      if (seen.has(current)) {
        return;
      }
      seen.add(current);
      Object.entries(current as Record<string, unknown>).forEach(([key, item]) => {
        visit(item, path ? `${path}.${key}` : key, depth + 1);
      });
    }
  }

  visit(value, '', 0);
  return rows;
}

function formatPayloadScalar(value: unknown): string | null {
  if (typeof value === 'string') {
    return value ? truncateSummaryValue(value) : '(empty)';
  }
  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }
  if (value === null) {
    return 'null';
  }
  return null;
}

function truncateSummaryValue(value: string): string {
  return value.length > 140 ? `${value.slice(0, 137)}...` : value;
}

function operationCategoriesForTab(tab: OperationTabKey): OperationDescriptor['category'][] {
  if (tab === 'maintenance') {
    return ['backup', 'restore', 'migration'];
  }
  return [tab];
}

function manifestPathForEvidencePack(pack: EvidencePackSummary | null | undefined): string {
  return pack?.exportPath ? `${pack.exportPath.replace(/\/$/, '')}/manifest.json` : '';
}

function mergeRunStatusWithSessionState(runStatusPayload: unknown, sessionStatePayload: unknown): unknown {
  const runRecord = asRecord(runStatusPayload);
  const sessionRecord = asRecord(sessionStatePayload);
  const next: Record<string, unknown> = { ...runRecord };
  const sessionJob = asRecord(sessionRecord.job);
  const sessionComputerUse = asRecord(sessionRecord.computer_use);

  if (Object.keys(sessionJob).length > 0) {
    next.job = { ...asRecord(runRecord.job), ...sessionJob };
  }
  if (Object.keys(sessionComputerUse).length > 0) {
    next.computer_use = { ...asRecord(runRecord.computer_use), ...sessionComputerUse };
  }

  return next;
}

function AppContent({ settings, updateSettings }: AppContentProps) {
  const previewMode = isBridgePreviewMode();
  const rendererArtifactFeatureFlags = resolveArtifactFeatureFlags(import.meta.env, {
    // These are bundled fallback adapters. Deployment policy is still enforced
    // by the backend rollout snapshot and the explicit VITE enable flags.
    spreadsheet: true,
    canvas: true,
  });

  const [activeView, setActiveView] = useState<ViewKey>('workspace');
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [runTab, setRunTab] = useState<RunTabKey>('overview');
  const [operationTab, setOperationTab] = useState<OperationTabKey>('identity');
  const [automationMode, setAutomationMode] = useState<AutomationMode>('assisted');
  const [computerUseRuntimeChoice, setComputerUseRuntimeChoice] =
    useState<ComputerUseRuntimeChoice>('vision-first');
  const [stepMode, setStepMode] = useState(true);
  const [askBeforeExternal, setAskBeforeExternal] = useState(true);
  const [askBeforeDeletion, setAskBeforeDeletion] = useState(true);
  const [askBeforeSend, setAskBeforeSend] = useState(true);

  const [handshakeData, setHandshakeData] = useState<unknown>(null);
  const [artifactCapabilitySnapshot, setArtifactCapabilitySnapshot] = useState<ArtifactRuntimeCapabilitySnapshot | null>(null);
  const [artifactCapabilityStatus, setArtifactCapabilityStatus] = useState<'loading' | 'ready' | 'failed'>(
    previewMode ? 'ready' : 'loading',
  );
  const [configData, setConfigData] = useState<unknown>(null);
  const artifactFeatureFlags = useMemo(
    () => resolveEffectiveArtifactFeatureFlags(
      rendererArtifactFeatureFlags,
      artifactCapabilityStatus === 'ready' ? artifactCapabilitySnapshot : null,
      previewMode,
    ),
    [artifactCapabilitySnapshot, artifactCapabilityStatus, previewMode, rendererArtifactFeatureFlags],
  );
  const [handshakeError, setHandshakeError] = useState<BridgeErrorPayload | null>(null);
  const [controlPlaneDoctor, setControlPlaneDoctor] = useState<unknown>(null);
  const [controlPlaneAgents, setControlPlaneAgents] = useState<unknown>({ agents: [] });
  const [controlPlanePolicy, setControlPlanePolicy] = useState<unknown>(null);
  const [controlPlaneClaims, setControlPlaneClaims] = useState<unknown>({ claims: [] });
  const [controlPlaneEvidenceVerifyResult, setControlPlaneEvidenceVerifyResult] = useState<unknown>(null);
  const [controlPlaneSnapshotVm, setControlPlaneSnapshotVm] =
    useState<PageViewModel<ControlPlaneSnapshot> | null>(null);

  const [approvalsData, setApprovalsData] = useState<unknown>({ pending: [] });
  const [selectedApprovalId, setSelectedApprovalId] = useState('');
  const [approvalDetail, setApprovalDetail] = useState<unknown>(null);

  const [runsData, setRunsData] = useState<unknown>({ items: [] });
  const [selectedRunId, setSelectedRunId] = useState('');
  const [runStatus, setRunStatus] = useState<unknown>(null);
  const [computerUseState, setComputerUseState] = useState<unknown>(null);
  const [computerUseSummaryData, setComputerUseSummaryData] = useState<unknown>(null);
  const [runReplay, setRunReplay] = useState<unknown>(null);
  const [artifactsByName, setArtifactsByName] = useState<Record<string, unknown>>({});
  const [selectedArtifactName, setSelectedArtifactName] = useState<string>('status.json');
  const [artifactEditorSelection, setArtifactEditorSelection] = useState<ArtifactSelection | null>(null);
  const [governedArtifactContext, setGovernedArtifactContext] = useState<Record<string, unknown> | null>(null);
  const [showRawArtifact, setShowRawArtifact] = useState(false);
  const [exportModalOpen, setExportModalOpen] = useState(false);
  const [exportPath, setExportPath] = useState('');
  const [exportSubmitting, setExportSubmitting] = useState(false);

  const [events, setEvents] = useState<unknown[]>([]);
  const [eventsCursor, setEventsCursor] = useState(0);
  const [eventsWarning, setEventsWarning] = useState('');
  const [sessionEventFilter, setSessionEventFilter] = useState<SessionEventFilter>('all');
  const [sessionEventVisibleLimit, setSessionEventVisibleLimit] = useState(20);
  const [sessionEventsLoadingMore, setSessionEventsLoadingMore] = useState(false);
  const [sessionEventsHasMore, setSessionEventsHasMore] = useState(false);
  const cursorRef = useRef(0);

  const [taskForm, setTaskForm] = useState<TaskFormState>({
    request: '',
    specPath: '',
    caseId: '',
    jobId: '',
    provider: '',
    fallbackProvider: '',
    model: '',
    hfModelId: '',
  });
  const [resumeForm, setResumeForm] = useState({
    specPath: '',
    resumeJobId: '',
    provider: '',
    fallbackProvider: '',
    model: '',
    hfModelId: '',
  });
  const [operationsForm, setOperationsForm] = useState<OperationsFormState>({
    permission: 'runtime.run',
    verifyPath: '',
    supportOutput: '',
    backupOutputDir: '',
    backupVerifyDir: '',
    restoreVerifyDir: '',
    readinessReport: 'artifacts/ga_readiness_report.json',
    readinessQualificationReport: 'artifacts/qualification_report.json',
    qualificationMode: 'mixed',
    qualificationOutputRoot: 'artifacts/qualification',
    qualificationWorkloads: '',
    qualificationMergeFromReport: '',
    qualificationSoakHours: '6',
    keyNextKeyId: '',
    keyActivateAt: '',
    keyRetireAfter: '',
  });
  const [operationOutputs, setOperationOutputs] = useState<Record<string, unknown>>({});
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [dismissedNotifications, setDismissedNotifications] = useState<string[]>([]);

  const locale = resolveLocale(settings.locale);
  const t = dictionaries[locale];
  const assistantCopy: AssistantViewCopy = {
    title: t.assistantTitle,
    subtitle: t.assistantSubtitle,
    welcomeTitle: t.assistantWelcomeTitle,
    badgeLabel: t.assistantBadgeLabel,
    newChat: t.assistantNewChat,
    messageLabel: t.assistantMessageLabel,
    sendLabel: t.assistantSendLabel,
    composerPlaceholder: t.assistantComposerPlaceholder,
    readOnlyByDefault: t.assistantReadOnlyByDefault,
    sensitiveDataNotice: t.assistantSensitiveDataNotice,
    dryRunSafe: t.assistantDryRunSafe,
    referencedRuns: t.assistantReferencedRuns,
    systemHealth: t.assistantSystemHealth,
    suggestedPromptsLabel: t.assistantSuggestedPromptsLabel,
    suggestedPrompts: [
      t.assistantPromptSummarizeErrors,
      t.assistantPromptDraftRemediation,
      t.assistantPromptReviewPolicies,
      t.assistantPromptAnalyzeRun,
    ],
    awaitingContextTitle: t.assistantAwaitingContextTitle,
    awaitingContextBody: t.assistantAwaitingContextBody,
    noReferencedRunTitle: t.assistantNoReferencedRunTitle,
    noReferencedRunBody: t.assistantNoReferencedRunBody,
    approvalLifecycle: t.assistantApprovalLifecycle,
    approvalGated: t.assistantApprovalGated,
    approvalLifecycleBody: t.assistantApprovalLifecycleBody,
  };

  const handshakeRecord = asRecord(handshakeData);
  const capabilities = asRecord(handshakeRecord.capabilities);
  const features = asRecord(capabilities.features);
  const doctor = asRecord(handshakeRecord.doctor);
  const supportedProfiles = readArray(capabilities, 'profiles');
  const contractMismatch = hasContractMismatch(handshakeData);
  const computerUseCapability = getComputerUseCapability(handshakeData);
  const computerUseVisionCapability = getComputerUseVisionRuntimeCapability(handshakeData);
  const computerUseVisionPlatformStatuses = Object.values(computerUseVisionCapability.platforms);
  const computerUseLiveEnabled = isComputerUseSessionStartAllowed(handshakeData, computerUseRuntimeChoice);
  const computerUseVisionBlockers = getComputerUseVisionRuntimeBlockers(handshakeData);
  const computerUseDisabledReason = computerUseLiveEnabled
    ? ''
    : computerUseRuntimeChoice === 'legacy-pilot'
      ? computerUseCapability.summary ||
        (computerUseCapability.reasonCode
          ? `Computer-use legacy pilot disabled: ${computerUseCapability.reasonCode}`
          : 'Computer-use legacy pilot requires an explicit qualified macOS pilot handshake.')
      : computerUseVisionBlockers.length > 0
        ? `Computer-use vision runtime blocked: ${computerUseVisionBlockers.join(', ')}`
        : computerUseVisionCapability.summary ||
          'Computer-use vision runtime requires a qualified fail-closed capability handshake.';
  const operatorIdValid = isOperatorIdValid(settings.operatorId);
  const canMutate = canMutateWithOperatorId(settings.operatorId, contractMismatch);

  const pendingApprovals = readArray(asRecord(approvalsData), 'pending');
  const runItems = readArray(asRecord(runsData), 'items');
  const selectedApproval = asRecord(approvalDetail);
  const runStatusRecord = asRecord(runStatus);
  const runJob = asRecord(runStatusRecord.job);
  const runComputerUse = asRecord(runStatusRecord.computer_use);
  const controlRegistry = asRecord(asRecord(computerUseState).registry);
  const runStatusValue = readString(runJob, 'status');
  const isComputerUseRun =
    Object.keys(runComputerUse).length > 0 || readString(runJob, 'team_id') === 'imperaos-computer-use';
  const linkedApprovals = pendingApprovals.filter(
    (item) => readString(asRecord(item), 'run_id') === selectedRunId,
  );
  const driftEvents = events.filter((item) => {
    const name = readString(asRecord(item), 'event').toLowerCase();
    return name.includes('snapshot_drift') || name.includes('approval_stale') || name.includes('stale_');
  });
  const configRecord = asRecord(configData);
  const assistantRuntimeSettings = getAssistantRuntimeSettings(settings);
  const assistantRuntimeValidationMessage = validateAssistantRuntimeSettings(assistantRuntimeSettings);
  const assistantModelProvider = settings.assistantProvider.trim()
    ? (settings.assistantProvider.trim() as AssistantProviderKind)
    : 'all';
  const assistantModels = useAssistantModels({
    settings,
    profile: settings.profile,
    provider: assistantModelProvider,
  });
  const assistantResolvedConfig = asRecord(asRecord(configRecord.resolved));
  const profileDefaultLabel = 'profile default';
  const assistantRuntimeSummary: AssistantRuntimeSummary = {
    selectedProvider: settings.assistantProvider.trim() || profileDefaultLabel,
    selectedModel: settings.assistantModel.trim() || profileDefaultLabel,
    selectedFallbackProvider: settings.assistantFallbackProvider.trim() || profileDefaultLabel,
    selectedHfModelId: settings.assistantHfModelId.trim() || profileDefaultLabel,
    effectiveProvider:
      settings.assistantProvider.trim() || readString(assistantResolvedConfig, 'llm_provider', profileDefaultLabel),
    effectiveModel:
      settings.assistantModel.trim() || readString(assistantResolvedConfig, 'model_name', profileDefaultLabel),
    effectiveHfModelId:
      settings.assistantHfModelId.trim() || readString(assistantResolvedConfig, 'hf_model_id', profileDefaultLabel),
  };

  function pushToast(kind: Toast['kind'], text: string) {
    const id = Date.now() + Math.floor(Math.random() * 1000);
    setToasts((prev) => [...prev, { id, kind, text }]);
    window.setTimeout(() => {
      setToasts((prev) => prev.filter((item) => item.id !== id));
    }, 4200);
  }

  async function refreshHandshake() {
    try {
      const payload = await handshake(settings);
      setHandshakeData(payload);
      setHandshakeError(null);
    } catch (error) {
      setHandshakeError(getErrorPayload(error));
    }
  }

  async function refreshConfig() {
    try {
      const payload = await resolveConfig(
        settings,
        assistantRuntimeValidationMessage ? undefined : assistantRuntimeOptionsFromSettings(settings),
      );
      setConfigData(payload);
    } catch (error) {
      const parsed = getErrorPayload(error);
      if (parsed) {
        pushToast('error', `${parsed.code}: ${parsed.message}`);
      }
    }
  }

  async function refreshApprovals() {
    try {
      const payload = await fetchApprovals(settings);
      setApprovalsData(payload);
      const pending = readArray(asRecord(payload), 'pending');
      if (!selectedApprovalId && pending.length > 0) {
        setSelectedApprovalId(readString(asRecord(pending[0]), 'approval_id'));
      }
    } catch (error) {
      const parsed = getErrorPayload(error);
      if (parsed) {
        pushToast('error', `${parsed.code}: ${parsed.message}`);
      }
    }
  }

  async function refreshRuns() {
    try {
      const payload = await listRuns(settings);
      setRunsData(payload);
      const items = readArray(asRecord(payload), 'items');
      if (!selectedRunId && items.length > 0) {
        setSelectedRunId(readString(asRecord(items[0]), 'job_id'));
      }
      void refreshComputerUseSummary();
    } catch (error) {
      const parsed = getErrorPayload(error);
      if (parsed) {
        pushToast('error', `${parsed.code}: ${parsed.message}`);
      }
    }
  }

  async function refreshComputerUseSummary() {
    try {
      const payload = await getComputerUseSummary(settings, 20);
      setComputerUseSummaryData(payload);
    } catch (error) {
      const parsed = getErrorPayload(error);
      if (parsed) {
        setComputerUseSummaryData({ status: 'error', error: parsed.message, code: parsed.code });
      }
    }
  }

  async function refreshControlPlane() {
    try {
      const [snapshotVm, doctorPayload, agentsPayload, claimsPayload, policyPayload] = await Promise.all([
        loadControlPlaneSnapshot(
          {
            getControlPlaneSnapshot: () => fetchControlPlaneSnapshot(settings),
          },
          { forceRefresh: true },
        ),
        fetchControlPlaneDoctor(settings).catch((error) => ({ status: 'blocked', error: getErrorPayload(error)?.message })),
        listControlPlaneAgents(settings).catch(() => ({ agents: [] })),
        verifyControlPlaneClaims(settings).catch(() => ({ claims: [] })),
        simulateControlPlanePolicy(settings, 'governed-ops').catch(() => null),
      ]);
      setControlPlaneSnapshotVm(snapshotVm);
      setControlPlaneDoctor(doctorPayload);
      setControlPlaneAgents(agentsPayload);
      setControlPlaneClaims(claimsPayload);
      setControlPlanePolicy(policyPayload);
    } catch (error) {
      const parsed = getErrorPayload(error);
      if (parsed) {
        pushToast('error', `${parsed.code}: ${parsed.message}`);
      }
    }
  }

  async function refreshCore() {
    await Promise.all([
      refreshHandshake(),
      refreshConfig(),
      refreshApprovals(),
      refreshRuns(),
      refreshControlPlane(),
    ]);
  }

  async function loadApprovalDetail(approvalId: string): Promise<unknown | null> {
    if (!approvalId) {
      setApprovalDetail(null);
      return null;
    }
    try {
      const payload = await showApproval(settings, approvalId);
      setApprovalDetail(payload);
      return payload;
    } catch (error) {
      const parsed = getErrorPayload(error);
      if (parsed) {
        pushToast('error', `${parsed.code}: ${parsed.message}`);
      }
      return null;
    }
  }

  async function loadRunContext(runId: string, notifyErrors = true) {
    if (!runId) {
      return;
    }

    try {
      const [statusPayload, replayPayload, sessionStatePayload] = await Promise.all([
        getRunStatus(settings, runId),
        getRunReplay(settings, runId),
        getComputerUseSessionState(settings, runId).catch(() => null),
      ]);
      setRunStatus(mergeRunStatusWithSessionState(statusPayload, sessionStatePayload));
      setComputerUseState(sessionStatePayload);
      setRunReplay(replayPayload);

      const nextArtifacts: Record<string, unknown> = {};
      await Promise.all(
        ARTIFACT_NAMES.map(async (name) => {
          try {
            nextArtifacts[name] = await readArtifact(settings, runId, name);
          } catch {
            nextArtifacts[name] = { artifactName: name, payload: {} };
          }
        }),
      );
      setArtifactsByName(nextArtifacts);
    } catch (error) {
      if (!notifyErrors) {
        return;
      }
      const parsed = getErrorPayload(error);
      if (parsed) {
        pushToast('error', `${parsed.code}: ${parsed.message}`);
      }
    }
  }

  useEffect(() => {
    void refreshCore();
  }, [settings.mode, settings.cliPath, settings.bundledPythonPath, settings.profile, settings.rootDir]);

  useEffect(() => {
    if (previewMode || !rendererArtifactFeatureFlags.workspace) {
      setArtifactCapabilitySnapshot(null);
      setArtifactCapabilityStatus('ready');
      return;
    }
    let cancelled = false;
    setArtifactCapabilitySnapshot(null);
    setArtifactCapabilityStatus('loading');
    void artifactBridge.getRuntimeCapabilitySnapshot()
      .then((snapshot) => {
        if (!cancelled) {
          setArtifactCapabilitySnapshot(snapshot);
          setArtifactCapabilityStatus('ready');
        }
      })
      .catch(() => {
        if (!cancelled) {
          setArtifactCapabilitySnapshot(null);
          setArtifactCapabilityStatus('failed');
        }
      });
    return () => { cancelled = true; };
  }, [previewMode, rendererArtifactFeatureFlags.workspace, settings.profile, settings.rootDir]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void refreshConfig();
    }, 250);
    return () => window.clearTimeout(timer);
  }, [
    settings.assistantProvider,
    settings.assistantFallbackProvider,
    settings.assistantModel,
    settings.assistantHfModelId,
  ]);

  useEffect(() => {
    if (!resumeForm.specPath && taskForm.specPath) {
      setResumeForm((prev) => ({ ...prev, specPath: taskForm.specPath }));
    }
  }, [resumeForm.specPath, taskForm.specPath]);

  useEffect(() => {
    if (!settings.debugRaw) {
      setShowRawArtifact(false);
    }
  }, [settings.debugRaw]);

  useEffect(() => {
    void loadApprovalDetail(selectedApprovalId);
  }, [selectedApprovalId, settings.profile]);

  useEffect(() => {
    if (!selectedRunId) {
      return;
    }
    setEvents([]);
    setEventsCursor(0);
    cursorRef.current = 0;
    setEventsWarning('');
    setSessionEventFilter('all');
    setSessionEventVisibleLimit(20);
    setSessionEventsHasMore(false);
    setComputerUseState(null);
    void loadRunContext(selectedRunId);
  }, [selectedRunId, settings.profile, settings.rootDir]);

  useEffect(() => {
    if (!selectedRunId) {
      return;
    }

    let cancelled = false;
    let timer: number | null = null;

    const poll = async () => {
      if (cancelled) {
        return;
      }

      try {
        const [statusPayload, sessionStatePayload] = await Promise.all([
          getRunStatus(settings, selectedRunId),
          getComputerUseSessionState(settings, selectedRunId).catch(() => null),
        ]);
        setRunStatus(mergeRunStatusWithSessionState(statusPayload, sessionStatePayload));
        setComputerUseState(sessionStatePayload);

        const stream = await tailEvents(settings, selectedRunId, cursorRef.current, 96 * 1024, 200);
        if (stream.reset) {
          setEvents(stream.events);
        } else if (stream.events.length > 0) {
          setEvents((prev) => [...prev, ...stream.events]);
        }
        setSessionEventsHasMore(stream.events.length > 0 || stream.truncated);

        cursorRef.current = stream.nextCursor;
        setEventsCursor(stream.nextCursor);
        if (stream.badLineCount > 0 || stream.truncated) {
          setEventsWarning(
            `events tail warning: badLineCount=${stream.badLineCount}, truncated=${String(stream.truncated)}`,
          );
        } else {
          setEventsWarning('');
        }

        const liveStatus = readString(asRecord(asRecord(statusPayload).job), 'status');
        const cadence = liveStatus === 'running' ? 1500 : liveStatus === 'blocked' ? 3500 : 6000;
        timer = window.setTimeout(() => {
          void poll();
        }, cadence);
      } catch (error) {
        const parsed = getErrorPayload(error);
        if (parsed) {
          setEventsWarning(`${parsed.code}: ${parsed.message}`);
        }
        timer = window.setTimeout(() => {
          void poll();
        }, 6000);
      }
    };

    void poll();

    return () => {
      cancelled = true;
      if (timer !== null) {
        window.clearTimeout(timer);
      }
    };
  }, [selectedRunId, settings.profile, settings.rootDir]);

  async function onDecideApproval(approve: boolean) {
    if (!selectedApprovalId || !canMutate) {
      pushToast('error', t.setOperatorId);
      return;
    }

    const actor = actorForOperator(settings.operatorId);
    const label = approve ? t.approve : t.reject;
    const confirmed = window.confirm(`${label}\n${selectedApprovalId}\n${actor}`);
    if (!confirmed) {
      return;
    }

    try {
      await decideApproval(settings, selectedApprovalId, approve, settings.operatorId, 'operator workspace action');
      pushToast('ok', `${label} OK`);
      await Promise.all([refreshApprovals(), refreshRuns()]);
      if (selectedRunId) {
        await loadRunContext(selectedRunId, false);
      }
    } catch (error) {
      const parsed = getErrorPayload(error);
      if (parsed) {
        pushToast('error', `${parsed.code}: ${parsed.message}`);
      }
    }
  }

  async function onExecuteApproval() {
    if (!selectedApprovalId || !canMutate) {
      pushToast('error', t.setOperatorId);
      return;
    }

    const actor = actorForOperator(settings.operatorId);
    const confirmed = window.confirm(`${t.execute}\n${selectedApprovalId}\n${actor}`);
    if (!confirmed) {
      return;
    }

    try {
      await executeApproval(settings, selectedApprovalId, settings.operatorId);
      pushToast('ok', `${t.execute} OK`);
      await Promise.all([refreshApprovals(), refreshRuns()]);
      if (selectedRunId) {
        await loadRunContext(selectedRunId, false);
      }
    } catch (error) {
      const parsed = getErrorPayload(error);
      if (parsed) {
        pushToast('error', `${parsed.code}: ${parsed.message}`);
      }
    }
  }

  async function onSubmitTask() {
    if (!taskForm.specPath.trim() || !taskForm.request.trim()) {
      pushToast('error', t.submitValidation);
      return;
    }

    try {
      const payload = await submitTeamRun(settings, {
        specPath: taskForm.specPath,
        request: taskForm.request,
        caseId: taskForm.caseId || undefined,
        jobId: taskForm.jobId || undefined,
        provider: taskForm.provider || undefined,
        fallbackProvider: taskForm.fallbackProvider || undefined,
        model: taskForm.model || undefined,
        hfModelId: taskForm.hfModelId || undefined,
        safetyOptions: {
          askBeforeExternalAction: askBeforeExternal,
          askBeforeDelete: askBeforeDeletion,
          askBeforeSend,
        },
      });
      const jobId = extractJobId(payload);
      if (jobId) {
        setSelectedRunId(jobId);
        setRunStatus({ job: { job_id: jobId, status: 'pending' } });
      }
      setActiveView('workspace');
      pushToast('ok', `${t.submitRun} OK`);
      void refreshRuns();
      window.setTimeout(() => {
        void refreshRuns();
      }, 1200);
    } catch (error) {
      const parsed = getErrorPayload(error);
      if (parsed) {
        pushToast('error', `${parsed.code}: ${parsed.message}`);
      }
    }
  }

  async function onSubmitComputerUseSession() {
    if (!computerUseLiveEnabled) {
      pushToast('error', computerUseDisabledReason);
      return;
    }

    if (!taskForm.request.trim()) {
      pushToast('error', t.sessionValidation);
      return;
    }

    const mode: 'dry_run' | 'step_approval' | 'execute' =
      automationMode === 'assisted' || stepMode ? 'step_approval' : 'execute';

    try {
      const payload = await submitComputerUseRun(settings, {
        request: taskForm.request,
        caseId: taskForm.caseId || undefined,
        jobId: taskForm.jobId || undefined,
        mode,
        runtime: computerUseRuntimeChoice,
        provider: taskForm.provider || undefined,
        fallbackProvider: taskForm.fallbackProvider || undefined,
        model: taskForm.model || undefined,
        hfModelId: taskForm.hfModelId || undefined,
        safetyOptions: {
          askBeforeExternalAction: askBeforeExternal,
          askBeforeDelete: askBeforeDeletion,
          askBeforeSend,
        },
      });
      const jobId = extractJobId(payload);
      if (jobId) {
        setSelectedRunId(jobId);
        setRunStatus({
          job: {
            job_id: jobId,
            request: taskForm.request,
            status: 'running',
            team_id: 'imperaos-computer-use',
          },
          computer_use: {
            mode,
            runtime: computerUseRuntimeChoice,
            lifecycle_state: 'running',
            stage: 'plan',
            paused: false,
            stopped: false,
          },
        });
      }
      setActiveView('workspace');
      pushToast('ok', `${t.startSession} OK`);
      void refreshRuns();
      window.setTimeout(() => {
        void refreshRuns();
        if (jobId) {
          void loadRunContext(jobId, false);
        }
      }, 1200);
    } catch (error) {
      const parsed = getErrorPayload(error);
      if (parsed) {
        pushToast('error', `${parsed.code}: ${parsed.message}`);
      }
    }
  }

  async function onResumeRun() {
    if (!selectedRunId || !resumeForm.specPath.trim()) {
      pushToast('error', t.resumeValidation);
      return;
    }

    try {
      const payload = await resumeTeamRun(settings, {
        specPath: resumeForm.specPath,
        sourceJobId: selectedRunId,
        resumeJobId: resumeForm.resumeJobId || undefined,
        provider: resumeForm.provider || undefined,
        fallbackProvider: resumeForm.fallbackProvider || undefined,
        model: resumeForm.model || undefined,
        hfModelId: resumeForm.hfModelId || undefined,
      });
      const jobId = extractJobId(payload);
      if (jobId) {
        setSelectedRunId(jobId);
      }
      pushToast('ok', `${t.resumeRun} OK`);
      void refreshRuns();
      window.setTimeout(() => {
        void refreshRuns();
      }, 1200);
    } catch (error) {
      const parsed = getErrorPayload(error);
      if (parsed) {
        pushToast('error', `${parsed.code}: ${parsed.message}`);
      }
    }
  }

  async function onControlSession(command: 'pause' | 'resume' | 'stop') {
    if (!selectedRunId || !isComputerUseRun) {
      return;
    }

    try {
      const label = command === 'pause' ? t.pause : command === 'resume' ? t.resumeRun : t.stopNow;
      let controlPayload: unknown;
      if (command === 'pause') {
        controlPayload = await pauseComputerUseSession(settings, selectedRunId);
      } else if (command === 'resume') {
        controlPayload = await resumeComputerUseSession(settings, selectedRunId);
      } else {
        const confirmed = window.confirm(`${t.stopNow}\n${selectedRunId}`);
        if (!confirmed) {
          return;
        }
        controlPayload = await stopComputerUseSession(settings, selectedRunId);
      }

      const statePayload = await getComputerUseSessionState(settings, selectedRunId).catch(() => null);
      setComputerUseState(statePayload);
      const controlRecord = asRecord(controlPayload);
      const outcome = readString(controlRecord, 'outcome', 'accepted');
      const reason = readString(controlRecord, 'reason');
      const outcomeLabel = humanizeCode(outcome);
      if (outcome === 'rejected') {
        pushToast('error', `${label}: ${outcomeLabel}${reason ? ` (${humanizeCode(reason)})` : ''}`);
      } else {
        pushToast('ok', `${label}: ${outcomeLabel}${reason ? ` (${humanizeCode(reason)})` : ''}`);
      }
      window.setTimeout(() => {
        void loadRunContext(selectedRunId, false);
        void refreshRuns();
      }, 500);
    } catch (error) {
      const parsed = getErrorPayload(error);
      if (parsed) {
        pushToast('error', `${parsed.code}: ${parsed.message}`);
      }
    }
  }

  function onExportArtifacts() {
    if (!selectedRunId) {
      return;
    }
    setExportPath((current) => current || `./exports/${selectedRunId}`);
    setExportModalOpen(true);
  }

  async function onConfirmExportArtifacts(target: string) {
    if (!selectedRunId || !target.trim()) {
      return;
    }

    setExportSubmitting(true);
    try {
      await exportRunArtifacts(settings, selectedRunId, target.trim());
      setExportPath(target.trim());
      setExportModalOpen(false);
      pushToast('ok', t.exportDone);
    } catch (error) {
      const parsed = getErrorPayload(error);
      if (parsed) {
        pushToast('error', `${parsed.code}: ${parsed.message}`);
      }
    } finally {
      setExportSubmitting(false);
    }
  }

  async function onLoadMoreSessionEvents() {
    if (filteredSessionEvents.length > sessionEventVisibleLimit) {
      setSessionEventVisibleLimit((value) => value + 20);
      return;
    }
    if (!selectedRunId || sessionEventsLoadingMore) {
      return;
    }

    setSessionEventsLoadingMore(true);
    try {
      const stream = await tailEvents(settings, selectedRunId, cursorRef.current, 96 * 1024, 200);
      if (stream.reset) {
        setEvents(stream.events);
      } else if (stream.events.length > 0) {
        setEvents((prev) => [...prev, ...stream.events]);
      }
      cursorRef.current = stream.nextCursor;
      setEventsCursor(stream.nextCursor);
      setSessionEventsHasMore(stream.events.length > 0 || stream.truncated);
      if (stream.events.length === 0 && !stream.truncated) {
        pushToast('ok', 'Yeni oturum olayı yok.');
      }
    } catch (error) {
      const parsed = getErrorPayload(error);
      if (parsed) {
        pushToast('error', `${parsed.code}: ${parsed.message}`);
      }
    } finally {
      setSessionEventsLoadingMore(false);
    }
  }

  async function onVerifyEvidencePack() {
    if (!selectedEvidenceManifestPath) {
      pushToast('error', 'No evidence manifest is available to verify.');
      return;
    }

    try {
      const payload = await verifyControlPlaneEvidence(settings, selectedEvidenceManifestPath);
      setControlPlaneEvidenceVerifyResult(payload);
      pushToast('ok', 'Evidence verification completed');
    } catch (error) {
      const parsed = getErrorPayload(error);
      if (parsed) {
        setControlPlaneEvidenceVerifyResult(parsed);
        pushToast('error', `${parsed.code}: ${parsed.message}`);
      }
    }
  }

  async function onApproveAndContinue() {
    if (!selectedApprovalId || !canMutate) {
      pushToast('error', t.setOperatorId);
      return;
    }

    const actor = actorForOperator(settings.operatorId);
    const confirmed = window.confirm(`Onayla ve Devam Et\n${selectedApprovalId}\n${actor}`);
    if (!confirmed) {
      return;
    }

    try {
      await decideApproval(settings, selectedApprovalId, true, settings.operatorId, 'mission control approval');
      await executeApproval(settings, selectedApprovalId, settings.operatorId);
      pushToast('ok', 'Onay akışı tamamlandı');
      await Promise.all([refreshApprovals(), refreshRuns()]);
      if (selectedRunId) {
        await loadRunContext(selectedRunId, false);
      }
    } catch (error) {
      const parsed = getErrorPayload(error);
      if (parsed) {
        pushToast('error', `${parsed.code}: ${parsed.message}`);
      }
    }
  }

  async function runOperation(key: string, task: () => Promise<unknown>) {
    try {
      const payload = await task();
      setOperationOutputs((prev) => ({ ...prev, [key]: payload }));
    } catch (error) {
      const parsed = getErrorPayload(error);
      if (parsed) {
        setOperationOutputs((prev) => ({ ...prev, [key]: parsed }));
        pushToast('error', `${parsed.code}: ${parsed.message}`);
      }
    }
  }

  function confirmRawDisclosure(label: string): boolean {
    if (!settings.debugRaw) {
      pushToast('error', 'Ham payload modu ayarlardan açılmalı.');
      return false;
    }
    return window.confirm(`${label}\nHam payload hassas bilgi içerebilir. Devam edilsin mi?`);
  }

  const selectedArtifactPayload = artifactsByName[selectedArtifactName];
  const parsedArtifact = asRecord(selectedArtifactPayload);
  const artifactValue = parsedArtifact.payload;
  const operationOutput = operationOutputs[operationTab] ?? {};
  const controlPlaneSnapshot = controlPlaneSnapshotVm && !controlPlaneSnapshotVm.error ? controlPlaneSnapshotVm.data : null;
  const operationDescriptors = controlPlaneSnapshot?.operations ?? [];
  const evidencePacks = controlPlaneSnapshot?.evidencePacks ?? [];
  const pilotLaunch = controlPlaneSnapshot?.pilotLaunch ?? null;
  const codeIntelligence = controlPlaneSnapshot?.codeIntelligence ?? null;
  const pilotOperations = controlPlaneSnapshot?.pilotOperations ?? null;
  const designPartnerBeta = controlPlaneSnapshot?.designPartnerBeta ?? null;
  const providerGovernance = controlPlaneSnapshot?.providerGovernance ?? null;
  const providerRuntime = controlPlaneSnapshot?.providerRuntime ?? null;
  const targetEvidenceClosure = controlPlaneSnapshot?.targetEvidenceClosure ?? null;
  const memoryGovernance = controlPlaneSnapshot?.memoryGovernance ?? null;
  const memoryRuntime = controlPlaneSnapshot?.memoryRuntime ?? null;
  const memorySync = controlPlaneSnapshot?.memorySync ?? null;
  const memoryAuthority = controlPlaneSnapshot?.memoryAuthority ?? null;
  const memorySemanticIndex = controlPlaneSnapshot?.memorySemanticIndex ?? null;
  const memoryPolicyEnforcement = controlPlaneSnapshot?.memoryPolicyEnforcement ?? null;
  const governedPilotWorkflow = controlPlaneSnapshot?.governedPilotWorkflow ?? null;
  const designPartnerFieldEvidence = controlPlaneSnapshot?.designPartnerFieldEvidence ?? null;
  const designPartnerHandoff = controlPlaneSnapshot?.designPartnerHandoff ?? null;
  const mainlineRcFreeze = controlPlaneSnapshot?.mainlineRcFreeze ?? null;
  const rcGateEvidence = controlPlaneSnapshot?.rcGateEvidence ?? null;
  const rcReleaseDecision = controlPlaneSnapshot?.rcReleaseDecision ?? null;
  const enterpriseWorkspace = controlPlaneSnapshot?.enterpriseWorkspace ?? null;
  const selectedEvidencePack = evidencePacks[0] ?? null;
  const selectedEvidenceManifestPath = manifestPathForEvidencePack(selectedEvidencePack);
  const workspaceSnapshot = buildWorkspaceSnapshot({
    runStatus,
    sessionState: computerUseState,
    events,
    pendingApprovals,
    linkedApprovals,
    artifactsByName,
  });
  const workspaceProgress = readWorkspaceProgress(workspaceSnapshot);
  const canResumeSession =
    Boolean(selectedRunId) && isComputerUseRun && computerUseLiveEnabled && workspaceSnapshot.runtimeState.canResume;

  function workspaceStageLabel(stage: WorkspaceStageKey): string {
    return {
      planning: t.stagePlanning,
      reading_screen: t.stageReadingScreen,
      waiting_approval: t.stageWaitingApproval,
      executing: t.stageExecuting,
      verifying: t.stageVerifying,
      blocked: t.stageBlocked,
      done: t.stageDone,
    }[stage];
  }

  function formatTimestamp(value: string, fallback = '-'): string {
    if (!value) {
      return fallback;
    }
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) {
      return value;
    }
    return new Intl.DateTimeFormat(locale === 'tr' ? 'tr-TR' : 'en-US', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    }).format(parsed);
  }

  function formatClock(value: string, fallback: string): string {
    if (!value) {
      return fallback;
    }
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) {
      return fallback;
    }
    return new Intl.DateTimeFormat(locale === 'tr' ? 'tr-TR' : 'en-US', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    }).format(parsed);
  }

  function sessionEventCategory(item: SessionEventItem): SessionEventFilter {
    const haystack = `${item.title} ${item.body} ${item.tag}`.toLowerCase();
    if (haystack.includes('assistant')) {
      return 'assistant';
    }
    if (haystack.includes('computer') || haystack.includes('vision')) {
      return 'computer_use';
    }
    if (haystack.includes('approval') || haystack.includes('onay')) {
      return 'approval';
    }
    if (haystack.includes('error') || haystack.includes('failed') || haystack.includes('hata')) {
      return 'error';
    }
    if (haystack.includes('warn') || haystack.includes('blocked') || haystack.includes('uyarı')) {
      return 'warning';
    }
    return 'status';
  }

  function eventRecordToSessionEventItem(value: unknown, index: number): SessionEventItem {
    const record = asRecord(value);
    const data = asRecord(record.data);
    const eventName =
      readString(record, 'event') ||
      readString(record, 'type') ||
      readString(data, 'event') ||
      `runtime_event_${index + 1}`;
    const message =
      readString(record, 'message') ||
      readString(record, 'summary') ||
      readString(data, 'message') ||
      readString(data, 'summary') ||
      eventName;
    const timestamp =
      readString(record, 'timestampUtc') ||
      readString(record, 'timestamp_utc') ||
      readString(record, 'timestamp') ||
      readString(data, 'timestampUtc') ||
      '';
    const normalized = `${eventName} ${message}`.toLowerCase();
    const tone: SessionEventItem['tone'] =
      normalized.includes('error') || normalized.includes('failed') || normalized.includes('rejected')
        ? 'warning'
        : normalized.includes('approved') || normalized.includes('verified') || normalized.includes('completed')
          ? 'success'
          : normalized.includes('warning') || normalized.includes('blocked') || normalized.includes('approval')
            ? 'warning'
            : 'info';

    return {
      id: readString(record, 'id') || `${eventName}-${index}-${timestamp || eventsCursor}`,
      time: timestamp ? formatClock(timestamp, '-') : '-',
      title: humanizeCode(eventName),
      body: message,
      tag: normalized.includes('approval')
        ? 'APPROVAL'
        : normalized.includes('assistant')
          ? 'ASSISTANT'
          : normalized.includes('computer')
            ? 'COMPUTER_USE'
            : 'STATUS',
      tone,
    };
  }

  const selectedRunRecord = asRecord(
    runItems.find((item) => readString(asRecord(item), 'job_id') === selectedRunId),
  );
  const runOptions = runItems
    .map((item) => {
      const row = asRecord(item);
      const id = readString(row, 'job_id');
      return id ? { id, label: id } : null;
    })
    .filter((item): item is { id: string; label: string } => item !== null);
  if (selectedRunId && !runOptions.some((item) => item.id === selectedRunId)) {
    runOptions.unshift({ id: selectedRunId, label: selectedRunId });
  }

  const selectedCreatedAt =
    readString(runJob, 'created_at') ||
    readString(selectedRunRecord, 'created_at') ||
    readString(runJob, 'started_at');
  const startedAt = formatTimestamp(selectedCreatedAt, previewMode ? '14 May 2025 14:32' : '-');
  const duration = readString(runJob, 'duration') || readString(runComputerUse, 'duration') || (previewMode ? '00:03:18' : '-');
  const sessionId =
    readString(controlRegistry, 'session_id') ||
    readString(runComputerUse, 'session_id') ||
    (previewMode ? 'session_7f3a' : '-');
  const missionStatusCode =
    handshakeError?.code ||
    readString(runComputerUse, 'last_error') ||
    (runStatusValue ? humanizeCode(runStatusValue).toUpperCase() : readString(doctor, 'status', 'Bilinmiyor'));
  const missionStatusError =
    handshakeError?.message ||
    workspaceSnapshot.blockedReason ||
    readString(runComputerUse, 'last_error_message') ||
    (previewMode ? 'Hata: No such file or directory (os error 2)' : 'Ölçüm yok');
  const sessionStatus = workspaceSnapshot.currentStatus || runStatusValue || readString(doctor, 'status', 'Bilinmiyor');
  const approvalRows = pendingApprovals.map((item) => asRecord(item));
  const activeApproval =
    approvalRows.find((item) => readString(item, 'approval_id') === selectedApprovalId) ||
    approvalRows[0] ||
    {};
  const activeApprovalId = readString(activeApproval, 'approval_id');
  const hasApproval = Boolean(activeApprovalId);
  const approvalLabel =
    readString(activeApproval, 'summary') ||
    readString(activeApproval, 'target_kind') ||
    'Plan gözden geçir ve çalıştırmaya izin ver.';
  const approvalDisabledReason = contractMismatch
    ? t.contractMismatch
    : !settings.operatorId.trim()
      ? t.setOperatorId
      : !operatorIdValid
        ? 'Operatör ID geçersiz.'
        : !activeApprovalId
          ? 'Seçili onay yok.'
          : '';
  const approvalDisabled = !canMutate || !activeApprovalId;
  const selectedApprovalActionDisabledReason = !selectedApprovalId
    ? t.noSelection
    : !canMutate
      ? approvalDisabledReason || t.setOperatorId
      : '';
  const selectedRunActionDisabledReason = !selectedRunId ? t.selectRun : '';
  const systemHealth = buildSystemHealthSummary({
    coreMode: settings.mode,
    handshakeRecord,
    doctor,
    metricsPayload: operationOutputs.metrics,
  });
  const activityItems = buildActivityItems(workspaceSnapshot, formatClock);
  const sessionEventItems =
    events.length > 0
      ? events.slice().reverse().map(eventRecordToSessionEventItem)
      : buildSessionEventItems(workspaceSnapshot, formatClock);
  const filteredSessionEvents =
    sessionEventFilter === 'all'
      ? sessionEventItems
      : sessionEventItems.filter((item) => sessionEventCategory(item) === sessionEventFilter);
  const sessionEvents = filteredSessionEvents.slice(0, sessionEventVisibleLimit);
  const runtimeSummary = buildRuntimeSummaryItems({
    snapshot: workspaceSnapshot,
    selectedRunId,
    hasApproval,
    stageLabel: workspaceStageLabel(workspaceSnapshot.stage),
    systemHealth,
  });
  const operatorNotification =
    !operatorIdValid && !dismissedNotifications.includes('operator-id-required')
      ? [
          {
            id: 'operator-id-required',
            kind: 'warning' as const,
            title: locale === 'tr' ? 'Operatör kimliği gerekli' : 'Operator identity required',
            subtitle: t.setOperatorId,
            time: '-',
          },
        ]
      : [];
  const notifications = [
    ...operatorNotification,
    ...buildNotificationItems({
    approvalRows,
    timeline: workspaceSnapshot.timeline,
    dismissedIds: dismissedNotifications,
    formatClock,
    }),
  ];
  const pendingApprovalSummaries = buildPendingApprovalSummaries(approvalRows, selectedRunId);
  const assistantRecentSessions: AssistantRailSession[] = runItems
    .slice(0, 3)
    .map((item) => {
      const row = asRecord(item);
      const id = readString(row, 'job_id');
      if (!id) {
        return null;
      }
      const status = readString(row, 'status') || readString(row, 'stage') || 'unknown';
      const createdAt = readString(row, 'created_at') || readString(row, 'started_at');
      return {
        id,
        title: id,
        status: humanizeCode(status),
        timestamp: createdAt ? formatClock(createdAt, '-') : '-',
      };
    })
    .filter((item): item is AssistantRailSession => item !== null);
  const claimMatrix = asControlPlaneClaimMatrix(controlPlaneClaims);
  const assistantComplianceSummary: AssistantComplianceSummary =
    claimMatrix.claims.length === 0
      ? { label: 'No compliance data available', tone: 'info' }
      : claimMatrix.claims.some((claim) => claim.status === 'blocked')
        ? {
            label: `${claimMatrix.claims.filter((claim) => claim.status === 'blocked').length} blocked`,
            tone: 'error',
          }
        : claimMatrix.claims.some((claim) => claim.status === 'conditional')
          ? {
              label: `${claimMatrix.claims.filter((claim) => claim.status === 'conditional').length} conditional`,
              tone: 'warning',
            }
          : { label: 'Clear', tone: 'success' };
  const assistantRelatedArtifacts = Object.entries(artifactsByName)
    .slice(0, 3)
    .map(([name, value]) => ({
      name,
      summary:
        readString(asRecord(value), 'status') ||
        readString(asRecord(value), 'stage') ||
        readString(asRecord(value), 'summary') ||
        selectedRunId,
    }));
  const assistantWorkbenchArtifacts = Object.entries(artifactsByName)
    .slice(0, 5)
    .map(([name, value]) => {
      const record = asRecord(value);
      const payload = 'payload' in record ? record.payload : value;
      return {
        name,
        summary:
          readString(asRecord(payload), 'status') ||
          readString(asRecord(payload), 'stage') ||
          readString(asRecord(payload), 'summary') ||
          readString(record, 'status') ||
          selectedRunId,
        value: payload,
      };
    });
  const computerUseLiveActionBlocked = isComputerUseRun && !computerUseLiveEnabled;
  const canResumeFromQuickAction =
    !computerUseLiveActionBlocked &&
    (canResumeSession || (Boolean(selectedRunId) && Boolean(resumeForm.specPath.trim())));
  const resumeDisabledReason = !selectedRunId
    ? 'Seçili çalıştırma yok.'
    : !canResumeFromQuickAction
      ? 'Devam için görev spec yolu veya resumable oturum gerekli.'
      : '';
  const cancelDisabled =
    !selectedRunId || !isComputerUseRun || computerUseLiveActionBlocked || !workspaceSnapshot.runtimeState.canStop;
  const cancelDisabledReason = !selectedRunId
    ? 'Seçili çalıştırma yok.'
    : !isComputerUseRun
      ? 'İptal yalnızca aktif computer-use oturumlarında kullanılabilir.'
      : computerUseLiveActionBlocked
        ? computerUseDisabledReason
      : !workspaceSnapshot.runtimeState.canStop
        ? 'Runtime bu durumda durdurma kabul etmiyor.'
        : '';
  function openRunTerminalView() {
    setActiveView('runs');
    setRunTab('stream');
  }
  const assistantSession = useAssistantRuntimeSession(settings, () => ({
    selectedRunId,
    selectedRunStatus: runStatus,
    selectedRunEvents: events,
    selectedArtifacts: artifactsByName,
    artifactContextRequest: governedArtifactContext,
    pendingApproval: approvalDetail || activeApproval,
    systemHealth,
  }), { enabled: artifactFeatureFlags.aiSdkTauriTransport });
  const assistantArtifactWorkspace = useAssistantArtifactWorkspaceController({
    assistantState: assistantSession.state,
    legacyArtifacts: assistantWorkbenchArtifacts,
    selectedLegacyArtifactName: selectedArtifactName,
    onSelectLegacyArtifact: setSelectedArtifactName,
  });

  useEffect(() => {
    const tab = assistantArtifactWorkspace.activeTab;
    setGovernedArtifactContext(tab ? {
      artifactId: tab.artifact.artifactId,
      revisionId: tab.revision.revisionId,
      purpose: 'edit',
      allowedScopes: ['selection', 'metadata'],
      selection: artifactEditorSelection,
    } : null);
  }, [
    artifactEditorSelection,
    assistantArtifactWorkspace.activeTab?.artifact.artifactId,
    assistantArtifactWorkspace.activeTab?.revision.revisionId,
  ]);

  useEffect(() => {
    const approvalId = assistantSession.state.pendingApprovalId;
    if (!approvalId || approvalId === selectedApprovalId) {
      return;
    }
    setSelectedApprovalId(approvalId);
    void loadApprovalDetail(approvalId).then((payload) => {
      if (payload) {
        assistantSession.actions.markApprovalDetailLoaded(approvalId, payload);
      }
    });
  }, [assistantSession.state.pendingApprovalId, selectedApprovalId, settings.profile]);

  function onReviewAssistantApproval(approvalId: string) {
    setSelectedApprovalId(approvalId);
    setActiveView('approvals');
    void loadApprovalDetail(approvalId);
  }

  async function onDecideAssistantApproval(approvalId: string, approve: boolean) {
    if (!approvalId || !canMutate) {
      pushToast('error', approvalDisabledReason || t.setOperatorId);
      return;
    }

    const label = approve ? t.approve : t.reject;
    const actor = actorForOperator(settings.operatorId);
    const confirmed = window.confirm(`${label}\n${approvalId}\n${actor}`);
    if (!confirmed) {
      return;
    }

    try {
      await decideApproval(settings, approvalId, approve, settings.operatorId, 'assistant approval action');
      pushToast('ok', `${label} OK`);
      assistantSession.actions.updateApprovalStatus(approvalId, approve ? 'approved' : 'rejected');
      assistantSession.actions.appendSystemMessage(
        approve
          ? locale === 'tr'
            ? 'Operatör tarafından onaylandı'
            : 'Approved by operator'
          : locale === 'tr'
            ? 'Operatör tarafından reddedildi'
            : 'Rejected by operator',
      );
      await Promise.all([refreshApprovals(), refreshRuns()]);
      if (selectedRunId) {
        await loadRunContext(selectedRunId, false);
      }
    } catch (error) {
      const parsed = getErrorPayload(error);
      if (parsed) {
        pushToast('error', `${parsed.code}: ${parsed.message}`);
      }
    }
  }

  async function onExecuteAssistantApproval(approvalId: string) {
    if (!approvalId || !canMutate) {
      pushToast('error', approvalDisabledReason || t.setOperatorId);
      return;
    }

    const actor = actorForOperator(settings.operatorId);
    const confirmed = window.confirm(`${t.execute}\n${approvalId}\n${actor}`);
    if (!confirmed) {
      return;
    }

    try {
      await executeApproval(settings, approvalId, settings.operatorId);
      pushToast('ok', `${t.execute} OK`);
      assistantSession.actions.updateApprovalStatus(approvalId, 'executed');
      assistantSession.actions.appendSystemMessage(
        locale === 'tr'
          ? 'Onaylı aksiyon yönetişim yaşam döngüsü üzerinden yürütüldü'
          : 'Executed approved action through governance lifecycle',
      );
      await Promise.all([refreshApprovals(), refreshRuns()]);
      if (selectedRunId) {
        await loadRunContext(selectedRunId, false);
      }
    } catch (error) {
      const parsed = getErrorPayload(error);
      if (parsed) {
        pushToast('error', `${parsed.code}: ${parsed.message}`);
      }
    }
  }

  async function onApplyAssistantProposal(proposal: AssistantArtifactProposalPart) {
    if (!canMutate) {
      pushToast('error', approvalDisabledReason || t.setOperatorId);
      return;
    }
    try {
      await assistantArtifactWorkspace.actions.applyProposal({
        proposalId: proposal.proposalId,
        artifactId: proposal.artifactId,
        approvalId: proposal.approvalId,
        baseRevisionNumber: proposal.baseRevisionNumber,
      });
      assistantSession.actions.updateApprovalStatus(proposal.approvalId, 'executed');
      pushToast(
        'ok',
        locale === 'tr'
          ? 'OnaylÄ± artifact Ã¶nerisi uygulandÄ±'
          : 'Approved artifact proposal applied',
      );
    } catch (error) {
      const parsed = getErrorPayload(error);
      pushToast(
        'error',
        parsed ? `${parsed.code}: ${parsed.message}` : 'ARTIFACT_PROPOSAL_APPLY_FAILED',
      );
    }
  }

  async function onCancelAssistantTurn() {
    try {
      await assistantSession.actions.cancel();
      pushToast('ok', locale === 'tr' ? 'Asistan yanıtı durduruldu' : 'Assistant response stopped');
    } catch (error) {
      const parsed = getErrorPayload(error);
      pushToast('error', parsed ? `${parsed.code}: ${parsed.message}` : locale === 'tr' ? 'İşlem tamamlanamadı' : 'Operation failed');
    }
  }

  const assistantRightRail = (
    <AssistantRightRail
      state={assistantSession.state}
      systemHealth={systemHealth}
      pendingApprovals={pendingApprovalSummaries}
      selectedRunId={selectedRunId}
      runtimeSummary={assistantRuntimeSummary}
      recentSessions={assistantRecentSessions}
      complianceSummary={assistantComplianceSummary}
      relatedArtifacts={assistantRelatedArtifacts}
      locale={locale}
      onRefreshContext={() => {
        void refreshCore();
        if (selectedRunId) {
          void loadRunContext(selectedRunId);
        }
      }}
      onViewApprovals={() => setActiveView('approvals')}
      onViewRuns={() => setActiveView('runs')}
    />
  );
  const assistantWorkbenchAvailable = artifactFeatureFlags.workspace && assistantArtifactWorkspace.available;
  const assistantWorkbench =
    assistantWorkbenchAvailable && assistantArtifactWorkspace.open ? (
      <AssistantWorkbench
        state={assistantSession.state}
        artifacts={assistantArtifactWorkspace.legacyArtifacts}
        selectedArtifactName={assistantArtifactWorkspace.selectedLegacyArtifactName}
        locale={locale}
        onSelectArtifact={assistantArtifactWorkspace.actions.selectLegacyArtifact}
        artifactFeatureFlags={artifactFeatureFlags}
        workspaceState={assistantArtifactWorkspace.state}
        catalog={assistantArtifactWorkspace.catalog}
        catalogNextCursor={assistantArtifactWorkspace.catalogNextCursor}
        catalogLoading={assistantArtifactWorkspace.catalogLoading}
        history={assistantArtifactWorkspace.history}
        historyNextCursor={assistantArtifactWorkspace.historyNextCursor}
        historyLoading={Boolean(assistantArtifactWorkspace.historyLoadingArtifactId)}
        comparison={assistantArtifactWorkspace.comparison}
        conflictResolving={assistantArtifactWorkspace.conflictResolving}
        workspaceError={assistantArtifactWorkspace.error}
        operationNotice={assistantArtifactWorkspace.operationNotice}
        formRuntime={assistantArtifactWorkspace.formRuntime}
        onSubmitForm={assistantArtifactWorkspace.actions.submitForm}
        onEditorSelectionChange={setArtifactEditorSelection}
        onOpenArtifact={(artifactId) => void assistantArtifactWorkspace.actions.openArtifact(artifactId)}
        onActivateArtifact={assistantArtifactWorkspace.actions.activate}
        onRequestClose={assistantArtifactWorkspace.actions.requestClose}
        onLoadCatalog={() => void assistantArtifactWorkspace.actions.loadCatalog()}
        onLoadMoreCatalog={() => void assistantArtifactWorkspace.actions.loadMoreCatalog()}
        onLoadHistory={(artifactId) => void assistantArtifactWorkspace.actions.loadHistory(artifactId)}
        onLoadMoreHistory={(artifactId) => void assistantArtifactWorkspace.actions.loadMoreHistory(artifactId)}
        onCompareRevision={(artifactId, revisionId) =>
          void assistantArtifactWorkspace.actions.compareRevision(artifactId, revisionId)
        }
        onCloseComparison={assistantArtifactWorkspace.actions.closeComparison}
        onRefreshConflict={(artifactId) => void assistantArtifactWorkspace.actions.refreshConflict(artifactId)}
        onCompareConflict={assistantArtifactWorkspace.actions.compareConflict}
        onReloadConflict={(artifactId) => void assistantArtifactWorkspace.actions.reloadConflict(artifactId)}
        onForkConflict={(artifactId) => void assistantArtifactWorkspace.actions.forkConflict(artifactId)}
        onEditArtifact={assistantArtifactWorkspace.actions.edit}
        onRetrySave={(artifactId) => void assistantArtifactWorkspace.actions.retrySave(artifactId)}
        onRestoreArtifact={(artifactId, revisionId) =>
          void assistantArtifactWorkspace.actions.restore(artifactId, revisionId)
        }
        onImportAsset={assistantArtifactWorkspace.actions.importAsset}
        onResolveAsset={assistantArtifactWorkspace.actions.resolveAsset}
        onExportArtifact={(artifactId, format, sheetId) => {
          const artifactKind = assistantArtifactWorkspace.state.tabs.find(
            (tab) => tab.artifact.artifactId === artifactId,
          )?.artifact.kind;
          if (format === 'source' || format === 'txt') void assistantArtifactWorkspace.actions.exportCode(artifactId, format);
          else if (format === 'pptx') void assistantArtifactWorkspace.actions.exportSlides(artifactId);
          else if (format === 'submission-json' || (artifactKind === 'form' && (format === 'json' || format === 'csv'))
            || ((artifactKind === 'document' || artifactKind === 'slides') && format === 'json')) {
            void assistantArtifactWorkspace.actions.exportStructured(artifactId, format);
          }
          else if (artifactKind === 'canvas' && (format === 'json' || format === 'svg' || format === 'png')) {
            void assistantArtifactWorkspace.actions.exportCanvas(artifactId, format);
          } else if (format === 'json' || format === 'svg' || format === 'png') {
            void assistantArtifactWorkspace.actions.exportFlow(artifactId, format);
          } else if (format === 'csv' || format === 'xlsx') {
            void assistantArtifactWorkspace.actions.exportSpreadsheet(artifactId, format, sheetId);
          } else void assistantArtifactWorkspace.actions.exportDocument(artifactId, format);
        }}
        onViewRuns={() => {
          setRunTab('artifacts');
          setActiveView('runs');
        }}
      />
    ) : null;

  return (
    <AppShell
      activeView={activeView as ShellViewKey}
      mobileNavOpen={mobileNavOpen}
      sidebarCollapsed={sidebarCollapsed}
      operatorId={settings.operatorId.trim()}
      previewMode={previewMode}
      operatorWarning={!operatorIdValid ? t.setOperatorId : ''}
      contractWarning={contractMismatch ? t.contractMismatch : ''}
      pendingApprovalCount={pendingApprovals.length}
      warningCount={driftEvents.length}
      notificationItems={notifications}
      themeMode={settings.theme}
      locale={locale}
      toasts={toasts}
      onNavigate={(view) => setActiveView(view)}
      onToggleNav={() => setMobileNavOpen((value) => !value)}
      onToggleSidebar={() => setSidebarCollapsed((value) => !value)}
      onCloseNav={() => setMobileNavOpen(false)}
      onRefresh={() => void refreshCore()}
      onDismissNotification={(id) => setDismissedNotifications((prev) => [...prev, id])}
      onThemeChange={(theme) => updateSettings({ theme })}
      rightRail={
        activeView === 'assistant' ? null : (
          <RightRail
            notifications={notifications}
            selectedRunId={selectedRunId || '-'}
            sessionId={sessionId}
            mode={settings.mode === 'auto' ? 'Yardımlı' : settings.mode}
            profile={settings.profile}
            startedAt={startedAt}
            duration={duration}
            systemHealth={systemHealth}
            pendingApprovals={pendingApprovalSummaries}
            resumeDisabled={!canResumeFromQuickAction}
            resumeDisabledReason={resumeDisabledReason}
            exportDisabled={!selectedRunId}
            exportDisabledReason={!selectedRunId ? 'Seçili çalıştırma yok.' : ''}
            cancelDisabled={cancelDisabled}
            cancelDisabledReason={cancelDisabledReason}
            onDismissNotification={(id) => setDismissedNotifications((prev) => [...prev, id])}
            onRefreshContext={() => {
              void refreshCore();
              if (selectedRunId) {
                void loadRunContext(selectedRunId);
              }
            }}
            onResume={() => {
              if (canResumeSession) {
                void onControlSession('resume');
              } else {
                void onResumeRun();
              }
            }}
            onOpenTerminal={openRunTerminalView}
            onExport={() => void onExportArtifacts()}
            onCancel={() => void onControlSession('stop')}
            onViewDetails={() => setActiveView('runs')}
            onViewApprovals={() => setActiveView('approvals')}
          />
        )
      }
    >
        {contractMismatch ? <div className="error-banner">{t.contractMismatch}</div> : null}
        {handshakeError ? (
          <div className="error-banner">
            <div>{`${handshakeError.code}: ${handshakeError.message}`}</div>
            <small>{handshakeError.command}</small>
          </div>
        ) : null}
        {activeView === 'dashboard' ? (
          <ControlPlaneDashboard
            doctor={controlPlaneDoctor}
            agents={controlPlaneAgents}
            claims={controlPlaneClaims}
            pendingApprovals={pendingApprovals.length}
            pilotLaunch={pilotLaunch}
            codeIntelligence={codeIntelligence}
            pilotOperations={pilotOperations}
            designPartnerBeta={designPartnerBeta}
            providerGovernance={providerGovernance}
            providerRuntime={providerRuntime}
            targetEvidenceClosure={targetEvidenceClosure}
            locale={locale}
          />
        ) : null}

        {activeView === 'agents' ? <AgentRegistryView agents={controlPlaneAgents} locale={locale} /> : null}

        {activeView === 'policy' ? <PolicySimulationView simulation={controlPlanePolicy} locale={locale} /> : null}

        {activeView === 'evidence' ? (
          <OperatorPageShell
            kicker={locale === 'tr' ? 'Kanıt' : 'Evidence'}
            title={locale === 'tr' ? 'İmzalı Kanıtlar' : 'Signed Evidence'}
            lead={
              locale === 'tr'
                ? 'Manifest bütünlüğü, replay doğrulaması ve yayın sınırları.'
                : 'Manifest integrity, replay verification and release boundaries.'
            }
            status={selectedEvidenceManifestPath ? (evidencePacks[0]?.signatureStatus ?? 'ready') : 'missing manifest'}
            actions={[
              {
                label: locale === 'tr' ? 'Claim kayıtlarını yenile' : 'Refresh claims',
                onClick: () => void refreshControlPlane(),
              },
              {
                label: locale === 'tr' ? 'Son evidence packi doğrula' : 'Verify latest evidence',
                onClick: () => void onVerifyEvidencePack(),
                disabled: !selectedEvidenceManifestPath,
                title: selectedEvidenceManifestPath
                  ? undefined
                  : locale === 'tr'
                    ? 'Doğrulanacak evidence manifest yok.'
                    : 'No evidence manifest is available to verify.',
                variant: 'primary',
              },
            ]}
            decisionItems={[
              {
                label: locale === 'tr' ? 'Mevcut durum' : 'Current state',
                value: selectedEvidenceManifestPath
                  ? locale === 'tr'
                    ? 'Manifest hazır'
                    : 'Manifest ready'
                  : 'missing',
                detail: selectedEvidenceManifestPath
                  ? selectedEvidenceManifestPath
                  : locale === 'tr'
                    ? 'Önce evidence manifest üretilmeli.'
                    : 'Generate an evidence manifest first.',
                tone: selectedEvidenceManifestPath ? 'success' : 'error',
              },
              {
                label: locale === 'tr' ? 'Neden önemli' : 'Why it matters',
                value: evidencePacks[0]?.claimGuardStatus ?? 'claim guard',
                detail: locale === 'tr'
                  ? 'Release ve ready claimleri bu kanıta dayanır.'
                  : 'Release and ready claims depend on this evidence.',
              },
              {
                label: locale === 'tr' ? 'Sıradaki aksiyon' : 'Next action',
                value: selectedEvidenceManifestPath
                  ? locale === 'tr'
                    ? 'Doğrula'
                    : 'Verify'
                  : locale === 'tr'
                    ? 'Manifest üret'
                    : 'Generate manifest',
                detail: locale === 'tr'
                  ? 'Ham JSON sadece gerektiğinde detayda kalır.'
                  : 'Raw JSON stays in details unless needed.',
                tone: selectedEvidenceManifestPath ? 'info' : 'warning',
              },
            ]}
            metrics={[
              {
                label: locale === 'tr' ? 'Packler' : 'Packs',
                value: evidencePacks.length,
                detail: evidencePacks[0]?.runId ?? (locale === 'tr' ? 'run bağlı değil' : 'no run linked'),
              },
              {
                label: locale === 'tr' ? 'İmza' : 'Signature',
                value: evidencePacks[0]?.signatureStatus ?? 'missing',
                detail: locale === 'tr' ? 'kurumsal kanıt' : 'enterprise evidence',
              },
              {
                label: locale === 'tr' ? 'Replay' : 'Replay',
                value: evidencePacks[0]?.replayStatus ?? 'not_available',
                detail: locale === 'tr' ? 'bütünlük kanıtı' : 'integrity proof',
              },
            ]}
            context={<ClaimBoundaryBanner claims={controlPlaneClaims} locale={locale} />}
          >
            <div className="section-grid">
              <EvidencePackView
                evidencePacks={evidencePacks}
                verifyResult={controlPlaneEvidenceVerifyResult}
                verifyDisabledReason={
                  selectedEvidenceManifestPath
                    ? ''
                    : locale === 'tr'
                      ? 'Doğrulanacak evidence manifest yok.'
                      : 'No evidence manifest is available to verify.'
                }
                pilotLaunch={pilotLaunch}
                locale={locale}
                onVerify={() => void onVerifyEvidencePack()}
              />
            </div>
          </OperatorPageShell>
        ) : null}

        {activeView === 'surfaces' ? (
          <ExecutionSurfacesView
            computerUseCapability={computerUseVisionCapability.capabilityResolution}
            locale={locale}
          />
        ) : null}

        {activeView === 'workspace' ? (
          <MissionControlView
            runOptions={runOptions}
            selectedRunId={selectedRunId}
            sessionId={sessionId}
            sessionStatus={humanizeCode(sessionStatus)}
            objective={workspaceSnapshot.objective || 'Yönetişimli görevi tarif edin.'}
            priority="Yüksek"
            targetType="Yönetişimli Görev"
            statusCode={missionStatusCode}
            statusError={missionStatusError}
            stageLabel={workspaceStageLabel(workspaceSnapshot.stage)}
            stageKey={mapWorkspaceStageToMissionStage(workspaceSnapshot.stage, hasApproval)}
            startedAt={startedAt}
            duration={duration}
            progress={workspaceProgress}
            activityItems={activityItems}
            sessionEvents={sessionEvents}
            sessionEventFilter={sessionEventFilter}
            sessionEventsHasMore={
              filteredSessionEvents.length > sessionEventVisibleLimit || sessionEventsHasMore
            }
            sessionEventsLoadingMore={sessionEventsLoadingMore}
            runtimeSummary={runtimeSummary}
            rawSummary={{ runStatus, computerUseState, configData, handshakeData }}
            computerUseCapabilityResolution={computerUseVisionCapability.capabilityResolution}
            debugRawEnabled={settings.debugRaw}
            hasApproval={hasApproval}
            approvalLabel={approvalLabel}
            approvalDisabled={approvalDisabled}
            approvalDisabledReason={approvalDisabledReason}
            onSelectRun={setSelectedRunId}
            onRawJsonRequested={() => confirmRawDisclosure('Runtime özeti ham JSON')}
            onSessionEventFilterChange={(filter) => {
              setSessionEventFilter(filter);
              setSessionEventVisibleLimit(20);
            }}
            onLoadMoreSessionEvents={() => void onLoadMoreSessionEvents()}
            onApprove={() => void onApproveAndContinue()}
            onEditApproval={() => setActiveView('approvals')}
            onReject={() => void onDecideApproval(false)}
            onResolveApprovalDisabled={() => setActiveView('settings')}
          />
        ) : null}
        {activeView === 'assistant' ? (
          <AssistantView
            copy={assistantCopy}
            state={assistantSession.state}
            approvalDisabled={approvalDisabled}
            approvalDisabledReason={approvalDisabledReason}
            debugRawEnabled={settings.debugRaw}
            rightRail={assistantRightRail}
            workbench={assistantWorkbench}
            workbenchAvailable={assistantWorkbenchAvailable}
            workbenchOpen={assistantWorkbenchAvailable && assistantArtifactWorkspace.open}
            runtimeSettings={assistantRuntimeSettings}
            modelDiscovery={assistantModels}
            locale={locale}
            assistantUiRuntimeEnabled={artifactFeatureFlags.assistantUiRuntime}
            activeArtifactKind={assistantArtifactWorkspace.activeTab?.artifact.kind}
            onRuntimeSettingsChange={updateSettings}
            onSend={(message, runtimeSettings, controls) =>
              void assistantSession.actions.send(message, runtimeSettings, controls)
            }
            onNewChat={() => {
              assistantArtifactWorkspace.actions.reset();
              assistantSession.actions.newChat();
            }}
            onToggleWorkbench={assistantWorkbenchAvailable ? assistantArtifactWorkspace.actions.toggle : undefined}
            onReviewApproval={onReviewAssistantApproval}
            onApprove={(approvalId) => void onDecideAssistantApproval(approvalId, true)}
            onReject={(approvalId) => void onDecideAssistantApproval(approvalId, false)}
            onExecute={(approvalId) => void onExecuteAssistantApproval(approvalId)}
            onApplyProposal={(proposal) => void onApplyAssistantProposal(proposal)}
            onRegenerate={(turnId) => void assistantSession.actions.regenerate(turnId, assistantRuntimeSettings)}
            onOpenArtifact={artifactFeatureFlags.workspace
              ? (artifactId) => void assistantArtifactWorkspace.actions.openArtifact(artifactId)
              : undefined}
            renderInlineArtifact={(artifact) => {
              if (!artifactFeatureFlags.workspace || !artifactFeatureFlags.form || artifact.kind !== 'form' || !artifact.artifactId) return null;
              const inlineTab = assistantArtifactWorkspace.state.tabs.find(
                (tab) => tab.artifact.artifactId === artifact.artifactId,
              ) ?? null;
              return (
                <AssistantInlineFormPart
                  artifactId={artifact.artifactId}
                  tab={inlineTab}
                  loading={assistantArtifactWorkspace.loadingArtifactId === artifact.artifactId}
                  locale={locale}
                  formRuntime={assistantArtifactWorkspace.formRuntime}
                  onLoad={assistantArtifactWorkspace.actions.openInlineArtifact}
                  onExpand={assistantArtifactWorkspace.actions.openArtifact}
                  onSubmit={assistantArtifactWorkspace.actions.submitForm}
                  workspaceEnabled={artifactFeatureFlags.workspace}
                  formEnabled={artifactFeatureFlags.form}
                />
              );
            }}
            onCancel={() => void onCancelAssistantTurn()}
            onOpenTerminal={openRunTerminalView}
          />
        ) : null}

        {activeView === 'tasks' ? (
          <section className="workspace" data-testid="page-primary-region">
            <div className="workspace-header">
              <div>
                <p className="workspace-kicker">{t.tasksKicker}</p>
                <h2>{t.tasks}</h2>
                <p className="workspace-lead">{t.tasksLead}</p>
              </div>
              <div className="workspace-actions">
                <button className="ghost-btn" type="button" onClick={() => void refreshRuns()}>
                  {t.refreshRuns}
                </button>
                <button
                  className="ghost-btn"
                  type="button"
                  disabled={!computerUseLiveEnabled}
                  title={computerUseDisabledReason}
                  onClick={() => void onSubmitComputerUseSession()}
                >
                  {t.startSession}
                </button>
                <button className="action-btn" type="button" onClick={() => void onSubmitTask()}>
                  {t.submitRun}
                </button>
              </div>
            </div>

            <div className="section-grid two-up">
              <article className="page-card">
                <h3>{t.taskWorkspace}</h3>
                <div className="toolbar-row">
                  <button
                    className={automationMode === 'assisted' ? 'tab-btn tab-btn-active' : 'tab-btn'}
                    type="button"
                    onClick={() => {
                      setAutomationMode('assisted');
                      setStepMode(true);
                    }}
                  >
                    {t.assistedMode}
                  </button>
                  <button
                    className={automationMode === 'supervised' ? 'tab-btn tab-btn-active' : 'tab-btn'}
                    type="button"
                    onClick={() => {
                      setAutomationMode('supervised');
                      setStepMode(false);
                    }}
                  >
                    {t.supervisedMode}
                  </button>
                </div>
                <div className="control-switches">
                  <label className="field field-inline">
                    <span>{t.askBeforeExternalAction}</span>
                    <input
                      type="checkbox"
                      checked={askBeforeExternal}
                      onChange={(event) => setAskBeforeExternal(event.target.checked)}
                    />
                  </label>
                  <label className="field field-inline">
                    <span>{t.askBeforeDeletion}</span>
                    <input
                      type="checkbox"
                      checked={askBeforeDeletion}
                      onChange={(event) => setAskBeforeDeletion(event.target.checked)}
                    />
                  </label>
                  <label className="field field-inline">
                    <span>{t.askBeforeSend}</span>
                    <input
                      type="checkbox"
                      checked={askBeforeSend}
                      onChange={(event) => setAskBeforeSend(event.target.checked)}
                    />
                  </label>
                </div>
                <ComputerUseBlockerChecklist
                  blocked={!computerUseLiveEnabled}
                  reason={computerUseDisabledReason}
                  blockers={computerUseVisionBlockers}
                  onOpenSettings={() => setActiveView('settings')}
                />
                <div className="form-grid">
                  <label className="field">
                    <span>{t.profile}</span>
                    <select value={settings.profile} onChange={(event) => updateSettings({ profile: event.target.value })}>
                      {(supportedProfiles.length > 0 ? supportedProfiles : [settings.profile]).map((item) => (
                        <option value={String(item)} key={String(item)}>
                          {String(item)}
                        </option>
                      ))}
                    </select>
                  </label>

                  <label className="field field-span">
                    <span>{t.specPath}</span>
                    <input
                      value={taskForm.specPath}
                      onChange={(event) => setTaskForm((prev) => ({ ...prev, specPath: event.target.value }))}
                      placeholder="examples/team/restricted_pilot.yaml"
                    />
                  </label>

                  <label className="field field-span">
                    <span>{t.request}</span>
                    <textarea
                      rows={6}
                      value={taskForm.request}
                      onChange={(event) => setTaskForm((prev) => ({ ...prev, request: event.target.value }))}
                      placeholder={t.requestPlaceholder}
                    />
                  </label>
                </div>

                <details className="details-panel">
                  <summary>{t.advancedOptions}</summary>
                  <div className="form-grid compact-grid">
                    <label className="field">
                      <span>{t.caseId}</span>
                      <input
                        value={taskForm.caseId}
                        onChange={(event) => setTaskForm((prev) => ({ ...prev, caseId: event.target.value }))}
                      />
                    </label>
                    <label className="field">
                      <span>{t.jobId}</span>
                      <input
                        value={taskForm.jobId}
                        onChange={(event) => setTaskForm((prev) => ({ ...prev, jobId: event.target.value }))}
                      />
                    </label>
                    <label className="field">
                      <span>{t.provider}</span>
                      <input
                        value={taskForm.provider}
                        onChange={(event) => setTaskForm((prev) => ({ ...prev, provider: event.target.value }))}
                        placeholder="auto"
                      />
                    </label>
                    <label className="field">
                      <span>{t.fallbackProvider}</span>
                      <input
                        value={taskForm.fallbackProvider}
                        onChange={(event) =>
                          setTaskForm((prev) => ({ ...prev, fallbackProvider: event.target.value }))
                        }
                        placeholder="transformers"
                      />
                    </label>
                    <label className="field">
                      <span>{t.model}</span>
                      <input
                        value={taskForm.model}
                        onChange={(event) => setTaskForm((prev) => ({ ...prev, model: event.target.value }))}
                      />
                    </label>
                    <label className="field">
                      <span>{t.hfModelId}</span>
                      <input
                        value={taskForm.hfModelId}
                        onChange={(event) => setTaskForm((prev) => ({ ...prev, hfModelId: event.target.value }))}
                      />
                    </label>
                  </div>
                </details>
              </article>

              <ComputerUseOperationsCard
                legacyCapability={computerUseCapability}
                visionCapability={computerUseVisionCapability}
                summary={computerUseSummaryData}
                runtimeChoice={computerUseRuntimeChoice}
                startAllowed={computerUseLiveEnabled}
                disabledReason={computerUseDisabledReason}
                blockers={computerUseVisionBlockers}
                onRuntimeChoiceChange={setComputerUseRuntimeChoice}
              />

              <article className="page-card">
                <h3>{t.submitReadiness}</h3>
                <div className="metric-list">
                  <div className="metric-row">
                    <span>{t.operatorId}</span>
                    <strong>{settings.operatorId.trim() || '-'}</strong>
                  </div>
                  <div className="metric-row">
                    <span>{t.rootDir}</span>
                    <strong>{settings.rootDir}</strong>
                  </div>
                  <div className="metric-row">
                    <span>{t.profile}</span>
                    <strong>{settings.profile}</strong>
                  </div>
                  <div className="metric-row">
                    <span>{t.workflowParity}</span>
                    <strong>{readBool(features, 'operatorWorkflowParity') ? t.enabled : t.disabled}</strong>
                  </div>
                  <div className="metric-row">
                    <span>Runtime</span>
                    <strong>{computerUseRuntimeChoice}</strong>
                  </div>
                  <div className="metric-row">
                    <span>Computer-use live</span>
                    <strong>{computerUseLiveEnabled ? t.enabled : 'Qualification required'}</strong>
                  </div>
                  <div className="metric-row">
                    <span>Reason code</span>
                    <strong>
                      {computerUseRuntimeChoice === 'legacy-pilot'
                        ? computerUseCapability.reasonCode || '-'
                        : computerUseVisionCapability.reasonCode ||
                          computerUseVisionCapability.capabilityResolution?.reasonCode ||
                          '-'}
                    </strong>
                  </div>
                  <div className="metric-row">
                    <span>Vision runtime</span>
                    <strong>{computerUseVisionCapability.stage}</strong>
                  </div>
                  <div className="metric-row">
                    <span>Vision provider</span>
                    <strong>
                      {computerUseVisionCapability.provider.kind}
                      {computerUseVisionCapability.provider.model
                        ? ` / ${computerUseVisionCapability.provider.model}`
                        : ''}
                    </strong>
                  </div>
                  <div className="metric-row">
                    <span>Vision safety</span>
                    <strong>
                      {computerUseVisionCapability.safety.rawScreenshotPersistence} /{' '}
                      {computerUseVisionCapability.safety.terminalControl}
                    </strong>
                  </div>
                  {computerUseVisionPlatformStatuses.length > 0 ? (
                    <div className="platform-gate-list" aria-label="Computer-use platform gates">
                      {computerUseVisionPlatformStatuses.map((platformStatus) => (
                        <span
                          className="platform-gate-pill"
                          key={platformStatus.platform}
                          title={platformStatus.reasonCode || platformStatus.stage}
                        >
                          <span>{platformStatus.platform}</span>
                          <strong>{platformStatus.liveEnabled ? 'live' : platformStatus.stage}</strong>
                        </span>
                      ))}
                    </div>
                  ) : null}
                </div>
                {!computerUseLiveEnabled ? (
                  <div className="warning-inline">{computerUseDisabledReason}</div>
                ) : null}
                <div className="stack-actions">
                  <button className="action-btn" type="button" onClick={() => void onSubmitTask()}>
                    {t.submitRun}
                  </button>
                  <button
                    className="ghost-btn"
                    type="button"
                    onClick={() => {
                      setActiveView('runs');
                    }}
                  >
                    {t.openRuns}
                  </button>
                </div>
              </article>
            </div>
          </section>
        ) : null}

        {activeView === 'approvals' ? (
          <OperatorPageShell
            kicker={t.approvalsKicker}
            title={t.approvals}
            lead={t.approvalsLead}
            status={selectedApprovalId ? readString(asRecord(selectedApproval), 'status', 'selected') : 'no selection'}
            actions={[
              { label: t.refresh, onClick: () => void refreshApprovals() },
              {
                label: t.approve,
                onClick: () => void onDecideApproval(true),
                disabled: !canMutate || !selectedApprovalId,
                title: selectedApprovalActionDisabledReason || undefined,
                variant: 'primary',
              },
              {
                label: t.reject,
                onClick: () => void onDecideApproval(false),
                disabled: !canMutate || !selectedApprovalId,
                title: selectedApprovalActionDisabledReason || undefined,
              },
              {
                label: t.execute,
                onClick: () => void onExecuteApproval(),
                disabled: !canMutate || !selectedApprovalId,
                title: selectedApprovalActionDisabledReason || undefined,
                variant: 'danger',
              },
            ]}
            decisionItems={[
              {
                label: locale === 'tr' ? 'Mevcut seçim' : 'Current selection',
                value: selectedApprovalId || (locale === 'tr' ? 'Seçim yok' : 'No selection'),
                detail: selectedApprovalId
                  ? readString(asRecord(selectedApproval), 'target_kind', '-')
                  : locale === 'tr'
                    ? 'Önce kuyruktan bir onay seçin.'
                    : 'Select an approval from the queue first.',
                tone: selectedApprovalId ? 'info' : 'warning',
              },
              {
                label: locale === 'tr' ? 'Mutasyon kapısı' : 'Mutation gate',
                value: canMutate ? (locale === 'tr' ? 'Hazır' : 'Ready') : (locale === 'tr' ? 'Blokeli' : 'Blocked'),
                detail: selectedApprovalActionDisabledReason || (locale === 'tr' ? 'Operatör kimliği geçerli.' : 'Operator identity is valid.'),
                tone: canMutate ? 'success' : 'error',
              },
              {
                label: locale === 'tr' ? 'Sıradaki aksiyon' : 'Next action',
                value: selectedApprovalId ? t.approve : t.pendingApprovals,
                detail: locale === 'tr'
                  ? 'Reject ve Execute aynı seçili onay bağlamını kullanır.'
                  : 'Reject and Execute use the same selected approval context.',
                tone: selectedApprovalId ? 'info' : 'warning',
              },
            ]}
            metrics={[
              {
                label: t.pendingApprovals,
                value: pendingApprovals.length,
                detail: locale === 'tr' ? 'operatör kuyruğu' : 'operator queue',
              },
              {
                label: t.operatorId,
                value: settings.operatorId.trim() || (locale === 'tr' ? 'eksik' : 'missing'),
                detail: locale === 'tr' ? 'mutasyonlar için gerekli' : 'required for mutations',
              },
              {
                label: t.status,
                value: selectedApprovalId ? readString(asRecord(selectedApproval), 'status', '-') : '-',
                detail: selectedApprovalId ?? (locale === 'tr' ? 'seçim yok' : 'no selection'),
              },
            ]}
          >
            <div className="operator-master-detail">
              <article className="page-card">
                <h3>{t.pendingApprovals}</h3>
                <div className="list-scroll">
                  {pendingApprovals.length === 0 ? <p className="supporting">{t.noData}</p> : null}
                  {pendingApprovals.map((item) => {
                    const row = asRecord(item);
                    const approvalId = readString(row, 'approval_id');
                    return (
                      <button
                        key={approvalId}
                        type="button"
                        className={approvalId === selectedApprovalId ? 'list-row list-row-active' : 'list-row'}
                        onClick={() => setSelectedApprovalId(approvalId)}
                      >
                        <strong>{approvalId}</strong>
                        <span>{readString(row, 'target_kind')}</span>
                        <small>{readString(row, 'status')}</small>
                      </button>
                    );
                  })}
                </div>
              </article>

              <article className="page-card">
                <h3>{t.selectedApproval}</h3>
                {selectedApprovalId ? (
                  <>
                    <PayloadSummary value={selectedApproval} title="Approval summary" maxItems={18} />
                    <JsonPanel value={selectedApproval} />
                  </>
                ) : (
                  <p className="supporting">{t.noSelection}</p>
                )}
              </article>
            </div>
          </OperatorPageShell>
        ) : null}

        {activeView === 'runs' ? (
          <OperatorPageShell
            kicker={t.runsKicker}
            title={t.runs}
            lead={t.runsLead}
            status={selectedRunId ? missionStatusCode : 'no selection'}
            statusTone={operatorToneFromStatus(selectedRunId ? missionStatusCode : 'missing')}
            actions={[
              { label: t.refreshRuns, onClick: () => void refreshRuns() },
              {
                label: t.refreshContext,
                onClick: () => void loadRunContext(selectedRunId),
                disabled: !selectedRunId,
                title: selectedRunActionDisabledReason || undefined,
              },
              {
                label: t.export,
                onClick: () => void onExportArtifacts(),
                disabled: !selectedRunId,
                title: selectedRunActionDisabledReason || undefined,
                variant: 'primary',
              },
            ]}
            decisionItems={[
              {
                label: locale === 'tr' ? 'Seçili run' : 'Selected run',
                value: selectedRunId || (locale === 'tr' ? 'Seçim yok' : 'No selection'),
                detail: selectedRunId
                  ? readString(asRecord(asRecord(runStatus).job), 'request', workspaceSnapshot.objective || '-')
                  : locale === 'tr'
                    ? 'Listeden bir run seçin.'
                    : 'Choose a run from the list.',
                tone: selectedRunId ? 'info' : 'warning',
              },
              {
                label: locale === 'tr' ? 'Durum' : 'Status',
                value: selectedRunId ? missionStatusCode : '-',
                detail: missionStatusError || (locale === 'tr' ? 'Run context seçime göre yüklenir.' : 'Run context follows the selection.'),
              },
              {
                label: locale === 'tr' ? 'Sıradaki aksiyon' : 'Next action',
                value: selectedRunId ? t.export : t.recentRuns,
                detail: selectedRunId
                  ? locale === 'tr'
                    ? 'Artifact, replay ve stream tabları aynı run bağlamını kullanır.'
                    : 'Artifact, replay, and stream tabs use the same run context.'
                  : locale === 'tr'
                    ? 'Önce run seçin.'
                    : 'Select a run first.',
                tone: selectedRunId ? 'info' : 'warning',
              },
            ]}
            metrics={[
              { label: t.recentRuns, value: runItems.length, detail: locale === 'tr' ? 'yüklenen kayıt' : 'loaded records' },
              { label: t.stream, value: events.length, detail: eventsWarning || (locale === 'tr' ? 'event tail' : 'event tail') },
              { label: t.artifacts, value: ARTIFACT_NAMES.length, detail: selectedArtifactName },
            ]}
          >

            {driftEvents.length > 0 ? <div className="warning-banner">{t.driftWarning}</div> : null}

            <div className="operator-master-detail">
              <article className="page-card">
                <h3>{t.recentRuns}</h3>
                <div className="list-scroll">
                  {runItems.length === 0 ? <p className="supporting">{t.noData}</p> : null}
                  {runItems.map((item) => {
                    const row = asRecord(item);
                    const jobId = readString(row, 'job_id');
                    return (
                      <button
                        key={jobId}
                        type="button"
                        className={jobId === selectedRunId ? 'list-row list-row-active' : 'list-row'}
                        onClick={() => setSelectedRunId(jobId)}
                      >
                        <strong>{jobId}</strong>
                        <span>{readString(row, 'status')}</span>
                        <small>{readString(row, 'created_at')}</small>
                      </button>
                    );
                  })}
                </div>
              </article>

              <article className="page-card">
                <div className="tab-strip">
                  {(['overview', 'stream', 'approvals', 'artifacts', 'replay', 'diagnostics'] as RunTabKey[]).map((tab) => (
                    <button
                      key={tab}
                      type="button"
                      className={runTab === tab ? 'tab-btn tab-btn-active' : 'tab-btn'}
                      onClick={() => setRunTab(tab)}
                    >
                      {tab === 'overview'
                        ? t.overview
                        : tab === 'stream'
                          ? t.stream
                          : tab === 'approvals'
                            ? t.approvals
                            : tab === 'artifacts'
                              ? t.artifacts
                              : tab === 'replay'
                                ? t.replay
                                : t.diagnostics}
                    </button>
                  ))}
                </div>

                {!selectedRunId ? <p className="supporting">{t.selectRun}</p> : null}
                {selectedRunId && runTab === 'overview' ? (
                  <>
                    <PayloadSummary value={runStatus} title="Run summary" maxItems={18} />
                    <JsonPanel value={runStatus} />
                  </>
                ) : null}

                {selectedRunId && runTab === 'stream' ? (
                  <div className="timeline-panel">
                    {eventsWarning ? <div className="warning-inline">{eventsWarning}</div> : null}
                    {events.length === 0 ? <p className="supporting">{t.noData}</p> : null}
                    {events.map((item, index) => {
                      const row = asRecord(item);
                      const eventData = asRecord(row.data);
                      const dataKeys = Object.keys(eventData);
                      return (
                        <div className="timeline-event" key={`${index}-${readString(row, 'timestamp', String(index))}`}>
                          <strong>{readString(row, 'event', 'event')}</strong>
                          <span>{readString(row, 'timestamp')}</span>
                          {dataKeys.length > 0 ? (
                            <span className="supporting">Payload keys: {dataKeys.slice(0, 4).join(', ')}</span>
                          ) : (
                            <span className="supporting">No structured payload fields.</span>
                          )}
                          <RawInspector value={eventData} label="Event raw payload" />
                        </div>
                      );
                    })}
                  </div>
                ) : null}

                {selectedRunId && runTab === 'approvals' ? (
                  linkedApprovals.length > 0 ? (
                    <>
                      <PayloadSummary value={linkedApprovals} title="Approval summary" maxItems={18} />
                      <JsonPanel value={linkedApprovals} />
                    </>
                  ) : (
                    <p className="supporting">{t.noLinkedApprovals}</p>
                  )
                ) : null}

                {selectedRunId && runTab === 'artifacts' ? (
                  <div className="artifact-panel">
                    <div className="toolbar-row">
                      <select value={selectedArtifactName} onChange={(event) => setSelectedArtifactName(event.target.value)}>
                        {ARTIFACT_NAMES.map((name) => (
                          <option value={name} key={name}>
                            {name}
                          </option>
                        ))}
                      </select>
                      <button
                        className="ghost-btn"
                        type="button"
                        disabled={!settings.debugRaw}
                        title={settings.debugRaw ? undefined : 'Ham payload modu ayarlardan açılmalı.'}
                        onClick={() => {
                          if (showRawArtifact) {
                            setShowRawArtifact(false);
                            return;
                          }
                          if (confirmRawDisclosure(`${selectedArtifactName} ham JSON`)) {
                            setShowRawArtifact(true);
                          }
                        }}
                      >
                        {showRawArtifact ? t.hideRaw : t.showRaw}
                      </button>
                    </div>
                    <PayloadSummary
                      value={showRawArtifact ? parsedArtifact : artifactValue}
                      title="Artifact summary"
                      maxItems={20}
                      testId="artifact-summary"
                    />
                    <JsonPanel value={showRawArtifact ? parsedArtifact : artifactValue} />
                  </div>
                ) : null}

                {selectedRunId && runTab === 'replay' ? (
                  <>
                    <PayloadSummary value={runReplay} title="Replay summary" maxItems={20} testId="run-replay-summary" />
                    <JsonPanel value={runReplay} />
                  </>
                ) : null}

                {selectedRunId && runTab === 'diagnostics' ? (
                  <div className="section-grid">
                    <article className="inner-card">
                      <h3>{t.driftSignals}</h3>
                      {driftEvents.length > 0 ? (
                        <>
                          <PayloadSummary value={driftEvents} title="Drift summary" maxItems={12} />
                          <JsonPanel value={driftEvents} />
                        </>
                      ) : (
                        <p className="supporting">{t.noDrift}</p>
                      )}
                    </article>
                    <article className="inner-card">
                      <h3>{t.systemContext}</h3>
                      <PayloadSummary
                        value={{ doctor: handshakeRecord.doctor ?? {}, config: configData ?? {} }}
                        title="System summary"
                        maxItems={12}
                      />
                      <JsonPanel value={{ doctor: handshakeRecord.doctor ?? {}, config: configData ?? {} }} />
                    </article>
                  </div>
                ) : null}
              </article>
            </div>
          </OperatorPageShell>
        ) : null}

        {activeView === 'system' ? (
          <section className="workspace" data-testid="page-primary-region">
            <div className="workspace-header">
              <div>
                <p className="workspace-kicker">{t.systemKicker}</p>
                <h2>{t.system}</h2>
                <p className="workspace-lead">{t.systemLead}</p>
              </div>
              <div className="workspace-actions">
                <button className="ghost-btn" type="button" onClick={() => void refreshHandshake()}>
                  {t.refreshDoctor}
                </button>
                <button className="ghost-btn" type="button" onClick={() => void refreshConfig()}>
                  {t.refreshConfig}
                </button>
              </div>
            </div>

            <div className="metric-grid">
              <article className="metric-card">
                <h3>{t.contractVersion}</h3>
                <p className="metric">{readString(handshakeRecord, 'contractVersion', '-')}</p>
              </article>
              <article className="metric-card">
                <h3>{t.coreVersion}</h3>
                <p className="metric">{readString(handshakeRecord, 'coreVersion', '-')}</p>
              </article>
              <article className="metric-card">
                <h3>{t.profile}</h3>
                <p className="metric">{settings.profile}</p>
              </article>
              <article className="metric-card">
                <h3>{t.runtimeHealth}</h3>
                <p className="metric">{readString(doctor, 'status', '-')}</p>
              </article>
              <article className="metric-card">
                <h3>{t.live}</h3>
                <p className="metric">{eventsCursor}</p>
              </article>
            </div>

            <div className="section-grid two-up">
              <article className="page-card">
                <h3>{t.doctor}</h3>
                <PayloadSummary value={doctor} title="Doctor summary" maxItems={12} />
                <JsonPanel value={doctor} />
              </article>
              <article className="page-card">
                <h3>{t.effectiveConfig}</h3>
                <dl className="metric-list">
                  <div className="metric-row">
                    <dt>{t.profile}</dt>
                    <dd>{readString(assistantResolvedConfig, 'profile_name', settings.profile)}</dd>
                  </div>
                  <div className="metric-row">
                    <dt>{t.provider}</dt>
                    <dd>{readString(assistantResolvedConfig, 'llm_provider', '-')}</dd>
                  </div>
                  <div className="metric-row">
                    <dt>{t.model}</dt>
                    <dd>{readString(assistantResolvedConfig, 'model_name', '-')}</dd>
                  </div>
                  <div className="metric-row">
                    <dt>{t.hfModelId}</dt>
                    <dd>{readString(assistantResolvedConfig, 'hf_model_id', '-')}</dd>
                  </div>
                </dl>
                <JsonPanel value={configRecord} />
              </article>
              <article className="page-card">
                <h3>{t.capabilities}</h3>
                <PayloadSummary value={capabilities} title="Capabilities summary" maxItems={12} />
                <JsonPanel value={capabilities} />
              </article>
              <article className="page-card">
                <h3>Pilot Launch Candidate</h3>
                <dl className="metric-list">
                  <div className="metric-row">
                    <dt>{t.status}</dt>
                    <dd>{pilotLaunch?.status ?? t.statusUnknown}</dd>
                  </div>
                  <div className="metric-row">
                    <dt>Enterprise Hat A</dt>
                    <dd>{pilotLaunch?.enterpriseHatA.status ?? t.statusUnknown}</dd>
                  </div>
                  <div className="metric-row">
                    <dt>{t.installRehearsal}</dt>
                    <dd>{pilotLaunch?.installRehearsal.status ?? t.statusUnknown}</dd>
                  </div>
                  <div className="metric-row">
                    <dt>{t.securityReview}</dt>
                    <dd>{pilotLaunch?.securityReview.status ?? t.statusUnknown}</dd>
                  </div>
                </dl>
              </article>
              <DesignPartnerBetaReadinessCard
                codeIntelligence={codeIntelligence}
                pilotOperations={pilotOperations}
                designPartnerBeta={designPartnerBeta}
                labels={{
                  title: t.betaOperations,
                  status: t.status,
                  codeIntelligence: t.codeIntelligence,
                  pilotOperations: t.pilotOperations,
                  feedbackBundle: t.feedbackBundle,
                  fallowTelemetry: t.fallowTelemetry,
                  secretScan: t.secretScan,
                  externalAgentGateway: t.externalAgentGateway,
                  ciInventory: t.ciInventory,
                  claimBoundary: t.claimBoundary,
                  nextActions: t.betaNextActions,
                  blockers: t.betaBlockers,
                  warnings: t.betaWarnings,
                  baselineDebt: t.baselineDebt,
                  ready: t.ready,
                  missing: t.missing,
                  none: t.none,
                }}
              />
              <article className="page-card">
                <h3>{t.capabilityContract}</h3>
                <PayloadSummary value={{ profiles: supportedProfiles, features }} title="Contract summary" maxItems={12} />
                <JsonPanel value={{ profiles: supportedProfiles, features }} />
              </article>
            </div>
          </section>
        ) : null}

        {activeView === 'memory-governance' ? (
          <MemoryGovernanceView snapshot={memoryGovernance} locale={locale} />
        ) : null}

        {activeView === 'enterprise-workspace' ? (
          <EnterpriseWorkspaceOverview snapshot={enterpriseWorkspace} locale={locale} />
        ) : null}

        {activeView === 'enterprise-users' ? (
          <UsersMembershipsView snapshot={enterpriseWorkspace} locale={locale} />
        ) : null}

        {activeView === 'enterprise-roles' ? (
          <RolesPermissionsView snapshot={enterpriseWorkspace} locale={locale} />
        ) : null}

        {activeView === 'enterprise-enrollment' ? (
          <AgentEnrollmentView snapshot={enterpriseWorkspace} locale={locale} />
        ) : null}

        {activeView === 'enterprise-fleet' ? (
          <AgentFleetView snapshot={enterpriseWorkspace} locale={locale} />
        ) : null}

        {activeView === 'enterprise-identity' ? (
          <IdentityHealthView snapshot={enterpriseWorkspace} locale={locale} />
        ) : null}

        {activeView === 'memory-runtime' ? (
          <>
            <MemoryRuntimeView runtime={memoryRuntime} sync={memorySync} locale={locale} />
            <section className="workspace">
              <div className="section-grid">
                <MemoryRuntimePolicyView snapshot={memoryPolicyEnforcement} locale={locale} />
              </div>
            </section>
          </>
        ) : null}

        {activeView === 'memory-authority' ? (
          <MemoryAuthorityView authority={memoryAuthority} locale={locale} />
        ) : null}

        {activeView === 'memory-semantic' ? (
          <MemorySemanticIndexView snapshot={memorySemanticIndex} locale={locale} />
        ) : null}

        {activeView === 'governed-pilot-workflow' ? (
          <GovernedPilotWorkflowView snapshot={governedPilotWorkflow} locale={locale} />
        ) : null}

        {activeView === 'design-partner-field-evidence' ? (
          <DesignPartnerFieldEvidenceView snapshot={designPartnerFieldEvidence} locale={locale} />
        ) : null}

        {activeView === 'design-partner-handoff' ? (
          <DesignPartnerHandoffView snapshot={designPartnerHandoff} locale={locale} />
        ) : null}

        {activeView === 'mainline-rc-freeze' ? (
          <MainlineRcFreezeView snapshot={mainlineRcFreeze} locale={locale} />
        ) : null}

        {activeView === 'rc-gate-evidence' ? (
          <RcGateEvidenceView snapshot={rcGateEvidence} locale={locale} />
        ) : null}

        {activeView === 'rc-release-decision' ? (
          <ReleaseDecisionView snapshot={rcReleaseDecision} locale={locale} />
        ) : null}

        {activeView === 'operations' ? (
          <section className="workspace" data-testid="page-primary-region">
            <div className="workspace-header">
              <div>
                <p className="workspace-kicker">{t.operationsKicker}</p>
                <h2>{t.operations}</h2>
                <p className="workspace-lead">{t.operationsLead}</p>
              </div>
              <div className="workspace-actions">
                <button
                  className="ghost-btn"
                  type="button"
                  onClick={() => void runOperation('metrics', () => snapshotMetrics(settings))}
                >
                  {t.quickMetrics}
                </button>
              </div>
            </div>

            <div className="tab-strip">
              {(['identity', 'qualification', 'security', 'keys', 'support', 'maintenance'] as OperationTabKey[]).map((tab) => (
                <button
                  key={tab}
                  type="button"
                  className={operationTab === tab ? 'tab-btn tab-btn-active' : 'tab-btn'}
                  onClick={() => setOperationTab(tab)}
                >
                  {tab === 'identity'
                    ? t.identity
                    : tab === 'qualification'
                      ? t.qualification
                      : tab === 'security'
                        ? t.security
                        : tab === 'keys'
                          ? t.keys
                          : tab === 'support'
                            ? t.support
                            : t.maintenance}
                </button>
              ))}
            </div>

            {operationTab === 'identity' ? (
              <div className="section-grid two-up">
                <article className="page-card">
                  <h3>{t.identity}</h3>
                  <OperationCommandList
                    operations={operationDescriptors}
                    categories={operationCategoriesForTab('identity')}
                    emptyMessage="Identity operation descriptors are loading from the control-plane snapshot."
                    locale={locale}
                  />
                  <div className="stack-actions">
                    <button className="action-btn" type="button" onClick={() => void runOperation('identity', () => fetchIdentity(settings))}>
                      {t.whoAmI}
                    </button>
                  </div>
                  <label className="field">
                    <span>{t.permission}</span>
                    <input
                      value={operationsForm.permission}
                      onChange={(event) => setOperationsForm((prev) => ({ ...prev, permission: event.target.value }))}
                    />
                  </label>
                  <button
                    className="ghost-btn"
                    type="button"
                    onClick={() => void runOperation('identity', () => checkPermission(settings, operationsForm.permission))}
                  >
                    {t.checkPermission}
                  </button>
                </article>
                <article className="page-card">
                  <h3>{t.operationOutput}</h3>
                  <PayloadSummary value={operationOutputs.identity ?? {}} title="Operation summary" maxItems={20} />
                  <JsonPanel value={operationOutputs.identity ?? {}} />
                </article>
              </div>
            ) : null}

            {operationTab === 'qualification' ? (
              <div className="section-grid two-up">
                <article className="page-card">
                  <h3>{t.qualification}</h3>
                  <OperationCommandList
                    operations={operationDescriptors}
                    categories={operationCategoriesForTab('qualification')}
                    emptyMessage="Qualification operation descriptors are loading from the control-plane snapshot."
                    locale={locale}
                  />
                  <div className="form-grid compact-grid">
                    <label className="field">
                      <span>{t.mode}</span>
                      <input
                        value={operationsForm.qualificationMode}
                        onChange={(event) =>
                          setOperationsForm((prev) => ({ ...prev, qualificationMode: event.target.value }))
                        }
                      />
                    </label>
                    <label className="field">
                      <span>{t.soakHours}</span>
                      <input
                        value={operationsForm.qualificationSoakHours}
                        onChange={(event) =>
                          setOperationsForm((prev) => ({ ...prev, qualificationSoakHours: event.target.value }))
                        }
                      />
                    </label>
                    <label className="field field-span">
                      <span>{t.outputRoot}</span>
                      <input
                        value={operationsForm.qualificationOutputRoot}
                        onChange={(event) =>
                          setOperationsForm((prev) => ({ ...prev, qualificationOutputRoot: event.target.value }))
                        }
                      />
                    </label>
                    <label className="field field-span">
                      <span>{t.workloads}</span>
                      <input
                        value={operationsForm.qualificationWorkloads}
                        onChange={(event) =>
                          setOperationsForm((prev) => ({ ...prev, qualificationWorkloads: event.target.value }))
                        }
                      />
                    </label>
                  </div>
                  <div className="toolbar-row">
                    <button className="action-btn" type="button" onClick={() => void runOperation('qualification', () => snapshotMetrics(settings))}>
                      {t.metricsSnapshot}
                    </button>
                    <button
                      className="ghost-btn"
                      type="button"
                      onClick={() =>
                        void runOperation('qualification', () =>
                          fetchGaReadiness(settings, {
                            report: operationsForm.readinessReport,
                            qualificationReport: operationsForm.readinessQualificationReport,
                          }),
                        )
                      }
                    >
                      {t.gaReadiness}
                    </button>
                    <button
                      className="action-btn"
                      type="button"
                      onClick={() =>
                        void runOperation('qualification', () =>
                          runQualification(settings, {
                            mode: operationsForm.qualificationMode,
                            soakHours: Number(operationsForm.qualificationSoakHours) || 6,
                            outputRoot: operationsForm.qualificationOutputRoot,
                            workloads: operationsForm.qualificationWorkloads || undefined,
                            mergeFromReport: operationsForm.qualificationMergeFromReport || undefined,
                          }),
                        )
                      }
                    >
                      {t.runQualification}
                    </button>
                    <button
                      className="ghost-btn"
                      type="button"
                      onClick={() =>
                        void runOperation('qualification', () =>
                          runInstallRehearsal(settings, {
                            targetRoot: '.imperaos/rehearsal/design-partner',
                            output: 'artifacts/install-rehearsal/report.json',
                            mode: 'source-cli',
                          }),
                        )
                      }
                    >
                      {t.installRehearsal}
                    </button>
                  </div>
                </article>
                <article className="page-card">
                  <h3>{t.operationOutput}</h3>
                  <PayloadSummary value={operationOutput} title="Operation summary" maxItems={20} />
                  <JsonPanel value={operationOutput} />
                </article>
              </div>
            ) : null}

            {operationTab === 'security' ? (
              <div className="section-grid two-up">
                <article className="page-card">
                  <h3>{t.security}</h3>
                  <OperationCommandList
                    operations={operationDescriptors}
                    categories={operationCategoriesForTab('security')}
                    emptyMessage="Security operation descriptors are loading from the control-plane snapshot."
                    locale={locale}
                  />
                  <button className="action-btn" type="button" onClick={() => void runOperation('security', () => fetchSecurityBaseline(settings))}>
                    {t.securityBaseline}
                  </button>
                  <button
                    className="ghost-btn"
                    type="button"
                    onClick={() =>
                      void runOperation('security', () =>
                        generateSecurityReview(settings, {
                          outputRoot: 'artifacts/security-review',
                          evidenceRoot: 'artifacts/evidence-corpus/valid',
                        }),
                      )
                    }
                  >
                    {t.securityReview}
                  </button>
                </article>
                <article className="page-card">
                  <h3>{t.operationOutput}</h3>
                  <PayloadSummary value={operationOutput} title="Operation summary" maxItems={20} />
                  <JsonPanel value={operationOutput} />
                </article>
              </div>
            ) : null}

            {operationTab === 'keys' ? (
              <div className="section-grid two-up">
                <article className="page-card">
                  <h3>{t.keys}</h3>
                  <OperationCommandList
                    operations={operationDescriptors}
                    categories={operationCategoriesForTab('keys')}
                    emptyMessage="Key operation descriptors are loading from the control-plane snapshot."
                    locale={locale}
                  />
                  <label className="field">
                    <span>{t.verifyPath}</span>
                    <input
                      value={operationsForm.verifyPath}
                      onChange={(event) => setOperationsForm((prev) => ({ ...prev, verifyPath: event.target.value }))}
                    />
                  </label>
                  <div className="form-grid compact-grid">
                    <label className="field">
                      <span>{t.nextKeyId}</span>
                      <input
                        value={operationsForm.keyNextKeyId}
                        onChange={(event) => setOperationsForm((prev) => ({ ...prev, keyNextKeyId: event.target.value }))}
                      />
                    </label>
                    <label className="field">
                      <span>{t.activateAt}</span>
                      <input
                        value={operationsForm.keyActivateAt}
                        onChange={(event) => setOperationsForm((prev) => ({ ...prev, keyActivateAt: event.target.value }))}
                      />
                    </label>
                    <label className="field">
                      <span>{t.retireAfter}</span>
                      <input
                        value={operationsForm.keyRetireAfter}
                        onChange={(event) => setOperationsForm((prev) => ({ ...prev, keyRetireAfter: event.target.value }))}
                      />
                    </label>
                  </div>
                  <div className="toolbar-row">
                    <button className="action-btn" type="button" onClick={() => void runOperation('keys', () => fetchKeysStatus(settings))}>
                      {t.keysStatus}
                    </button>
                    <button
                      className="ghost-btn"
                      type="button"
                      onClick={() => void runOperation('keys', () => verifySignedArtifact(settings, operationsForm.verifyPath))}
                    >
                      {t.verifyArtifact}
                    </button>
                    <button
                      className="ghost-btn"
                      type="button"
                      onClick={() =>
                        void runOperation('keys', () =>
                          rotateKeyPlan(settings, {
                            nextKeyId: operationsForm.keyNextKeyId || undefined,
                            activateAt: operationsForm.keyActivateAt || undefined,
                            retireAfter: operationsForm.keyRetireAfter || undefined,
                          }),
                        )
                      }
                    >
                      {t.rotatePlan}
                    </button>
                  </div>
                </article>
                <article className="page-card">
                  <h3>{t.operationOutput}</h3>
                  <PayloadSummary value={operationOutput} title="Operation summary" maxItems={20} />
                  <JsonPanel value={operationOutput} />
                </article>
              </div>
            ) : null}

            {operationTab === 'support' ? (
              <div className="section-grid two-up">
                <article className="page-card">
                  <h3>{t.support}</h3>
                  <OperationCommandList
                    operations={operationDescriptors}
                    categories={operationCategoriesForTab('support')}
                    emptyMessage="Support operation descriptors are loading from the control-plane snapshot."
                    locale={locale}
                  />
                  <label className="field">
                    <span>{t.outputPathOptional}</span>
                    <input
                      value={operationsForm.supportOutput}
                      onChange={(event) => setOperationsForm((prev) => ({ ...prev, supportOutput: event.target.value }))}
                    />
                  </label>
                  <button
                    className="action-btn"
                    type="button"
                    onClick={() => void runOperation('support', () => exportSupportBundle(settings, operationsForm.supportOutput || undefined))}
                  >
                    {t.exportSupportBundle}
                  </button>
                </article>
                <article className="page-card">
                  <h3>{t.operationOutput}</h3>
                  <PayloadSummary value={operationOutput} title="Operation summary" maxItems={20} />
                  <JsonPanel value={operationOutput} />
                </article>
              </div>
            ) : null}

            {operationTab === 'maintenance' ? (
              <div className="section-grid two-up">
                <article className="page-card">
                  <h3>{t.maintenance}</h3>
                  <OperationCommandList
                    operations={operationDescriptors}
                    categories={operationCategoriesForTab('maintenance')}
                    emptyMessage="Maintenance operation descriptors are loading from the control-plane snapshot."
                    locale={locale}
                  />
                  <div className="form-grid compact-grid">
                    <label className="field">
                      <span>{t.outputDirOptional}</span>
                      <input
                        value={operationsForm.backupOutputDir}
                        onChange={(event) => setOperationsForm((prev) => ({ ...prev, backupOutputDir: event.target.value }))}
                      />
                    </label>
                    <label className="field">
                      <span>{t.backupDir}</span>
                      <input
                        value={operationsForm.backupVerifyDir}
                        onChange={(event) => setOperationsForm((prev) => ({ ...prev, backupVerifyDir: event.target.value }))}
                      />
                    </label>
                    <label className="field">
                      <span>{t.restoreBackupDir}</span>
                      <input
                        value={operationsForm.restoreVerifyDir}
                        onChange={(event) => setOperationsForm((prev) => ({ ...prev, restoreVerifyDir: event.target.value }))}
                      />
                    </label>
                  </div>
                  <div className="toolbar-row">
                    <button
                      className="action-btn"
                      type="button"
                      onClick={() => void runOperation('maintenance', () => createBackup(settings, operationsForm.backupOutputDir || undefined))}
                    >
                      {t.createBackup}
                    </button>
                    <button
                      className="ghost-btn"
                      type="button"
                      onClick={() => void runOperation('maintenance', () => verifyBackup(settings, operationsForm.backupVerifyDir))}
                    >
                      {t.verifyBackup}
                    </button>
                    <button
                      className="ghost-btn"
                      type="button"
                      onClick={() => void runOperation('maintenance', () => verifyRestore(settings, operationsForm.restoreVerifyDir))}
                    >
                      {t.verifyRestore}
                    </button>
                    <button className="ghost-btn" type="button" onClick={() => void runOperation('maintenance', () => planMigration(settings))}>
                      {t.migratePlan}
                    </button>
                    <button className="ghost-btn" type="button" onClick={() => void runOperation('maintenance', () => dryRunMigration(settings))}>
                      {t.migrateDryRun}
                    </button>
                  </div>
                </article>
                <article className="page-card">
                  <h3>{t.operationOutput}</h3>
                  <PayloadSummary value={operationOutput} title="Operation summary" maxItems={20} />
                  <JsonPanel value={operationOutput} />
                </article>
              </div>
            ) : null}
          </section>
        ) : null}

        {activeView === 'settings' ? (
          <OperatorPageShell
            kicker={t.settingsKicker}
            title={t.settings}
            lead={t.settingsLead}
            status={settings.operatorId.trim() ? (locale === 'tr' ? 'hazır' : 'ready') : (locale === 'tr' ? 'operator id eksik' : 'operator id missing')}
            actions={[
              {
                label: t.save,
                onClick: () => {
                  saveSettings(settings);
                  pushToast('ok', t.saved);
                },
                variant: 'primary',
              },
            ]}
            decisionItems={[
              {
                label: locale === 'tr' ? 'Runtime kapısı' : 'Runtime gate',
                value: settings.operatorId.trim() ? settings.mode : 'blocked',
                detail: settings.operatorId.trim()
                  ? locale === 'tr'
                    ? 'Mutasyonlar operator id ile imzalanabilir.'
                    : 'Mutations can be signed with the operator id.'
                  : t.setOperatorId,
                tone: settings.operatorId.trim() ? 'success' : 'error',
              },
              {
                label: locale === 'tr' ? 'Arayüz' : 'Interface',
                value: settings.locale,
                detail: locale === 'tr' ? 'Dil ve ham payload tercihleri burada tutulur.' : 'Locale and raw payload preferences live here.',
              },
              {
                label: locale === 'tr' ? 'Kaydetme' : 'Save behavior',
                value: locale === 'tr' ? 'Yerel' : 'Local',
                detail: locale === 'tr' ? 'Ayarlar tarayıcı depolamasına yazılır.' : 'Settings are written to browser storage.',
                tone: 'info',
              },
            ]}
            metrics={[
              { label: t.operatorId, value: settings.operatorId.trim() || '-', detail: locale === 'tr' ? 'mutasyon kimliği' : 'mutation identity' },
              { label: t.profile, value: settings.profile, detail: locale === 'tr' ? 'runtime profili' : 'runtime profile' },
              { label: t.mode, value: settings.mode, detail: settings.rootDir },
            ]}
          >
            <div className="section-grid two-up">
              <article className="operator-work-card">
                <h3>{t.runtimeSection}</h3>
                <div className="operator-setting-list">
                  <label className="operator-setting-row">
                    <div>
                      <span>{t.operatorId}</span>
                      <small>{locale === 'tr' ? 'Onay ve execute işlemleri için zorunlu.' : 'Required for approval and execute actions.'}</small>
                    </div>
                    <input
                      aria-label={t.operatorId}
                      value={settings.operatorId}
                      onChange={(event) => updateSettings({ operatorId: event.target.value })}
                      placeholder={t.operatorIdPlaceholder}
                    />
                  </label>
                  <label className="operator-setting-row">
                    <div>
                      <span>{t.rootDir}</span>
                      <small>{locale === 'tr' ? 'Run ve artifact bağlamının kökü.' : 'Root for run and artifact context.'}</small>
                    </div>
                    <input aria-label={t.rootDir} value={settings.rootDir} onChange={(event) => updateSettings({ rootDir: event.target.value })} />
                  </label>
                  <label className="operator-setting-row">
                    <div>
                      <span>{t.mode}</span>
                      <small>{locale === 'tr' ? 'CLI runtime çözümleme modu.' : 'CLI runtime resolution mode.'}</small>
                    </div>
                    <select aria-label={t.mode} value={settings.mode} onChange={(event) => updateSettings({ mode: event.target.value as PanelSettings['mode'] })}>
                      <option value="auto">auto</option>
                      <option value="external">external</option>
                      <option value="bundled">bundled</option>
                    </select>
                  </label>
                  <label className="operator-setting-row">
                    <div>
                      <span>{t.cliPath}</span>
                      <small>{locale === 'tr' ? 'External modda tercih edilen CLI yolu.' : 'Preferred CLI path for external mode.'}</small>
                    </div>
                    <input aria-label={t.cliPath} value={settings.cliPath} onChange={(event) => updateSettings({ cliPath: event.target.value })} />
                  </label>
                  <label className="operator-setting-row">
                    <div>
                      <span>{t.bundledPythonPath}</span>
                      <small>{locale === 'tr' ? 'Bundled runtime için Python yolu.' : 'Python path for bundled runtime.'}</small>
                    </div>
                    <input
                      aria-label={t.bundledPythonPath}
                      value={settings.bundledPythonPath}
                      onChange={(event) => updateSettings({ bundledPythonPath: event.target.value })}
                    />
                  </label>
                </div>
              </article>

              <article className="operator-work-card">
                <h3>{t.interfaceSection}</h3>
                <div className="operator-setting-list">
                  <label className="operator-setting-row">
                    <div>
                      <span>{t.locale}</span>
                      <small>{locale === 'tr' ? 'Uygulama dili otomatik veya manuel seçilir.' : 'Choose automatic or fixed app language.'}</small>
                    </div>
                    <select aria-label={t.locale} value={settings.locale} onChange={(event) => updateSettings({ locale: event.target.value as LocaleMode })}>
                      <option value="auto">auto</option>
                      <option value="en">English</option>
                      <option value="tr">Türkçe</option>
                    </select>
                  </label>
                  <label className="operator-setting-row">
                    <div>
                      <span>{t.updaterMode}</span>
                      <small>{locale === 'tr' ? 'Güncelleme kontrol davranışı.' : 'Update checking behavior.'}</small>
                    </div>
                    <select
                      aria-label={t.updaterMode}
                      value={settings.updaterMode}
                      onChange={(event) => updateSettings({ updaterMode: event.target.value as PanelSettings['updaterMode'] })}
                    >
                      <option value="off">off</option>
                      <option value="manual">manual</option>
                      <option value="auto">auto</option>
                    </select>
                  </label>
                  <label className="operator-setting-row">
                    <div>
                      <span>{t.remoteTelemetry}</span>
                      <small>{locale === 'tr' ? 'Remote telemetry gönderimini kontrol eder.' : 'Controls remote telemetry submission.'}</small>
                    </div>
                    <input
                      aria-label={t.remoteTelemetry}
                      type="checkbox"
                      checked={settings.remoteTelemetry}
                      onChange={(event) => updateSettings({ remoteTelemetry: event.target.checked })}
                    />
                  </label>
                  <label className="operator-setting-row">
                    <div>
                      <span>{t.debugRaw}</span>
                      <small>{locale === 'tr' ? 'Ham JSON görünümü için ayrıca onay ister.' : 'Requires confirmation before raw JSON disclosure.'}</small>
                    </div>
                    <input
                      aria-label={t.debugRaw}
                      type="checkbox"
                      checked={settings.debugRaw}
                      onChange={(event) => updateSettings({ debugRaw: event.target.checked })}
                    />
                  </label>
                </div>
              </article>

              <article className="operator-work-card">
                <h3>{locale === 'tr' ? 'AI runtime' : 'AI runtime'}</h3>
                <div className="operator-setting-list">
                  <label className="operator-setting-row">
                    <div>
                      <span>{locale === 'tr' ? 'Asistan sağlayıcısı' : 'Assistant provider'}</span>
                      <small>{locale === 'tr' ? 'Profil, yerel Ollama veya remote sağlayıcı.' : 'Profile, local Ollama, or remote provider.'}</small>
                    </div>
                    <select
                      aria-label={locale === 'tr' ? 'Asistan sağlayıcısı' : 'Assistant provider'}
                      value={settings.assistantProvider}
                      onChange={(event) => updateSettings({ assistantProvider: event.target.value })}
                    >
                      <option value="">{locale === 'tr' ? 'Profil varsayılanı' : 'Use profile default'}</option>
                      <option value="local-ollama">Ollama local</option>
                      <option value="openai-public">OpenAI</option>
                      <option value="deepseek-public">DeepSeek</option>
                    </select>
                  </label>
                  <label className="operator-setting-row">
                    <div>
                      <span>{locale === 'tr' ? 'Varsayılan model' : 'Default model'}</span>
                      <small>{locale === 'tr' ? 'Boş bırakılırsa profil seçimi kullanılır.' : 'Leave blank to use the profile selection.'}</small>
                    </div>
                    <input
                      aria-label={locale === 'tr' ? 'Varsayılan model' : 'Default model'}
                      value={settings.assistantModel}
                      onChange={(event) => updateSettings({ assistantModel: event.target.value })}
                      placeholder={
                        settings.assistantProvider === 'deepseek-public'
                          ? 'deepseek-v4-flash'
                          : settings.assistantProvider === 'openai-public'
                            ? 'gpt-5.1'
                            : 'qwen3.5:4b'
                      }
                      spellCheck={false}
                    />
                  </label>
                  <div className="operator-setting-row" role="note">
                    <div>
                      <span>{locale === 'tr' ? 'Provider kimlik bilgileri' : 'Provider credentials'}</span>
                      <small>
                        {locale === 'tr'
                          ? 'Kimlik bilgileri güvenilir backend ortamında yönetilir; renderer tarafında saklanmaz.'
                          : 'Credentials are managed by the trusted backend environment and are never stored in the renderer.'}
                      </small>
                    </div>
                  </div>
                </div>
              </article>

              <article className="operator-work-card" aria-label="Artifact Workspace capabilities">
                <h3>Artifact Workspace</h3>
                <dl className="metric-list">
                  <div className="metric-row"><dt>Rollout</dt><dd>{artifactCapabilityStatus === 'failed' ? 'capability unavailable (ARTIFACT_CAPABILITY_UNAVAILABLE)' : artifactCapabilitySnapshot?.rolloutStage ?? (previewMode ? 'preview' : rendererArtifactFeatureFlags.workspace ? artifactCapabilityStatus : 'disabled')}</dd></div>
                  <div className="metric-row"><dt>Workspace</dt><dd>{artifactFeatureFlags.workspace ? 'enabled' : 'disabled'}</dd></div>
                  <div className="metric-row"><dt>Assistant UI runtime</dt><dd>{(artifactCapabilitySnapshot?.features['assistant_ui_runtime.enabled'] ?? artifactFeatureFlags.assistantUiRuntime) ? 'enabled' : 'disabled'}</dd></div>
                  <div className="metric-row"><dt>AI SDK transport</dt><dd>{(artifactCapabilitySnapshot?.features['ai_sdk_tauri_transport.enabled'] ?? artifactFeatureFlags.aiSdkTauriTransport) ? 'enabled' : 'disabled'}</dd></div>
                  <div className="metric-row"><dt>Export</dt><dd>{(artifactCapabilitySnapshot?.features['artifact_workspace.export.enabled'] ?? artifactFeatureFlags.export) ? 'enabled' : 'disabled'}</dd></div>
                  <div className="metric-row"><dt>Backend doctor</dt><dd>{artifactCapabilitySnapshot ? `spreadsheet ${artifactCapabilitySnapshot.licenses.spreadsheet ? 'verified' : 'fallback'} · canvas ${artifactCapabilitySnapshot.licenses.canvas ? 'verified' : 'fallback'}` : artifactCapabilityStatus === 'failed' ? 'capability unavailable; workspace disabled' : 'unavailable'}</dd></div>
                  <div className="metric-row"><dt>Runtime config</dt><dd><span className="inline-token">IMPERAOS_ARTIFACT_WORKSPACE_PROFILE</span> · <span className="inline-token">IMPERAOS_ARTIFACT_*_EDITOR_ENABLED</span></dd></div>
                  {(artifactCapabilitySnapshot
                    ? Object.entries(artifactCapabilitySnapshot.kindCapabilities)
                    : Object.entries({
                        document: { enabled: artifactFeatureFlags.document, editable: artifactFeatureFlags.document, exportable: artifactFeatureFlags.export, adapter: 'renderer gate' },
                        form: { enabled: artifactFeatureFlags.form, editable: artifactFeatureFlags.form, exportable: artifactFeatureFlags.export, adapter: 'renderer gate' },
                        code: { enabled: artifactFeatureFlags.code, editable: artifactFeatureFlags.code, exportable: artifactFeatureFlags.export, adapter: 'renderer gate' },
                        flow: { enabled: artifactFeatureFlags.flow, editable: artifactFeatureFlags.flow, exportable: artifactFeatureFlags.export, adapter: 'renderer gate' },
                        spreadsheet: { enabled: artifactFeatureFlags.spreadsheet, editable: artifactFeatureFlags.spreadsheet, exportable: artifactFeatureFlags.export, adapter: 'bundled fallback' },
                        canvas: { enabled: artifactFeatureFlags.canvas, editable: artifactFeatureFlags.canvas, exportable: artifactFeatureFlags.export, adapter: 'bundled fallback' },
                        slides: { enabled: artifactFeatureFlags.slides, editable: artifactFeatureFlags.slides, exportable: artifactFeatureFlags.export, adapter: 'renderer gate' },
                      })
                  ).map(([kind, capability]) => (
                    <div className="metric-row" key={kind}>
                      <dt>{kind}</dt>
                      <dd>{capability.enabled ? 'enabled' : 'disabled'} · {capability.editable ? 'editable' : 'read-only'} · {capability.exportable ? 'exportable' : 'no export'} · {capability.adapter} · {'requiresLicense' in capability && capability.requiresLicense ? 'license required' : 'no license required'} · {'reasonCode' in capability ? String(capability.reasonCode ?? 'ready') : capability.enabled ? 'ready' : 'renderer flag disabled'}</dd>
                    </div>
                  ))}
                </dl>
              </article>
            </div>
          </OperatorPageShell>
        ) : null}

        {activeView === 'logs' ? <LogsPage events={events} runItems={runItems} snapshot={controlPlaneSnapshot} locale={locale} /> : null}

        {activeView === 'reports' ? (
          <ReportsPage
            operationOutputs={operationOutputs}
            claims={controlPlaneClaims}
            snapshot={controlPlaneSnapshot}
            locale={locale}
          />
        ) : null}

        {activeView === 'alerts' ? (
          <AlertsPage
            driftEvents={driftEvents}
            pendingApprovals={pendingApprovals}
            claims={controlPlaneClaims}
            snapshot={controlPlaneSnapshot}
            locale={locale}
          />
        ) : null}

        {activeView === 'plans' ? <PlansPage profile={settings.profile} snapshot={controlPlaneSnapshot} locale={locale} /> : null}

        {activeView === 'users' ? (
          <UsersPage operatorId={settings.operatorId.trim()} profile={settings.profile} snapshot={controlPlaneSnapshot} locale={locale} />
        ) : null}

        {activeView === 'roles' ? <RolesPage profile={settings.profile} snapshot={controlPlaneSnapshot} locale={locale} /> : null}

        {activeView === 'policy-packs' ? (
          <PolicyPacksPage claims={controlPlaneClaims} snapshot={controlPlaneSnapshot} locale={locale} />
        ) : null}
        <ExportArtifactsModal
          open={exportModalOpen}
          runId={selectedRunId}
          initialPath={exportPath || `./exports/${selectedRunId || 'run'}`}
          submitting={exportSubmitting}
          locale={locale}
          onClose={() => setExportModalOpen(false)}
          onSubmit={(path) => void onConfirmExportArtifacts(path)}
        />
    </AppShell>
  );
}

function App() {
  const [settings, setSettings] = useState<PanelSettings>(() => loadSettings());

  function updateSettings(next: Partial<PanelSettings>) {
    setSettings((prev) => {
      const merged = { ...prev, ...next };
      saveSettings(merged);
      return merged;
    });
  }

  return (
    <ThemeProvider mode={settings.theme}>
      <AppContent settings={settings} updateSettings={updateSettings} />
    </ThemeProvider>
  );
}

export default App;
