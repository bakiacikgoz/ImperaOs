from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from imperaos.control_plane.models import (
    ClaimMatrix,
    ControlPlaneRunSummary,
    EvidencePackManifest,
    EvidenceVerifyResult,
    PolicySimulationResult,
    ReadinessReport,
)
from imperaos.governance.models import ApprovalTicket
from imperaos.team.models import JobRun, TaskRun, TeamEvent


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)


class ComputerUseCapabilityContract(ContractModel):
    enabled: bool
    stage: str
    platform: str
    scope: str
    execution_modes: list[str] = Field(alias="executionModes")
    replayable: bool
    fail_closed: bool = Field(alias="failClosed")
    adapter_status: str = Field(alias="adapterStatus")
    reason_code: str | None = Field(default=None, alias="reasonCode")
    summary: str | None = None


class ComputerUsePlatformCapabilityContract(ContractModel):
    platform: Literal["macos", "windows", "linux"]
    stage: Literal[
        "unavailable",
        "disabled",
        "not_configured",
        "missing_permission",
        "provider_unavailable",
        "not_qualified",
        "qualified_available",
        "permission_ready",
        "provider_ready",
        "ready_for_live_fixture",
        "fixture_qualified",
        "qualified_limited",
        "enabled",
        "blocked",
        "ready_for_dry_run",
        "ready_for_step_approval",
        "qualified_supervised_pilot",
    ]
    live_enabled: bool = Field(alias="liveEnabled")
    capture_backend: str = Field(alias="captureBackend")
    input_backend: str = Field(alias="inputBackend")
    provider: str
    permissions: list[str] = Field(default_factory=list)
    execution_modes: list[str] = Field(alias="executionModes")
    replayable: bool
    fail_closed: bool = Field(alias="failClosed")
    reason_code: str | None = Field(default=None, alias="reasonCode")
    summary: str | None = None
    blockers: list[str] = Field(default_factory=list)
    qualification_status: str = Field(default="missing", alias="qualificationStatus")
    fixture_qualified: bool = Field(default=False, alias="fixtureQualified")
    production_qualified: bool = Field(default=False, alias="productionQualified")
    environment: dict[str, str] = Field(default_factory=dict)


class ComputerUseCapabilityEvidencePayload(ContractModel):
    status: str
    source: Literal["none", "default_path", "explicit_path", "fixture", "unknown"] = "none"
    fresh: bool = False
    commit_match: bool = Field(False, alias="commitMatch")
    config_match: bool = Field(False, alias="configMatch")
    provider_match: bool = Field(False, alias="providerMatch")
    backend_match: bool = Field(False, alias="backendMatch")


class ComputerUseCapabilityConfigPayload(ContractModel):
    vision_enabled: bool = Field(False, alias="visionEnabled")
    provider: str = "none"
    capture_backend: str = Field("disabled", alias="captureBackend")
    input_backend: str = Field("disabled", alias="inputBackend")
    raw_screenshot_persistence: bool = Field(False, alias="rawScreenshotPersistence")
    terminal_policy: str = Field("deny", alias="terminalPolicy")


class ComputerUseCapabilityDriverPayload(ContractModel):
    ready: bool = False
    capture_ready: bool = Field(False, alias="captureReady")
    input_ready: bool = Field(False, alias="inputReady")
    permission_ready: bool = Field(False, alias="permissionReady")


class ComputerUseCapabilitySafetyPayload(ContractModel):
    fail_closed: bool = Field(True, alias="failClosed")
    raw_screenshot_persistence_allowed: bool = Field(
        False,
        alias="rawScreenshotPersistenceAllowed",
    )
    requires_step_approval: bool = Field(True, alias="requiresStepApproval")
    sensitive_surface_stop_enabled: bool = Field(True, alias="sensitiveSurfaceStopEnabled")


class ComputerUseCapabilityResolutionPayload(ContractModel):
    schema_version: Literal[1] = Field(1, alias="schemaVersion")
    platform: Literal["macos", "windows", "linux", "unknown"]
    profile: str | None = None
    status: str
    live_enabled: Literal[False] = Field(False, alias="liveEnabled")
    supervised_live_allowed: bool = Field(False, alias="supervisedLiveAllowed")
    public_live_claim_allowed: Literal[False] = Field(
        False,
        alias="publicLiveClaimAllowed",
    )
    reason_code: str | None = Field(None, alias="reasonCode")
    blockers: list[str] = Field(default_factory=list)
    evidence: ComputerUseCapabilityEvidencePayload
    config: ComputerUseCapabilityConfigPayload
    driver: ComputerUseCapabilityDriverPayload
    safety: ComputerUseCapabilitySafetyPayload


class ComputerUseVisionRuntimeCapabilityContract(ContractModel):
    enabled: bool
    stage: Literal[
        "configured",
        "not_configured",
        "missing_permission",
        "provider_unavailable",
        "not_qualified",
        "qualified_available",
        "permission_ready",
        "provider_ready",
        "ready_for_live_fixture",
        "fixture_qualified",
        "qualified_limited",
        "enabled",
        "qualified",
        "qualified_supervised_pilot",
        "ready_for_dry_run",
        "ready_for_step_approval",
        "blocked",
    ]
    platform: Literal["macos", "windows", "linux", "unknown"]
    scope: Literal["vision_first_desktop_web_file"]
    execution_modes: list[str] = Field(alias="executionModes")
    replayable: bool
    fail_closed: bool = Field(alias="failClosed")
    reason_code: str | None = Field(default=None, alias="reasonCode")
    summary: str | None = None
    provider: dict[str, Any] = Field(default_factory=dict)
    safety: dict[str, Any] = Field(default_factory=dict)
    platforms: dict[str, ComputerUsePlatformCapabilityContract] = Field(default_factory=dict)
    capability_resolution: ComputerUseCapabilityResolutionPayload | None = Field(
        None,
        alias="capabilityResolution",
    )


class OperatorFeatureFlagsContract(ContractModel):
    operator_workflow_parity: bool = Field(alias="operatorWorkflowParity")
    enterprise_ops_parity: bool = Field(alias="enterpriseOpsParity")
    computer_use_pilot: ComputerUseCapabilityContract = Field(alias="computerUsePilot")
    computer_use_vision_runtime: ComputerUseVisionRuntimeCapabilityContract = Field(
        alias="computerUseVisionRuntime"
    )


class OperatorCommandCapabilitiesContract(ContractModel):
    approval_pending_json: bool = Field(alias="approvalPendingJson")
    approval_show_json: bool = Field(alias="approvalShowJson")
    approval_decide: bool = Field(alias="approvalDecide")
    approval_execute: bool = Field(alias="approvalExecute")
    computer_use_submit: bool = Field(alias="computerUseSubmit")
    computer_use_pause: bool = Field(alias="computerUsePause")
    computer_use_resume: bool = Field(alias="computerUseResume")
    computer_use_stop: bool = Field(alias="computerUseStop")
    computer_use_state_json: bool = Field(alias="computerUseStateJson")
    computer_use_summary_json: bool = Field(alias="computerUseSummaryJson")
    team_submit: bool = Field(alias="teamSubmit")
    team_resume_submit: bool = Field(alias="teamResumeSubmit")
    team_list_json: bool = Field(alias="teamListJson")
    team_status_json: bool = Field(alias="teamStatusJson")
    team_replay_json: bool = Field(alias="teamReplayJson")
    config_resolve_json: bool = Field(alias="configResolveJson")
    auth_whoami_json: bool = Field(alias="authWhoamiJson")
    auth_check_json: bool = Field(alias="authCheckJson")
    security_baseline_json: bool = Field(alias="securityBaselineJson")
    keys_status_json: bool = Field(alias="keysStatusJson")
    keys_verify_json: bool = Field(alias="keysVerifyJson")
    keys_rotate_plan_json: bool = Field(alias="keysRotatePlanJson")
    support_bundle_export_json: bool = Field(alias="supportBundleExportJson")
    metrics_snapshot_json: bool = Field(alias="metricsSnapshotJson")
    ga_readiness_json: bool = Field(alias="gaReadinessJson")
    qualification_run_json: bool = Field(alias="qualificationRunJson")
    backup_create_json: bool = Field(alias="backupCreateJson")
    backup_verify_json: bool = Field(alias="backupVerifyJson")
    restore_verify_json: bool = Field(alias="restoreVerifyJson")
    migrate_plan_json: bool = Field(alias="migratePlanJson")
    migrate_apply_dry_run_json: bool = Field(alias="migrateApplyDryRunJson")


class OperatorCapabilitiesPayload(ContractModel):
    core_version: str = Field(alias="coreVersion")
    contract_version: Literal["3.0"] = Field(alias="contractVersion")
    profiles: list[str]
    preview_mode: bool | None = Field(default=None, alias="previewMode")
    features: OperatorFeatureFlagsContract
    commands: OperatorCommandCapabilitiesContract
    artifact_schema: dict[str, str] = Field(default_factory=dict, alias="artifactSchema")


class ControlPlaneAgentListPayloadContract(ContractModel):
    agents: list[dict[str, Any]] = Field(default_factory=list)


class ControlPlaneRunSummaryPayloadContract(ControlPlaneRunSummary):
    pass


class ControlPlanePolicySimulationPayloadContract(PolicySimulationResult):
    pass


class ControlPlaneEvidenceExportPayloadContract(EvidencePackManifest):
    pass


class ControlPlaneEvidenceVerifyPayloadContract(EvidenceVerifyResult):
    pass


class ControlPlaneReadinessPayloadContract(ReadinessReport):
    pass


class ControlPlaneClaimMatrixPayloadContract(ClaimMatrix):
    pass


class BridgeHandshakeContract(ContractModel):
    ui_version: str = Field(alias="uiVersion")
    core_version: str = Field(alias="coreVersion")
    profile: str
    contract_version: Literal["3.0"] = Field(alias="contractVersion")
    capabilities: OperatorCapabilitiesPayload
    doctor: dict[str, Any]
    root_dir: str = Field(alias="rootDir")
    mode: str


class SpawnedRunPayloadContract(ContractModel):
    contract_version: Literal["3.0"] = Field(alias="contractVersion")
    job_id: str = Field(alias="jobId")
    profile: str
    root_dir: str = Field(alias="rootDir")
    process_id: int | None = Field(alias="processId")


class AssistantStartTurnPayloadContract(ContractModel):
    contract_version: Literal["3.0"] = Field(alias="contractVersion")
    assistant_turn_id: str = Field(alias="assistantTurnId")
    session_id: str = Field(alias="sessionId")
    process_id: int | None = Field(alias="processId")
    status: Literal["started"]


class AssistantArtifactEventDataContract(ContractModel):
    artifact_id: str = Field(alias="artifactId", min_length=1, max_length=128)
    revision_id: str | None = Field(default=None, alias="revisionId", max_length=128)
    proposal_id: str | None = Field(default=None, alias="proposalId", max_length=128)
    approval_id: str | None = Field(default=None, alias="approvalId", max_length=128)
    action_hash: str | None = Field(
        default=None, alias="actionHash", pattern=r"^[a-f0-9]{64}$"
    )
    kind: (
        Literal["document", "form", "code", "flow", "spreadsheet", "canvas", "slides"]
        | None
    ) = None
    title: str | None = Field(default=None, max_length=200)
    base_revision_number: int | None = Field(default=None, alias="baseRevisionNumber", ge=1)
    summary: str | None = Field(default=None, max_length=500)
    status: str | None = Field(default=None, max_length=64)


class AssistantFormRequestedDataContract(ContractModel):
    artifact_id: str = Field(alias="artifactId", min_length=1, max_length=128)
    revision_id: str = Field(alias="revisionId", min_length=1, max_length=128)
    schema_: dict[str, Any] = Field(alias="schema")
    ui_schema: dict[str, Any] = Field(default_factory=dict, alias="uiSchema")
    title: str | None = Field(default=None, max_length=200)


class AssistantFormSubmittedDataContract(ContractModel):
    artifact_id: str = Field(alias="artifactId", min_length=1, max_length=128)
    revision_id: str = Field(alias="revisionId", min_length=1, max_length=128)
    submission_id: str = Field(alias="submissionId", min_length=1, max_length=128)
    status: Literal["accepted", "rejected", "pending_continuation"]


class AssistantToolResultDataContract(ContractModel):
    tool_call_id: str = Field(alias="toolCallId", min_length=1, max_length=128)
    tool_name: str = Field(alias="toolName", min_length=1, max_length=128)
    status: Literal["succeeded", "failed", "denied"]
    result: dict[str, Any] = Field(default_factory=dict)


class AssistantStreamEventPayloadContract(ContractModel):
    contract_version: Literal["3.0"] = Field(alias="contractVersion")
    event_id: str | None = Field(default=None, alias="eventId", min_length=1, max_length=128)
    assistant_turn_id: str = Field(alias="assistantTurnId")
    session_id: str = Field(alias="sessionId")
    event: Literal[
        "status",
        "token",
        "delta",
        "text_delta",
        "router_decision",
        "policy_decision",
        "approval_pending",
        "expert_start",
        "expert_end",
        "artifact_proposed",
        "artifact_committed",
        "artifact_patch_proposed",
        "artifact_patch_applied",
        "form_requested",
        "form_submitted",
        "tool_result",
        "audit_artifact",
        "final",
        "warning",
        "error",
        "cancelled",
    ]
    sequence: int = Field(ge=1)
    timestamp_utc: str = Field(alias="timestampUtc")
    trace_id: str | None = Field(default=None, alias="traceId", max_length=128)
    data_class: Literal["public", "internal", "confidential", "regulated"] | None = Field(
        default=None, alias="dataClass"
    )
    data: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_typed_event_data(self) -> AssistantStreamEventPayloadContract:
        v3_events = {
            "artifact_proposed",
            "artifact_committed",
            "artifact_patch_proposed",
            "artifact_patch_applied",
            "form_requested",
            "form_submitted",
            "tool_result",
        }
        if self.event not in v3_events:
            return self
        if self.event_id is None or self.trace_id is None or self.data_class is None:
            raise ValueError("v3 typed events require eventId, traceId, and dataClass")
        if self.event.startswith("artifact_"):
            parsed = AssistantArtifactEventDataContract.model_validate(self.data)
            if (
                self.event in {"artifact_committed", "artifact_patch_applied"}
                and parsed.revision_id is None
            ):
                raise ValueError("committed artifact events require revisionId")
            if self.event.startswith("artifact_patch_") and parsed.proposal_id is None:
                raise ValueError("artifact patch events require proposalId")
            if self.event == "artifact_patch_proposed" and (
                parsed.approval_id is None or parsed.action_hash is None
            ):
                raise ValueError(
                    "artifact patch proposal events require approvalId and actionHash"
                )
        elif self.event == "form_requested":
            AssistantFormRequestedDataContract.model_validate(self.data)
        elif self.event == "form_submitted":
            AssistantFormSubmittedDataContract.model_validate(self.data)
        else:
            AssistantToolResultDataContract.model_validate(self.data)
        return self


class ApprovalPendingPayloadContract(ContractModel):
    contract_version: Literal["3.0"]
    pending: list[ApprovalTicket] = Field(default_factory=list)


class ApprovalDetailPayloadContract(ContractModel):
    contract_version: Literal["3.0"]
    approval_id: str
    status: str
    execution_status: str
    ticket: ApprovalTicket


class RunSummaryItemContract(ContractModel):
    job_id: str
    case_id: str
    team_id: str
    status: str
    request: str
    created_at: str
    finished_at: str
    audit_envelope_path: str
    job_dir: str


class RunSummaryPayloadContract(ContractModel):
    contract_version: Literal["3.0"]
    status: str
    root_dir: str
    count: int
    items: list[RunSummaryItemContract] = Field(default_factory=list)
    errors: list[dict[str, str]] = Field(default_factory=list)


class TeamStatusArtifactContract(ContractModel):
    contract_version: Literal["3.0"]
    job: JobRun
    tasks: list[TaskRun] = Field(default_factory=list)
    audit_envelope_path: str | None = None
    job_dir: str | None = None
    resume_outcomes: list[dict[str, Any]] = Field(default_factory=list)
    continuation: dict[str, Any] = Field(default_factory=dict)
    computer_use: dict[str, Any] = Field(default_factory=dict)


class RunReplayPayloadContract(ContractModel):
    contract_version: Literal["3.0"]
    job_id: str
    status: str | None = None
    team_id: str | None = None
    case_id: str | None = None
    final_output: str | None = None
    event_count: int
    task_event_count: int
    handoff_event_count: int
    approval_event_count: int
    decision_count: int
    integrity: dict[str, Any] = Field(default_factory=dict)
    trace_refs: list[str] = Field(default_factory=list)
    approvals: list[dict[str, Any]] = Field(default_factory=list)
    tasks: list[dict[str, Any]] = Field(default_factory=list)
    handoffs: list[dict[str, Any]] = Field(default_factory=list)
    verified: bool | None = None
    errors: list[str] = Field(default_factory=list)
    checks: dict[str, Any] = Field(default_factory=dict)
    consistency: dict[str, Any] = Field(default_factory=dict)


class ReadArtifactPayloadContract(ContractModel):
    contract_version: Literal["3.0"] = Field(alias="contractVersion")
    artifact_name: str = Field(alias="artifactName")
    payload: dict[str, Any] = Field(default_factory=dict)
    truncated: bool
    bytes_read: int = Field(alias="bytesRead")


class TailEventsPayloadContract(ContractModel):
    contract_version: Literal["3.0"] = Field(alias="contractVersion")
    events: list[TeamEvent] = Field(default_factory=list)
    next_cursor: int = Field(alias="nextCursor")
    reset: bool
    truncated: bool
    bad_line_count: int = Field(alias="badLineCount")


class ConfigResolvePayloadContract(ContractModel):
    contract_version: Literal["3.0"]
    profile: str
    status: str
    resolved: dict[str, Any] = Field(default_factory=dict)
    source_map: dict[str, Any] = Field(default_factory=dict)


class AuthWhoAmIPayloadContract(ContractModel):
    contract_version: Literal["3.0"]
    identity_enabled: bool
    verified: bool
    actor: dict[str, Any] | None = None
    error_code: str | None = None
    error: str | None = None


class AuthCheckPayloadContract(ContractModel):
    contract_version: Literal["3.0"]
    permission: str
    allowed: bool
    actor: dict[str, Any] | None = None
    error_code: str | None = None
    error: str | None = None


class SecurityBaselinePayloadContract(ContractModel):
    contract_version: Literal["3.0"]
    profile: str
    overall_status: str
    checks: dict[str, Any] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    roots: dict[str, str] = Field(default_factory=dict)
    key_status: dict[str, Any] = Field(default_factory=dict)
    misconfiguration_risks: list[str] = Field(default_factory=list)


class KeyStatusPayloadContract(ContractModel):
    contract_version: Literal["3.0"]
    provider: str
    current_key_id: str | None = None
    private_key_path: str
    private_key_present: bool
    trusted_keys_dir: str
    trusted_key_count: int
    trusted_keys: list[str] = Field(default_factory=list)
    key_manifest_path: str
    key_manifest_present: bool
    compat_env_hmac_enabled: bool
    enterprise_compatible: bool
    pkcs11_status: str


class SupportBundleExportPayloadContract(ContractModel):
    contract_version: Literal["3.0"]
    bundle_dir: str
    archive_path: str
    manifest_path: str
    file_count: int


class DeviceActionApprovalSnapshotContract(ContractModel):
    kind: Literal["device_action"]
    target_kind: Literal["device_action"]
    action_hash: str
    policy_hash: str
    action_id: str
    category: str
    risk_class: str
    target_ref: str
    window_or_tab_identity: str
    window_identity: str
    app_identity: str
    selector_source: str
    selector_context: dict[str, Any] = Field(default_factory=dict)
    perception_fingerprint: str
    action_plan: dict[str, Any] = Field(default_factory=dict)
    execution_contract: dict[str, Any] = Field(default_factory=dict)


class PreviewFixtureOperationsContract(ContractModel):
    identity: AuthWhoAmIPayloadContract
    permission_check: AuthCheckPayloadContract = Field(alias="permissionCheck")
    security: SecurityBaselinePayloadContract
    keys: KeyStatusPayloadContract
    support: SupportBundleExportPayloadContract
    metrics: dict[str, Any] = Field(default_factory=dict)
    ga_readiness: dict[str, Any] = Field(default_factory=dict, alias="gaReadiness")
    qualification: dict[str, Any] = Field(default_factory=dict)
    backup_create: dict[str, Any] = Field(default_factory=dict, alias="backupCreate")
    backup_verify: dict[str, Any] = Field(default_factory=dict, alias="backupVerify")
    restore_verify: dict[str, Any] = Field(default_factory=dict, alias="restoreVerify")
    migrate_plan: dict[str, Any] = Field(default_factory=dict, alias="migratePlan")
    migrate_apply_dry_run: dict[str, Any] = Field(
        default_factory=dict,
        alias="migrateApplyDryRun",
    )


class PreviewFixtureArtifactsContract(ContractModel):
    status: TeamStatusArtifactContract
    tasks: dict[str, Any] = Field(default_factory=dict)
    handoffs: dict[str, Any] = Field(default_factory=dict)
    audit_envelope: dict[str, Any] = Field(default_factory=dict, alias="auditEnvelope")


class PreviewFixtureAssistantContract(ContractModel):
    start_turn: AssistantStartTurnPayloadContract = Field(alias="startTurn")
    events: list[AssistantStreamEventPayloadContract] = Field(default_factory=list)


class PreviewFixtureBundleContract(ContractModel):
    contract_version: Literal["3.0"] = Field(alias="contractVersion")
    assistant: PreviewFixtureAssistantContract | None = None
    handshake: BridgeHandshakeContract
    submit_team_run: SpawnedRunPayloadContract = Field(alias="submitTeamRun")
    approval_pending: ApprovalPendingPayloadContract = Field(alias="approvalPending")
    approval_detail: ApprovalDetailPayloadContract = Field(alias="approvalDetail")
    run_summary: RunSummaryPayloadContract = Field(alias="runSummary")
    run_detail: TeamStatusArtifactContract = Field(alias="runDetail")
    run_replay: RunReplayPayloadContract = Field(alias="runReplay")
    read_artifact: PreviewFixtureArtifactsContract = Field(alias="readArtifact")
    tail_events: TailEventsPayloadContract = Field(alias="tailEvents")
    config_resolve: ConfigResolvePayloadContract = Field(alias="configResolve")
    operations: PreviewFixtureOperationsContract
    device_action_snapshot: DeviceActionApprovalSnapshotContract = Field(
        alias="deviceActionSnapshot"
    )
