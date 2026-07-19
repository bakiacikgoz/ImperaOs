import previewControlPlaneSnapshotFixture from '../../../contracts/operator_panel/fixtures/control_plane_snapshot_preview.json';
import previewBundle from '../../../contracts/operator_panel/fixtures/operator_panel_preview.json';

export {
  getAssistantFixture as previewAssistantFixture,
  previewAssistantEvents,
  previewAssistantStartTurn,
} from './assistant/assistantFixtures';

import type { ComputerUseRuntimeChoice } from './capabilities';
import type { PanelSettings } from './settings';

type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };

function cloneValue<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function replaceRootInValue(value: JsonValue, rootDir: string): JsonValue {
  if (typeof value === 'string') {
    return value.replaceAll('.imperaos/team/jobs', rootDir);
  }
  if (Array.isArray(value)) {
    return value.map((item) => replaceRootInValue(item, rootDir));
  }
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [key, replaceRootInValue(item, rootDir)]),
    );
  }
  return value;
}

function withRuntimePaths<T>(value: T, rootDir: string): T {
  return replaceRootInValue(cloneValue(value) as JsonValue, rootDir) as T;
}

export function previewHandshake(settings: PanelSettings) {
  const payload = cloneValue(previewBundle.handshake);
  payload.profile = settings.profile;
  payload.rootDir = settings.rootDir;
  payload.mode = settings.mode;
  payload.capabilities.previewMode = true;
  payload.capabilities.features.computerUsePilot = {
    enabled: true,
    stage: 'execution_slice',
    platform: 'macos',
    scope: 'browser+desktop+file',
    executionModes: ['dry_run', 'step_approval', 'execute'],
    replayable: true,
    failClosed: true,
    adapterStatus: 'safari_applescript',
    reasonCode: 'MACOS_COMPUTER_USE_PILOT',
    summary: 'macOS pilot preview is qualification-gated; Windows live computer-use remains disabled.',
  };
  payload.capabilities.commands.computerUseSubmit = true;
  payload.capabilities.commands.computerUsePause = true;
  payload.capabilities.commands.computerUseResume = true;
  payload.capabilities.commands.computerUseStop = true;
  payload.capabilities.commands.computerUseStateJson = true;
  payload.capabilities.commands.computerUseSummaryJson = true;
  payload.doctor.profile = settings.profile;
  return payload;
}

export function previewSubmitResponse(settings: PanelSettings, jobId?: string) {
  const payload = cloneValue(previewBundle.submitTeamRun);
  payload.jobId = jobId || payload.jobId;
  payload.profile = settings.profile;
  payload.rootDir = settings.rootDir;
  return payload;
}

function previewComputerUseStatus(settings: PanelSettings, jobId?: string) {
  const runPayload = withRuntimePaths(previewBundle.runDetail, settings.rootDir) as Record<string, unknown>;
  const job = (runPayload.job as Record<string, unknown>) ?? {};
  const resolvedJobId = jobId || String(job.job_id ?? 'job-ui-preview-cu-1');
  const lastControlCommand = {
    command_id: 'ctrl-preview-resume',
    command_type: 'resume',
    issued_at: '2026-03-08T09:10:08Z',
    issued_by: 'operator',
    expected_state: 'awaiting_approval',
    reason: 'approval_not_executed',
  };
  const lastControlResult = {
    command_id: 'ctrl-preview-resume',
    command_type: 'resume',
    outcome: 'rejected',
    processed_at: '2026-03-08T09:10:08Z',
    previous_state: 'awaiting_approval',
    resulting_state: 'awaiting_approval',
    reason: 'approval_not_executed',
    deferred_until_safe_checkpoint: false,
  };
  job.job_id = resolvedJobId;
  job.team_id = 'imperaos-computer-use';
  job.request = job.request || 'open "https://preview.imperaos.local/form"\nclick "#start"\ntype "Preview operator" into "#name"';
  job.status = 'blocked';
  runPayload.computer_use = {
    mode: 'step_approval',
    session_state: 'awaiting_approval',
    lifecycle_state: 'awaiting_approval',
    stage: 'require_approval',
    active_action: 'click',
    current_url: 'https://preview.imperaos.local/form',
    active_app: 'browser:safari',
    active_window: 'safari:ImperaOS Preview Form',
    pending_approval_id: 'apr_20260308_device_action',
    paused: true,
    stopped: false,
    stopped_by_user: false,
    resume_allowed: false,
    pending_command: null,
    last_safe_checkpoint: 'approval_wait',
    last_control_command: lastControlCommand,
    last_control_result: lastControlResult,
    last_processed_command_id: 'ctrl-preview-resume',
    last_verified_effect: 'Open https://preview.imperaos.local/form.',
    last_error: null,
    last_verification_result: {
      verified: true,
      kind: 'navigation',
      summary: 'Verified the preview form URL before requesting approval.',
    },
    artifacts: {
      upload_file: {
        selected_file: `${settings.rootDir}/attachments/brief.txt`,
      },
    },
    world_model: {
      active_run_id: resolvedJobId,
      objective: job.request,
      stage: 'require_approval',
      last_known_status: 'blocked',
      execution_state: 'awaiting_approval',
      active_window: {
        window_identity: 'safari:ImperaOS Preview Form',
        app_identity: 'browser:safari',
        surface_kind: 'browser',
        focused: true,
      },
      open_windows: [],
      active_application_identity: 'browser:safari',
      active_surface: 'browser:safari:https://preview.imperaos.local/form',
      focused_window_title: 'ImperaOS Preview Form',
      current_url: 'https://preview.imperaos.local/form',
      browser_tab_title: 'ImperaOS Preview Form',
      observed_targets: [],
      visible_target_set: ['#start', '#name', '#resume'],
      changed_resources: [],
      pending_approval_ids: ['apr_20260308_device_action'],
      pending_dialog_state: {
        dialog_open: false,
      },
      selected_file_state: {
        selected_path: `${settings.rootDir}/attachments/brief.txt`,
      },
      filesystem_result_set: [],
      last_completed_action: 'open_url',
      last_verified_effect: 'Open https://preview.imperaos.local/form.',
      last_verification_result: {
        verified: true,
        summary: 'Verified the preview form URL before requesting approval.',
      },
      last_safe_checkpoint: 'approval_wait',
      pending_control: null,
      resume_allowed: false,
      last_control_result: lastControlResult,
      drift_detected: false,
      user_intervention_required: true,
      interruption_state: 'awaiting_approval',
      notes: ['preview-mode'],
    },
    recorder: {
      mode: 'step_approval',
      traces: [],
    },
    event_count: 6,
    steps: [
      {
        step_index: 0,
        before_hash: 'a'.repeat(64),
        execution_status: 'approval_required',
        action: {
          action_id: 'click_start_button',
          action_type: 'click',
          target_element_id: 'start_button',
          rationale: 'The local preview form start button is visible.',
          expected_effect: 'The preview form advances to the name field.',
          risk_class: 'medium',
          requires_approval: true,
          confidence: 0.91,
        },
        policy_decision: {
          reason_code: 'COMPUTER_USE_APPROVAL_REQUIRED',
        },
        approval_snapshot: {
          status: 'pending',
          raw_screenshot_path: null,
        },
        verification: {
          status: 'satisfied',
          reason_code: 'VISION_VERIFICATION_SATISFIED',
        },
      },
    ],
  };
  return runPayload;
}

export function previewComputerUseSubmitResponse(
  settings: PanelSettings,
  jobId?: string,
  runtime?: ComputerUseRuntimeChoice,
) {
  const payload = previewSubmitResponse(settings, jobId || 'job-ui-preview-cu-1') as Record<string, unknown>;
  payload.jobId = jobId || 'job-ui-preview-cu-1';
  payload.runtime = runtime ?? 'vision-first';
  return payload;
}

export function previewComputerUseSummary(settings: PanelSettings, limit = 20) {
  return {
    contractVersion: previewBundle.contractVersion,
    status: 'ok',
    checked_at: '2026-03-08T09:42:00Z',
    artifact_root: settings.rootDir,
    window: {
      limit: Math.max(1, Math.min(limit, 200)),
      observed: 4,
    },
    counts: {
      success: 1,
      blocked: 1,
      failed: 1,
      stopped: 1,
      active: 0,
    },
    recent_runs: [
      {
        job_id: 'job-ui-preview-cu-1',
        job_status: 'blocked',
        session_state: 'awaiting_approval',
        outcome: 'blocked',
        failure_code: 'approval_not_executed',
        finished_at: '2026-03-08T09:10:08Z',
        created_at: '2026-03-08T09:10:00Z',
      },
    ],
    top_failure_codes: [{ code: 'approval_not_executed', count: 1 }],
    last_success_at: '2026-03-08T08:42:00Z',
    last_blocked_at: '2026-03-08T09:10:08Z',
    last_failed_at: '2026-03-07T17:15:00Z',
    last_stopped_at: '2026-03-07T16:05:00Z',
    readiness_status: 'blocked',
    readiness_blockers: ['VISION_PROVIDER_UNAVAILABLE', 'COMPUTER_USE_EVIDENCE_MISSING'],
    readiness_warnings: [],
    summary: 'Recent pilot outcomes: 1 success, 1 blocked, 1 failed, 1 stopped, 0 active.',
  };
}

export function previewComputerUseControl(jobId: string, requested: 'pause' | 'resume' | 'stop') {
  const reason =
    requested === 'pause'
      ? 'pause_not_allowed_while_awaiting_approval'
      : requested === 'resume'
        ? 'approval_not_executed'
        : null;
  return {
    contract_version: '3.0',
    job_id: jobId,
    requested,
    command_id: `ctrl-preview-${requested}`,
    outcome: requested === 'stop' ? 'accepted' : 'rejected',
    reason,
  };
}

export function previewComputerUseSessionState(settings: PanelSettings, jobId?: string) {
  const payload = previewComputerUseStatus(settings, jobId) as Record<string, unknown>;
  const computerUse = (payload.computer_use as Record<string, unknown>) ?? {};
  return {
    job_id: String((payload.job as Record<string, unknown>).job_id ?? jobId ?? 'job-ui-preview-cu-1'),
    registry: {
      job_id: String((payload.job as Record<string, unknown>).job_id ?? jobId ?? 'job-ui-preview-cu-1'),
      job_dir: `${settings.rootDir}/${String((payload.job as Record<string, unknown>).job_id ?? jobId ?? 'job-ui-preview-cu-1')}`,
      pid: 4242,
      state: computerUse.lifecycle_state ?? 'awaiting_approval',
      updated_at: '2026-03-08T09:41:00Z',
    },
    computer_use: computerUse,
    job: payload.job ?? {},
    recovery: {
      recoverable_state: 'awaiting_approval',
      last_processed_command_id: 'ctrl-preview-resume',
      last_completed_action_index: 0,
      pending_control_command: null,
      resume_allowed: false,
      control_history: [
        {
          command_id: 'ctrl-preview-resume',
          command_type: 'resume',
          outcome: 'rejected',
          processed_at: '2026-03-08T09:10:08Z',
          previous_state: 'awaiting_approval',
          resulting_state: 'awaiting_approval',
          reason: 'approval_not_executed',
        },
      ],
    },
  };
}

export function previewApprovalPending() {
  return cloneValue(previewBundle.approvalPending);
}

export function previewApprovalDetail(approvalId?: string) {
  const payload = cloneValue(previewBundle.approvalDetail);
  if (approvalId) {
    payload.approval_id = approvalId;
    payload.ticket.approval_id = approvalId;
  }
  return payload;
}

export function previewRunSummary(settings: PanelSettings) {
  const payload = withRuntimePaths(previewBundle.runSummary, settings.rootDir);
  payload.root_dir = settings.rootDir;
  return payload;
}

export function previewRunDetail(settings: PanelSettings, jobId?: string) {
  return previewComputerUseStatus(settings, jobId);
}

export function previewRunReplay(jobId?: string) {
  const payload = cloneValue(previewBundle.runReplay);
  if (jobId) {
    payload.job_id = jobId;
  }
  return payload;
}

export function previewArtifact(settings: PanelSettings, jobId: string, artifactName: string) {
  const payloads = {
    'status.json': previewRunDetail(settings, jobId),
    'tasks.json': cloneValue(previewBundle.readArtifact.tasks),
    'handoffs.json': cloneValue(previewBundle.readArtifact.handoffs),
    'audit_envelope.json': withRuntimePaths(previewBundle.readArtifact.auditEnvelope, settings.rootDir),
  } as const;

  return {
    contractVersion: previewBundle.contractVersion,
    artifactName,
    payload: payloads[artifactName as keyof typeof payloads] ?? {},
    truncated: false,
    bytesRead: 1024,
  };
}

export function previewTailEvents() {
  const payload = cloneValue(previewBundle.tailEvents) as {
    contractVersion: string;
    events: unknown[];
    nextCursor: number;
    reset: boolean;
    truncated: boolean;
    badLineCount: number;
  };
  payload.events = [
    {
      schema_version: '3',
      event: 'session_started',
      event_id: 'evt-preview-cu-1',
      event_seq: 1,
      timestamp: '2026-03-08T09:10:00Z',
      team_id: 'imperaos-computer-use',
      case_id: 'case-preview',
      job_id: 'job-ui-preview-cu-1',
      phase: 'computer_use',
      status_before: 'pending',
      status_after: 'running',
      data: {
        mode: 'step_approval',
        action_count: 3,
      },
    },
    {
      schema_version: '3',
      event: 'observation_captured',
      event_id: 'evt-preview-cu-2',
      event_seq: 2,
      timestamp: '2026-03-08T09:10:02Z',
      team_id: 'imperaos-computer-use',
      case_id: 'case-preview',
      job_id: 'job-ui-preview-cu-1',
      phase: 'computer_use',
      status_before: 'running',
      status_after: 'running',
      data: {
        action_id: 'open_url',
        current_url: 'https://preview.imperaos.local/form',
        window_identity: 'safari:ImperaOS Preview Form',
      },
    },
    {
      schema_version: '3',
      event: 'action_started',
      event_id: 'evt-preview-cu-3',
      event_seq: 3,
      timestamp: '2026-03-08T09:10:03Z',
      team_id: 'imperaos-computer-use',
      case_id: 'case-preview',
      job_id: 'job-ui-preview-cu-1',
      phase: 'computer_use',
      status_before: 'running',
      status_after: 'running',
      data: {
        action_id: 'open_url',
        selector: 'document',
      },
    },
    {
      schema_version: '3',
      event: 'action_verified',
      event_id: 'evt-preview-cu-4',
      event_seq: 4,
      timestamp: '2026-03-08T09:10:04Z',
      team_id: 'imperaos-computer-use',
      case_id: 'case-preview',
      job_id: 'job-ui-preview-cu-1',
      phase: 'computer_use',
      status_before: 'running',
      status_after: 'running',
      data: {
        action_id: 'open_url',
        verification: {
          verified: true,
        },
      },
    },
    {
      schema_version: '3',
      event: 'approval_required',
      event_id: 'evt-preview-cu-5',
      event_seq: 5,
      timestamp: '2026-03-08T09:10:05Z',
      team_id: 'imperaos-computer-use',
      case_id: 'case-preview',
      job_id: 'job-ui-preview-cu-1',
      phase: 'computer_use',
      status_before: 'running',
      status_after: 'blocked',
      approval_id: 'apr_20260308_device_action',
      data: {
        approval_id: 'apr_20260308_device_action',
        action_id: 'click',
      },
    },
    {
      schema_version: '3',
      event: 'session_paused',
      event_id: 'evt-preview-cu-6',
      event_seq: 6,
      timestamp: '2026-03-08T09:10:05Z',
      team_id: 'imperaos-computer-use',
      case_id: 'case-preview',
      job_id: 'job-ui-preview-cu-1',
      phase: 'computer_use',
      status_before: 'running',
      status_after: 'blocked',
      approval_id: 'apr_20260308_device_action',
      data: {
        reason: 'approval_required',
      },
    },
    {
      schema_version: '3',
      event: 'computer_use.control_command_received',
      event_id: 'evt-preview-cu-7',
      event_seq: 7,
      timestamp: '2026-03-08T09:10:08Z',
      team_id: 'imperaos-computer-use',
      case_id: 'case-preview',
      job_id: 'job-ui-preview-cu-1',
      phase: 'computer_use',
      status_before: 'blocked',
      status_after: 'blocked',
      approval_id: 'apr_20260308_device_action',
      data: {
        command: {
          command_id: 'ctrl-preview-resume',
          command_type: 'resume',
          issued_at: '2026-03-08T09:10:08Z',
          issued_by: 'operator',
          expected_state: 'awaiting_approval',
          reason: 'approval_not_executed',
        },
        session_state: 'awaiting_approval',
      },
    },
    {
      schema_version: '3',
      event: 'computer_use.control_command_rejected',
      event_id: 'evt-preview-cu-8',
      event_seq: 8,
      timestamp: '2026-03-08T09:10:08Z',
      team_id: 'imperaos-computer-use',
      case_id: 'case-preview',
      job_id: 'job-ui-preview-cu-1',
      phase: 'computer_use',
      status_before: 'blocked',
      status_after: 'blocked',
      approval_id: 'apr_20260308_device_action',
      data: {
        command: {
          command_id: 'ctrl-preview-resume',
          command_type: 'resume',
          issued_at: '2026-03-08T09:10:08Z',
          issued_by: 'operator',
          expected_state: 'awaiting_approval',
          reason: 'approval_not_executed',
        },
        result: {
          command_id: 'ctrl-preview-resume',
          command_type: 'resume',
          outcome: 'rejected',
          processed_at: '2026-03-08T09:10:08Z',
          previous_state: 'awaiting_approval',
          resulting_state: 'awaiting_approval',
          reason: 'approval_not_executed',
          deferred_until_safe_checkpoint: false,
        },
      },
    },
  ];
  payload.nextCursor = 3620;
  return payload;
}

export function previewConfigResolve(settings: PanelSettings) {
  const payload = cloneValue(previewBundle.configResolve);
  payload.profile = settings.profile;
  const resolved = payload.resolved as { profile_name?: string; team?: { artifact_dir?: string } };
  resolved.profile_name = settings.profile;
  if (resolved.team) {
    resolved.team.artifact_dir = settings.rootDir;
  }
  return payload;
}

export function previewIdentity(settings: PanelSettings) {
  const payload = cloneValue(previewBundle.operations.identity);
  const actor = payload.actor as { actor_id?: string } | null;
  if (actor && settings.operatorId.trim()) {
    actor.actor_id = settings.operatorId.trim();
  }
  return payload;
}

export function previewPermissionCheck(permission: string) {
  const payload = cloneValue(previewBundle.operations.permissionCheck);
  payload.permission = permission;
  return payload;
}

export function previewSecurityBaseline() {
  return cloneValue(previewBundle.operations.security);
}

export function previewInstallRehearsal(targetRoot?: string, output?: string) {
  return {
    version: 'control-plane.install-rehearsal/v1',
    rehearsalId: 'rehearsal-preview',
    status: 'pass',
    targetRoot: targetRoot || '.imperaos/rehearsal/design-partner',
    outputPath: output || 'artifacts/install-rehearsal/report.json',
    supportBundleSafe: true,
    rollbackPlanPresent: true,
    secretScanStatus: 'pass',
    blockingReasons: [],
  };
}

export function previewSecurityReview(outputRoot?: string, evidenceRoot?: string) {
  return {
    version: 'control-plane.security-review/v1',
    status: 'pass',
    outputRoot: outputRoot || 'artifacts/security-review',
    evidenceRoot: evidenceRoot || 'artifacts/evidence-corpus/valid',
    noSecretScan: { status: 'pass', findings: [] },
    claimConsistency: { status: 'pass', blockingReasons: [] },
    blockingReasons: [],
  };
}

export function previewKeysStatus() {
  return cloneValue(previewBundle.operations.keys);
}

export function previewSupportBundle(output?: string) {
  const payload = cloneValue(previewBundle.operations.support);
  if (output) {
    payload.archive_path = output;
  }
  return payload;
}

export function previewMetricsSnapshot() {
  return cloneValue(previewBundle.operations.metrics);
}

export function previewGaReadiness() {
  return cloneValue(previewBundle.operations.gaReadiness);
}

export function previewQualification() {
  return cloneValue(previewBundle.operations.qualification);
}

export function previewBackupCreate(outputDir?: string) {
  const payload = cloneValue(previewBundle.operations.backupCreate);
  if (outputDir) {
    payload.backup_dir = outputDir;
  }
  return payload;
}

export function previewBackupVerify(backupDir: string) {
  const payload = cloneValue(previewBundle.operations.backupVerify);
  payload.backup_dir = backupDir;
  return payload;
}

export function previewRestoreVerify(backupDir: string) {
  const payload = cloneValue(previewBundle.operations.restoreVerify);
  payload.backup_dir = backupDir;
  return payload;
}

export function previewMigratePlan() {
  return cloneValue(previewBundle.operations.migratePlan);
}

export function previewMigrateApplyDryRun() {
  return cloneValue(previewBundle.operations.migrateApplyDryRun);
}

export function previewControlPlaneDoctor(settings: PanelSettings) {
  return {
    status: 'healthy',
    profile: settings.profile,
    policy_available: true,
    identity_available: true,
    signing_available: true,
    registry_available: true,
    evidence_export_available: true,
    claim_guard_available: true,
    blocking_reasons: [],
  };
}

export function previewControlPlaneAgentList() {
  return {
    agents: [
      {
        agent_id: 'governed-ops',
        display_name: 'Governed Ops Agent',
        runtime_kind: 'imperaos_team',
        agent_type: 'internal',
        status: 'registered',
        readiness: 'policy_simulated',
        owner_team: 'platform-security',
        policy_pack_id: 'active-runtime-policy',
        risk_profile: 'guarded',
        last_run_id: 'cp-run-preview-001',
        last_evidence_pack_id: 'evp-preview-run',
        last_evidence_status: 'pending',
      },
      {
        agent_id: 'external-agent',
        display_name: 'External Gateway Agent',
        runtime_kind: 'external_stdio',
        agent_type: 'external_stdio',
        status: 'registered',
        readiness: 'policy_simulated',
        owner_team: 'platform-security',
        policy_pack_id: 'enterprise_default',
        risk_profile: 'guarded',
        last_run_id: 'cp-ext-run-preview',
        last_evidence_pack_id: null,
        last_evidence_status: 'missing',
      },
    ],
  };
}

export function previewControlPlanePolicySimulation() {
  return {
    version: 'control-plane.policy-simulation/v1',
    agent_id: 'governed-ops',
    policy_hash: 'sha256:preview',
    overall_status: 'conditional',
    summary: { allow: 1, require_approval: 1, deny: 0, unknown: 0 },
    decisions: [
      {
        action_id: 'inspect_queue',
        phase: 'task',
        risk_class: 'read_only',
        decision_action: 'allow',
        reason_code: 'RISK_READ_ONLY_ALLOWED',
        matched_rule_path: 'risk_defaults[read_only]',
        policy_hash: 'sha256:preview',
        approval_id: null,
        qualification_required: false,
      },
      {
        action_id: 'restart_service',
        phase: 'tool',
        risk_class: 'mutation',
        decision_action: 'require_approval',
        reason_code: 'RISK_REQUIRES_APPROVAL',
        matched_rule_path: 'risk_defaults[mutation]',
        policy_hash: 'sha256:preview',
        approval_id: 'apr-preview-control-plane',
        qualification_required: false,
      },
    ],
    blocking_reasons: [],
  };
}

export function previewControlPlaneClaims() {
  return {
    version: 'control-plane.claim-matrix/v1',
    generated_at: '2026-05-31T00:00:00Z',
    claims: [
      {
        claim_id: 'enterprise-self-hosted-agent-control-plane',
        status: 'conditional',
        required_evidence: ['security_baseline', 'qualification', 'ga_readiness', 'signed_evidence_pack'],
        blocking_reasons: ['SIGNED_EVIDENCE_PACK_MISSING'],
      },
      {
        claim_id: 'public-desktop-installer',
        status: 'blocked',
        required_evidence: ['macos_notarization', 'windows_signed_rc', 'clean_machine_smoke'],
        blocking_reasons: ['HAT_B_EVIDENCE_MISSING'],
      },
      {
        claim_id: 'live-windows-computer-use',
        status: 'blocked',
        required_evidence: ['platform_qualification', 'signed_trusted_evidence'],
        blocking_reasons: ['WINDOWS_COMPUTER_USE_NOT_QUALIFIED'],
      },
    ],
  };
}

export function previewControlPlaneSnapshot(settings: PanelSettings) {
  const payload = cloneValue(previewControlPlaneSnapshotFixture);
  payload.system.profile = settings.profile;
  payload.dataSource.sourceReason = 'explicit browser preview fixture';
  return payload;
}
