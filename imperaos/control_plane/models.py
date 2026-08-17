from __future__ import annotations

import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from imperaos.control_plane.enterprise_workspace import EnterpriseWorkspaceSnapshot
from imperaos.control_plane.pilot_workflow_models import GovernedPilotWorkflowSnapshot
from imperaos.memory.models import MemoryAuthoritySnapshot, disabled_memory_authority_snapshot
from imperaos.memory.runtime_policy_snapshot import MemoryPolicyEnforcementSnapshot
from imperaos.memory.runtime_snapshot import MemoryRuntimeSnapshot, MemorySyncSnapshot
from imperaos.memory.semantic import MemorySemanticIndexSnapshot
from imperaos.memory.workspace_models import WorkspaceMemoryAuthorityHealth
from imperaos.release.gate_models import RcGateEvidenceSnapshot
from imperaos.release_decision.models import RcReleaseDecisionSnapshot


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        use_enum_values=True,
    )


class RuntimeKind(StrEnum):
    IMPERAOS_CORE = "imperaos_core"
    IMPERAOS_TEAM = "imperaos_team"
    EXTERNAL_STDIO = "external_stdio"
    EXTERNAL_HTTP = "external_http"
    COMPUTER_USE_ADAPTER = "computer_use_adapter"


class ExecutionSurface(StrEnum):
    CORE_RUNTIME = "core_runtime"
    TEAM_RUNTIME = "team_runtime"
    EXTERNAL_STDIO = "external_stdio"
    COMPUTER_USE_LIVE = "computer_use_live"
    OPERATOR_PANEL = "operator_panel"


class RiskClass(StrEnum):
    READ_ONLY = "read_only"
    LOCAL_WRITE = "local_write"
    EXTERNAL_WRITE = "external_write"
    MUTATION = "mutation"
    DESTRUCTIVE = "destructive"
    CREDENTIAL_SENSITIVE = "credential_sensitive"
    FINANCIAL_OR_LEGAL = "financial_or_legal"
    SECURITY_SENSITIVE = "security_sensitive"
    COMPUTER_USE_VISUAL = "computer_use_visual"
    UNKNOWN = "unknown"


class ControlPlaneDecisionAction(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"
    UNKNOWN = "unknown"


class AgentStatus(StrEnum):
    REGISTERED = "registered"
    DISABLED = "disabled"
    BLOCKED = "blocked"


class AgentReadiness(StrEnum):
    NOT_EVALUATED = "not_evaluated"
    POLICY_SIMULATED = "policy_simulated"
    QUALIFIED = "qualified"
    PRODUCTION_ALLOWED = "production_allowed"
    BLOCKED = "blocked"


class RunStatus(StrEnum):
    CREATED = "created"
    POLICY_EVALUATING = "policy_evaluating"
    POLICY_BLOCKED = "policy_blocked"
    APPROVAL_PENDING = "approval_pending"
    APPROVAL_REJECTED = "approval_rejected"
    APPROVED = "approved"
    EXECUTING = "executing"
    BLOCKED = "blocked"
    FAILED = "failed"
    COMPLETED = "completed"
    EVIDENCE_EXPORTED = "evidence_exported"
    VERIFIED = "verified"


class ClaimStatus(StrEnum):
    ALLOWED = "allowed"
    CONDITIONAL = "conditional"
    BLOCKED = "blocked"
    DEFERRED = "deferred"


class AgentOwner(StrictModel):
    team: str
    contact: str


class AgentQualification(StrictModel):
    required: bool = True
    minimum_level: Literal["development", "pilot", "enterprise", "ga"] = "pilot"
    status: Literal["missing", "development", "pilot", "enterprise", "ga"] = "missing"


class AgentEvidenceRequirements(StrictModel):
    signed_pack_required: bool = True
    replay_required: bool = True


class DeclaredAction(StrictModel):
    action_id: str
    phase: Literal["task", "tool", "handoff", "memory_write", "device_action"] = "tool"
    risk_class: RiskClass
    target_kind: str
    effect: str
    action_type: str = "control_plane_action"

    @field_validator("action_id")
    @classmethod
    def _action_id_valid(cls, value: str) -> str:
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,127}", value):
            raise ValueError("action_id must be stable lowercase snake/kebab text")
        return value


class AgentSpec(StrictModel):
    version: Literal["control-plane.agent/v1"]
    agent_id: str
    display_name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    runtime_kind: RuntimeKind
    profile: str = "enterprise"
    policy_profile: str | None = None
    owner: AgentOwner
    allowed_surfaces: list[ExecutionSurface] = Field(default_factory=list)
    blocked_surfaces: list[ExecutionSurface] = Field(default_factory=list)
    declared_actions: list[DeclaredAction] = Field(default_factory=list)
    qualification: AgentQualification = Field(default_factory=AgentQualification)
    evidence: AgentEvidenceRequirements = Field(default_factory=AgentEvidenceRequirements)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("agent_id")
    @classmethod
    def _agent_id_valid(cls, value: str) -> str:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,62}[a-z0-9]", value):
            raise ValueError("agent_id must be kebab-case and 3-64 chars")
        return value

    @model_validator(mode="after")
    def _set_policy_and_validate_surfaces(self) -> AgentSpec:
        if self.policy_profile is None:
            self.policy_profile = self.profile
        overlap = set(self.allowed_surfaces) & set(self.blocked_surfaces)
        if overlap:
            values = ", ".join(sorted(str(item) for item in overlap))
            raise ValueError(f"allowed_surfaces and blocked_surfaces overlap: {values}")
        return self


class AgentRecord(StrictModel):
    version: Literal["control-plane.agent-record/v1"] = "control-plane.agent-record/v1"
    agent_id: str
    spec_hash: str
    status: AgentStatus = AgentStatus.REGISTERED
    readiness: AgentReadiness = AgentReadiness.NOT_EVALUATED
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    disabled_reason: str | None = None
    last_run_id: str | None = None
    last_evidence_pack_id: str | None = None
    spec: AgentSpec


class AgentRegisterResult(StrictModel):
    status: Literal["registered", "unchanged"]
    agent_id: str
    spec_hash: str
    record_path: str
    record: AgentRecord


class ActionProposal(StrictModel):
    version: Literal["control-plane.action-proposal/v1"]
    correlation_id: str
    run_id: str
    agent_id: str
    phase: Literal["task", "tool", "handoff", "memory_write", "device_action"] = "tool"
    action_id: str
    action_type: str = "control_plane_action"
    target_kind: str
    target_ref: str = ""
    risk_class: RiskClass = RiskClass.UNKNOWN
    effect_summary: str
    args_fingerprint: str = "sha256:unknown"
    idempotency_key: str
    payload_redacted: bool = True
    requested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ControlPlanePolicyDecision(StrictModel):
    action_id: str
    phase: str
    risk_class: RiskClass
    decision_action: ControlPlaneDecisionAction
    reason_code: str
    matched_rule_path: str
    policy_hash: str
    approval_id: str | None = None
    qualification_required: bool = False


class PolicySimulationSummary(StrictModel):
    allow: int = 0
    require_approval: int = 0
    deny: int = 0
    unknown: int = 0


class PolicySimulationResult(StrictModel):
    version: Literal["control-plane.policy-simulation/v1"] = (
        "control-plane.policy-simulation/v1"
    )
    agent_id: str
    policy_hash: str
    overall_status: Literal["pass", "conditional", "blocked"]
    summary: PolicySimulationSummary
    decisions: list[ControlPlanePolicyDecision] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list)


class ControlPlaneRunSummary(StrictModel):
    version: Literal["control-plane.run/v1"] = "control-plane.run/v1"
    run_id: str
    agent_id: str
    profile: str
    status: RunStatus
    submitted_by: str
    identity_ref: str | None = None
    input_hash: str
    policy_hash: str
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    approval_ids: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    evidence_pack_id: str | None = None
    blocking_reasons: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)


class EvidencePackItem(StrictModel):
    kind: str
    path: str
    sha256: str
    required: bool = True


class RedactionSummary(StrictModel):
    raw_screenshots_persisted: int = 0
    secrets_redacted: bool = True
    pii_redaction_enabled: bool = True


class EvidenceVerificationSummary(StrictModel):
    hash_chain_verified: bool = False
    signature_verified: bool = False
    replay_verified: bool = False


class EvidenceSignatureSummary(StrictModel):
    mode: str = "unsigned"
    key_id: str | None = None
    algorithm: str = "ed25519"
    signature_ref: str | None = None


class EvidencePackManifest(StrictModel):
    version: Literal["control-plane.evidence-pack/v1"] = "control-plane.evidence-pack/v1"
    pack_id: str
    run_id: str
    agent_id: str
    profile: str
    runtime_version: str
    git_commit: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    items: list[EvidencePackItem] = Field(default_factory=list)
    redaction_summary: RedactionSummary = Field(default_factory=RedactionSummary)
    verification: EvidenceVerificationSummary = Field(
        default_factory=EvidenceVerificationSummary
    )
    signature: EvidenceSignatureSummary = Field(default_factory=EvidenceSignatureSummary)
    warnings: list[str] = Field(default_factory=list)


class EvidenceVerifyResult(StrictModel):
    status: Literal["pass", "fail"]
    hash_chain_verified: bool
    signature_verified: bool
    required_items_present: bool
    replay_verified: bool
    blocking_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class EvidenceVerificationHistoryItem(StrictModel):
    history_id: str = Field(alias="historyId")
    evidence_id: str = Field(alias="evidenceId")
    status: Literal["pass", "fail"]
    verified_at_utc: datetime = Field(alias="verifiedAtUtc")
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")
    warnings: list[str] = Field(default_factory=list)


class EvidenceIndexEntry(StrictModel):
    evidence_id: str = Field(alias="evidenceId")
    run_id: str = Field(alias="runId")
    agent_id: str | None = Field(default=None, alias="agentId")
    path: str
    manifest_hash: str = Field(alias="manifestHash")
    signature_status: Literal["valid", "invalid", "missing", "unknown"] = Field(
        alias="signatureStatus"
    )
    replay_status: Literal["verified", "failed", "not_available", "unknown"] = Field(
        alias="replayStatus"
    )
    verified_at_utc: datetime | None = Field(default=None, alias="verifiedAtUtc")
    claim_status: Literal["ready", "conditional", "blocked"] = Field(alias="claimStatus")
    redaction_status: Literal["clean", "warning", "failed", "unknown"] = Field(
        alias="redactionStatus"
    )
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")


class EvidenceIndexSnapshot(StrictModel):
    version: Literal["control-plane.evidence-index/v1"] = "control-plane.evidence-index/v1"
    generated_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        alias="generatedAtUtc",
    )
    status: Literal["pass", "conditional", "blocked"]
    entries: list[EvidenceIndexEntry] = Field(default_factory=list)
    verification_history: list[EvidenceVerificationHistoryItem] = Field(
        default_factory=list,
        alias="verificationHistory",
    )
    warnings: list[str] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")


class ClaimItem(StrictModel):
    claim_id: str
    status: ClaimStatus
    required_evidence: list[str] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list)


class ClaimMatrix(StrictModel):
    version: Literal["control-plane.claim-matrix/v1"] = "control-plane.claim-matrix/v1"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    claims: list[ClaimItem] = Field(default_factory=list)


class ReadinessReport(StrictModel):
    version: Literal["control-plane.readiness/v1"] = "control-plane.readiness/v1"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    profile: str
    status: Literal["pass", "conditional", "blocked"]
    checks: dict[str, bool] = Field(default_factory=dict)
    blocking_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class DataSourceState(StrictModel):
    mode: Literal["preview_fixture", "tauri_live", "cli_live", "stale_cache", "error"]
    is_mock: bool = Field(alias="isMock")
    is_silent_fallback: bool = Field(alias="isSilentFallback")
    last_refresh_utc: datetime | None = Field(default=None, alias="lastRefreshUtc")
    age_ms: int | None = Field(default=None, alias="ageMs")
    freshness: Literal["fresh", "stale", "unknown"]
    contract_version: str = Field(alias="contractVersion")
    source_reason: str | None = Field(default=None, alias="sourceReason")


class SystemHealthState(StrictModel):
    status: Literal["healthy", "partial", "degraded", "blocked", "unknown"]
    confidence: Literal["high", "medium", "low"]
    missing_signals: list[str] = Field(default_factory=list, alias="missingSignals")
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")
    last_doctor_status: str = Field(alias="lastDoctorStatus")
    human_summary: str = Field(alias="humanSummary")


class SystemSummary(StrictModel):
    profile: str
    root_dir: str = Field(alias="rootDir")
    core_version: str = Field(alias="coreVersion")
    contract_version: str = Field(alias="contractVersion")
    health: SystemHealthState
    doctor: dict[str, Any] = Field(default_factory=dict)
    capabilities: dict[str, Any] = Field(default_factory=dict)
    config_summary: dict[str, Any] = Field(default_factory=dict, alias="configSummary")
    source_map: dict[str, str] = Field(default_factory=dict, alias="sourceMap")
    warnings: list[str] = Field(default_factory=list)


class DashboardSummary(StrictModel):
    agent_count: int = Field(alias="agentCount")
    run_count: int = Field(alias="runCount")
    pending_approval_count: int = Field(alias="pendingApprovalCount")
    evidence_pack_count: int = Field(alias="evidencePackCount")
    active_alert_count: int = Field(alias="activeAlertCount")
    blocked_claim_count: int = Field(alias="blockedClaimCount")
    conditional_claim_count: int = Field(alias="conditionalClaimCount")


class AgentSummary(StrictModel):
    agent_id: str = Field(alias="agentId")
    display_name: str = Field(alias="displayName")
    runtime_kind: str = Field(alias="runtimeKind")
    agent_type: Literal[
        "internal",
        "external_stdio",
        "external_http",
        "computer_use_adapter",
    ] = Field(default="internal", alias="agentType")
    status: str
    readiness: str
    owner_team: str | None = Field(default=None, alias="ownerTeam")
    policy_pack_id: str | None = Field(default=None, alias="policyPackId")
    risk_profile: Literal["read_only", "guarded", "restricted", "blocked"] = Field(
        default="guarded",
        alias="riskProfile",
    )
    last_run_id: str | None = Field(default=None, alias="lastRunId")
    last_evidence_pack_id: str | None = Field(default=None, alias="lastEvidencePackId")
    last_evidence_status: Literal["missing", "pending", "valid", "invalid"] = Field(
        default="missing",
        alias="lastEvidenceStatus",
    )


class AgentRegistryV2Item(StrictModel):
    agent_id: str = Field(alias="agentId")
    display_name: str = Field(alias="displayName")
    runtime_kind: str = Field(alias="runtimeKind")
    agent_type: Literal[
        "internal",
        "external_stdio",
        "external_http",
        "computer_use_adapter",
    ] = Field(alias="agentType")
    owner_team: str | None = Field(default=None, alias="ownerTeam")
    owner_contact: str | None = Field(default=None, alias="ownerContact")
    policy_pack_id: str = Field(alias="policyPackId")
    risk_profile: Literal["read_only", "guarded", "restricted", "blocked"] = Field(
        alias="riskProfile"
    )
    adapter_contract_version: str | None = Field(
        default=None,
        alias="adapterContractVersion",
    )
    enabled: bool
    status: str
    readiness: str
    last_run_id: str | None = Field(default=None, alias="lastRunId")
    last_evidence_pack_id: str | None = Field(default=None, alias="lastEvidencePackId")
    last_evidence_status: Literal["missing", "pending", "valid", "invalid"] = Field(
        alias="lastEvidenceStatus"
    )
    workspace_id: str | None = Field(default=None, alias="workspaceId")
    principal_id: str | None = Field(default=None, alias="principalId")
    device_id: str | None = Field(default=None, alias="deviceId")
    enrollment_id: str | None = Field(default=None, alias="enrollmentId")
    enrollment_status: str | None = Field(default=None, alias="enrollmentStatus")
    workspace_binding_status: Literal["unbound", "bound", "blocked"] = Field(
        default="unbound",
        alias="workspaceBindingStatus",
    )
    updated_at: datetime = Field(alias="updatedAt")


class AgentRegistryV2Snapshot(StrictModel):
    version: Literal["control-plane.agent-registry/v2"] = "control-plane.agent-registry/v2"
    generated_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        alias="generatedAtUtc",
    )
    agents: list[AgentRegistryV2Item] = Field(default_factory=list)


class RunSnapshotSummary(StrictModel):
    run_id: str = Field(alias="runId")
    agent_id: str = Field(alias="agentId")
    profile: str
    status: str
    submitted_by: str = Field(alias="submittedBy")
    identity_ref: str | None = Field(default=None, alias="identityRef")
    input_hash: str = Field(alias="inputHash")
    policy_hash: str = Field(alias="policyHash")
    started_at: datetime = Field(alias="startedAt")
    completed_at: datetime | None = Field(default=None, alias="completedAt")
    approval_ids: list[str] = Field(default_factory=list, alias="approvalIds")
    artifact_refs: list[str] = Field(default_factory=list, alias="artifactRefs")
    evidence_pack_id: str | None = Field(default=None, alias="evidencePackId")
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")
    next_actions: list[str] = Field(default_factory=list, alias="nextActions")


class ApprovalSnapshotSummary(StrictModel):
    approval_id: str = Field(alias="approvalId")
    run_id: str = Field(alias="runId")
    status: str
    target_kind: str = Field(alias="targetKind")
    target_ref: str = Field(alias="targetRef")
    action_hash: str = Field(alias="actionHash")
    policy_hash: str = Field(alias="policyHash")
    request_hash: str = Field(alias="requestHash")
    snapshot_hash: str = Field(alias="snapshotHash")
    execution_status: str = Field(alias="executionStatus")
    created_at: datetime = Field(alias="createdAt")
    expires_at: datetime = Field(alias="expiresAt")
    actor: str | None = None
    disabled_reason: str | None = Field(default=None, alias="disabledReason")


class EvidencePackSummary(StrictModel):
    pack_id: str = Field(alias="packId")
    run_id: str | None = Field(default=None, alias="runId")
    created_at_utc: datetime | None = Field(default=None, alias="createdAtUtc")
    signature_status: Literal["missing", "pending", "valid", "invalid"] = Field(
        alias="signatureStatus"
    )
    hash_chain_status: Literal["pending", "valid", "broken"] = Field(alias="hashChainStatus")
    replay_status: Literal["not_available", "pending", "passed", "failed"] = Field(
        alias="replayStatus"
    )
    claim_guard_status: Literal["ready", "conditional", "blocked"] = Field(
        alias="claimGuardStatus"
    )
    redaction_status: Literal["passed", "warning", "failed", "unknown"] = Field(
        alias="redactionStatus"
    )
    artifact_count: int = Field(alias="artifactCount")
    export_path: str | None = Field(default=None, alias="exportPath")
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")


class PolicyPackSummary(StrictModel):
    pack_id: str = Field(alias="packId")
    label: str
    version: str
    status: Literal["active", "available", "missing", "blocked"]
    policy_hash: str | None = Field(default=None, alias="policyHash")
    rule_count: int = Field(default=0, alias="ruleCount")
    source_path: str | None = Field(default=None, alias="sourcePath")
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")


class PolicyPackRule(StrictModel):
    rule_id: str = Field(alias="ruleId")
    category: Literal["task", "tool", "handoff", "memory", "action", "claim"]
    action: Literal["allow", "require_approval", "deny"]
    risk_class: RiskClass | None = Field(default=None, alias="riskClass")
    target_kind: str | None = Field(default=None, alias="targetKind")
    explain: str | None = None


class PolicyPackManifest(StrictModel):
    schema_version: Literal["control-plane.policy-pack/v1"] = Field(
        default="control-plane.policy-pack/v1",
        alias="schemaVersion",
    )
    policy_pack_id: str = Field(alias="policyPackId")
    version: str
    status: Literal["draft", "staged", "active", "retired"] = "draft"
    default_decision: Literal["allow", "require_approval", "deny"] = Field(
        default="deny",
        alias="defaultDecision",
    )
    rules: list[PolicyPackRule] = Field(default_factory=list)
    created_by: str = Field(alias="createdBy")
    signed_manifest_ref: str | None = Field(default=None, alias="signedManifestRef")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC), alias="createdAt")


class PolicyPackValidationResult(StrictModel):
    version: Literal["control-plane.policy-pack-validation/v1"] = (
        "control-plane.policy-pack-validation/v1"
    )
    policy_pack_id: str = Field(alias="policyPackId")
    policy_version: str = Field(alias="policyVersion")
    status: Literal["pass", "conditional", "blocked"]
    rule_count: int = Field(alias="ruleCount")
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")
    warnings: list[str] = Field(default_factory=list)


class PolicyPackDiffResult(StrictModel):
    version: Literal["control-plane.policy-pack-diff/v1"] = "control-plane.policy-pack-diff/v1"
    base_policy_pack_id: str = Field(alias="basePolicyPackId")
    candidate_policy_pack_id: str = Field(alias="candidatePolicyPackId")
    added_rules: list[str] = Field(default_factory=list, alias="addedRules")
    removed_rules: list[str] = Field(default_factory=list, alias="removedRules")
    changed_rules: list[str] = Field(default_factory=list, alias="changedRules")
    risk_changes: list[str] = Field(default_factory=list, alias="riskChanges")
    status: Literal["pass", "conditional", "blocked"]
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")
    warnings: list[str] = Field(default_factory=list)


class PolicyPackPromotionDryRun(StrictModel):
    version: Literal["control-plane.policy-pack-promotion/v1"] = (
        "control-plane.policy-pack-promotion/v1"
    )
    policy_pack_id: str = Field(alias="policyPackId")
    policy_version: str = Field(alias="policyVersion")
    dry_run: bool = Field(alias="dryRun")
    status: Literal["pass", "conditional", "blocked"]
    would_promote: bool = Field(alias="wouldPromote")
    activation_audit_ref: str | None = Field(default=None, alias="activationAuditRef")
    validation: PolicyPackValidationResult
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")
    warnings: list[str] = Field(default_factory=list)


class ExecutionSurfaceSummary(StrictModel):
    surface_id: str = Field(alias="surfaceId")
    label: str
    status: Literal["ready", "conditional", "blocked", "not_applicable"]
    claim_id: str | None = Field(default=None, alias="claimId")
    reason_codes: list[str] = Field(default_factory=list, alias="reasonCodes")
    human_summary: str = Field(alias="humanSummary")


class LogEventSummary(StrictModel):
    event_id: str = Field(alias="eventId")
    timestamp: datetime = Field(alias="timestamp")
    severity: Literal["info", "warning", "error", "critical"]
    source: str
    message: str
    run_id: str | None = Field(default=None, alias="runId")
    evidence_pack_id: str | None = Field(default=None, alias="evidencePackId")


class AlertSummary(StrictModel):
    alert_id: str = Field(alias="alertId")
    severity: Literal["info", "warning", "error", "critical"]
    status: Literal["active", "resolved"]
    title: str
    reason_code: str = Field(alias="reasonCode")
    recommended_action: str = Field(alias="recommendedAction")
    linked_run_id: str | None = Field(default=None, alias="linkedRunId")
    linked_evidence_pack_id: str | None = Field(default=None, alias="linkedEvidencePackId")


class ReportSummary(StrictModel):
    report_id: str = Field(alias="reportId")
    kind: Literal["readiness", "evidence", "qualification", "support", "security", "metrics"]
    title: str
    status: Literal["ready", "conditional", "blocked", "missing"]
    path: str | None = None
    generated_at_utc: datetime | None = Field(default=None, alias="generatedAtUtc")
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")


class ReportManifestItem(StrictModel):
    report_id: str = Field(alias="reportId")
    kind: Literal[
        "readiness",
        "evidence",
        "qualification",
        "support",
        "security",
        "metrics",
        "policy",
        "alerts",
        "logs",
    ]
    title: str
    status: Literal["ready", "conditional", "blocked", "missing"]
    path: str
    generated_at_utc: datetime = Field(alias="generatedAtUtc")
    summary: str


class AlertEvaluation(StrictModel):
    alert_id: str = Field(alias="alertId")
    severity: Literal["info", "warning", "critical"]
    state: Literal["active", "resolved", "suppressed"]
    source: Literal["snapshot", "evidence", "policy", "approval", "runtime", "ci"]
    reason_code: str = Field(alias="reasonCode")
    suggested_action: str = Field(alias="suggestedAction")
    first_seen_at: datetime = Field(alias="firstSeenAt")
    last_seen_at: datetime = Field(alias="lastSeenAt")


class ReportManifest(StrictModel):
    version: Literal["control-plane.report-manifest/v1"] = (
        "control-plane.report-manifest/v1"
    )
    generated_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        alias="generatedAtUtc",
    )
    status: Literal["pass", "conditional", "blocked"]
    reports: list[ReportManifestItem] = Field(default_factory=list)
    alerts: list[AlertEvaluation] = Field(default_factory=list)
    logs_export_ref: str | None = Field(default=None, alias="logsExportRef")
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")
    warnings: list[str] = Field(default_factory=list)


class OperationResultSummary(StrictModel):
    status: Literal["not_run", "passed", "failed", "blocked"]
    summary: str
    generated_at_utc: datetime | None = Field(default=None, alias="generatedAtUtc")
    error_code: str | None = Field(default=None, alias="errorCode")


class OperationDescriptor(StrictModel):
    operation_id: str = Field(alias="operationId")
    category: Literal[
        "identity",
        "qualification",
        "security",
        "keys",
        "support",
        "backup",
        "restore",
        "migration",
    ]
    label: str
    description: str
    risk_level: Literal["read_only", "low", "medium", "high", "destructive"] = Field(
        alias="riskLevel"
    )
    permission: str
    supports_dry_run: bool = Field(alias="supportsDryRun")
    enabled: bool
    disabled_reason: str | None = Field(default=None, alias="disabledReason")
    last_result: OperationResultSummary | None = Field(default=None, alias="lastResult")


class OperationWorkflowRequest(StrictModel):
    version: Literal["control-plane.operation-workflow-request/v1"] = (
        "control-plane.operation-workflow-request/v1"
    )
    operation_id: str = Field(alias="operationId")
    actor_id: str = Field(alias="actorId")
    dry_run: bool = Field(default=True, alias="dryRun")
    requested_at: datetime = Field(default_factory=lambda: datetime.now(UTC), alias="requestedAt")


class OperationWorkflowResult(StrictModel):
    version: Literal["control-plane.operation-workflow-result/v1"] = (
        "control-plane.operation-workflow-result/v1"
    )
    operation_id: str = Field(alias="operationId")
    actor_id: str = Field(alias="actorId")
    status: Literal["passed", "blocked", "requires_approval"]
    dry_run: bool = Field(alias="dryRun")
    permission: str
    risk_level: Literal["read_only", "low", "medium", "high", "destructive"] = Field(
        alias="riskLevel"
    )
    reason_code: str = Field(alias="reasonCode")
    next_actions: list[str] = Field(default_factory=list, alias="nextActions")
    generated_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        alias="generatedAtUtc",
    )


class UserSummary(StrictModel):
    user_id: str = Field(alias="userId")
    subject: str
    issuer: str | None = None
    status: Literal["active", "expired", "unknown"]
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    last_seen_utc: datetime | None = Field(default=None, alias="lastSeenUtc")


class RoleSummary(StrictModel):
    role_id: str = Field(alias="roleId")
    label: str
    risk_level: Literal["low", "medium", "high"] = Field(alias="riskLevel")
    permissions: list[str] = Field(default_factory=list)
    assignment_count: int = Field(default=0, alias="assignmentCount")


class RbacBinding(StrictModel):
    actor_id: str = Field(alias="actorId")
    role_id: str = Field(alias="roleId")
    source: Literal["local_fixture", "identity_assertion", "external_idp_placeholder"]


class RbacMatrixSnapshot(StrictModel):
    version: Literal["control-plane.rbac-matrix/v1"] = "control-plane.rbac-matrix/v1"
    generated_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        alias="generatedAtUtc",
    )
    users: list[UserSummary] = Field(default_factory=list)
    roles: list[RoleSummary] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    bindings: list[RbacBinding] = Field(default_factory=list)
    effective_permissions: dict[str, list[str]] = Field(
        default_factory=dict,
        alias="effectivePermissions",
    )
    source: Literal["local_fixture", "identity_assertion", "external_idp_placeholder"]


class RbacPermissionDecision(StrictModel):
    version: Literal["control-plane.rbac-decision/v1"] = "control-plane.rbac-decision/v1"
    actor_id: str = Field(alias="actorId")
    permission: str
    status: Literal["allowed", "denied"]
    dry_run: bool = Field(default=True, alias="dryRun")
    reason_code: str = Field(alias="reasonCode")
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    generated_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        alias="generatedAtUtc",
    )


class AdminSummary(StrictModel):
    users: list[UserSummary] = Field(default_factory=list)
    roles: list[RoleSummary] = Field(default_factory=list)
    policy_packs: list[PolicyPackSummary] = Field(default_factory=list, alias="policyPacks")
    permission_matrix: dict[str, list[str]] = Field(default_factory=dict, alias="permissionMatrix")
    source: Literal["local_fixture", "identity_assertion", "external_idp_placeholder"]


class QuickActionSummary(StrictModel):
    action_id: str = Field(alias="actionId")
    label: str
    enabled: bool
    disabled_reason: str | None = Field(default=None, alias="disabledReason")


class DesignPartnerRcCheck(StrictModel):
    check_id: str = Field(alias="checkId")
    label: str
    status: Literal["passed", "conditional", "failed"]
    detail: str
    blocking: bool = False


class DesignPartnerRcStatus(StrictModel):
    schema_version: Literal["control-plane.design-partner-rc/v1"] = Field(
        default="control-plane.design-partner-rc/v1",
        alias="schemaVersion",
    )
    generated_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        alias="generatedAtUtc",
    )
    status: Literal["ready", "conditional", "blocked"] = "conditional"
    checks: list[DesignPartnerRcCheck] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    artifact_root: str = Field(default="artifacts/design-partner-rc", alias="artifactRoot")


class PilotLaunchStatusTile(StrictModel):
    tile_id: str = Field(alias="tileId")
    label: str
    status: Literal["ready", "conditional", "blocked", "missing"]
    detail: str
    path: str | None = None
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")


class PilotLaunchNextAction(StrictModel):
    label: str
    severity: Literal["info", "warning", "blocking"]
    target: str


class PilotLaunchAdminProposalSummary(StrictModel):
    proposal_id: str = Field(alias="proposalId")
    kind: str
    operation: str
    status: str
    permission_required: str = Field(alias="permissionRequired")
    approval_id: str | None = Field(default=None, alias="approvalId")
    audit_envelope_path: str | None = Field(default=None, alias="auditEnvelopePath")


class PilotLaunchReadinessStatus(StrictModel):
    schema_version: Literal["control-plane.pilot-launch-readiness/v1"] = Field(
        default="control-plane.pilot-launch-readiness/v1",
        alias="schemaVersion",
    )
    generated_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        alias="generatedAtUtc",
    )
    status: Literal["ready", "conditional", "blocked"] = "conditional"
    headline: str
    artifact_root: str = Field(alias="artifactRoot")
    enterprise_hat_a: PilotLaunchStatusTile = Field(alias="enterpriseHatA")
    install_rehearsal: PilotLaunchStatusTile = Field(alias="installRehearsal")
    external_agent_pilot: PilotLaunchStatusTile = Field(alias="externalAgentPilot")
    governance_admin: PilotLaunchStatusTile = Field(alias="governanceAdmin")
    security_review: PilotLaunchStatusTile = Field(alias="securityReview")
    claim_guard: PilotLaunchStatusTile = Field(alias="claimGuard")
    evidence_corpus: PilotLaunchStatusTile = Field(alias="evidenceCorpus")
    pilot_metrics: PilotLaunchStatusTile = Field(alias="pilotMetrics")
    admin_proposals: list[PilotLaunchAdminProposalSummary] = Field(
        default_factory=list,
        alias="adminProposals",
    )
    next_actions: list[PilotLaunchNextAction] = Field(default_factory=list, alias="nextActions")
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class CodeIntelligenceFindingBucket(StrictModel):
    bucket_id: str = Field(alias="bucketId")
    label: str
    status: Literal["ready", "warn", "blocked", "missing"]
    count: int = 0
    errors: int = 0
    warnings: int = 0
    path: str | None = None
    detail: str = ""


class CodeIntelligenceSummary(StrictModel):
    schema_version: Literal["control-plane.code-intelligence-summary/v1"] = Field(
        default="control-plane.code-intelligence-summary/v1",
        alias="schemaVersion",
    )
    generated_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        alias="generatedAtUtc",
    )
    status: Literal["ready", "conditional", "blocked", "missing"] = "missing"
    verdict: str = "missing"
    tool: str = "fallow"
    tool_version: str | None = Field(default=None, alias="toolVersion")
    artifact_root: str = Field(default="artifacts/code-intelligence/fallow", alias="artifactRoot")
    telemetry_disabled: bool = Field(default=True, alias="telemetryDisabled")
    boundary_violations: int = Field(default=0, alias="boundaryViolations")
    secret_scan_status: str = Field(default="unknown", alias="secretScanStatus")
    buckets: list[CodeIntelligenceFindingBucket] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class PilotOperationsChecklistItem(StrictModel):
    item_id: str = Field(alias="itemId")
    label: str
    status: Literal["ready", "conditional", "blocked", "missing"]
    detail: str
    path: str | None = None
    blocking: bool = False


class PilotOperationsTimelineEvent(StrictModel):
    event_id: str = Field(alias="eventId")
    label: str
    status: Literal["completed", "pending", "blocked", "warning"]
    detail: str
    artifact_ref: str | None = Field(default=None, alias="artifactRef")
    occurred_at_utc: datetime | None = Field(default=None, alias="occurredAtUtc")


class PilotOperationsStatus(StrictModel):
    schema_version: Literal["control-plane.pilot-operations/v1"] = Field(
        default="control-plane.pilot-operations/v1",
        alias="schemaVersion",
    )
    generated_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        alias="generatedAtUtc",
    )
    status: Literal["ready", "conditional", "blocked"] = "conditional"
    headline: str = "Pilot operations are conditional."
    artifact_root: str = Field(default="artifacts/pilot-ops", alias="artifactRoot")
    checklist: list[PilotOperationsChecklistItem] = Field(default_factory=list)
    timeline: list[PilotOperationsTimelineEvent] = Field(default_factory=list)
    acceptance_metrics: dict[str, Any] = Field(default_factory=dict, alias="acceptanceMetrics")
    feedback_bundle_path: str | None = Field(default=None, alias="feedbackBundlePath")
    next_actions: list[PilotLaunchNextAction] = Field(default_factory=list, alias="nextActions")
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class DesignPartnerBetaStatus(StrictModel):
    schema_version: Literal["control-plane.design-partner-beta/v1"] = Field(
        default="control-plane.design-partner-beta/v1",
        alias="schemaVersion",
    )
    generated_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        alias="generatedAtUtc",
    )
    status: Literal["ready", "conditional", "blocked"] = "conditional"
    headline: str = "Design Partner Beta Operations Candidate is conditional."
    artifact_root: str = Field(default="artifacts/design-partner-beta", alias="artifactRoot")
    code_intelligence: CodeIntelligenceSummary = Field(
        default_factory=CodeIntelligenceSummary,
        alias="codeIntelligence",
    )
    pilot_operations: PilotOperationsStatus = Field(
        default_factory=PilotOperationsStatus,
        alias="pilotOperations",
    )
    checks: list[PilotOperationsChecklistItem] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ProviderCapabilities(StrictModel):
    supports_streaming: bool = Field(default=False, alias="supportsStreaming")
    supports_server_tools: bool = Field(default=False, alias="supportsServerTools")
    supports_custom_tools: bool = Field(default=True, alias="supportsCustomTools")
    supports_store_false: bool = Field(default=True, alias="supportsStoreFalse")


class ProviderToolPolicy(StrictModel):
    server_tools_policy: Literal["denied", "approval_required"] = Field(
        default="denied",
        alias="serverToolsPolicy",
    )
    custom_tools_policy: Literal["proposal_only", "approval_required", "execute"] = Field(
        default="proposal_only",
        alias="customToolsPolicy",
    )
    requested_server_tools: list[str] = Field(default_factory=list, alias="requestedServerTools")


class ProviderRetentionPolicy(StrictModel):
    store: bool = False
    evidence_mode: Literal["hash_only"] = Field(default="hash_only", alias="evidenceMode")
    raw_persistence: bool = Field(default=False, alias="rawPersistence")


class NativeRequestEnvelope(StrictModel):
    provider_kind: Literal[
        "ollama",
        "transformers",
        "openai_responses",
        "anthropic_messages",
        "google_gemini",
        "deepseek_chat",
    ] = Field(alias="providerKind")
    model: str
    profile: str = "enterprise"
    request_hash: str = Field(alias="requestHash")
    raw_persistence: bool = Field(default=False, alias="rawPersistence")
    tool_policy: ProviderToolPolicy = Field(alias="toolPolicy")
    retention_policy: ProviderRetentionPolicy = Field(alias="retentionPolicy")
    approval_context: dict[str, Any] | None = Field(default=None, alias="approvalContext")
    native_payload: dict[str, Any] = Field(default_factory=dict, alias="nativePayload")
    created_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        alias="createdAtUtc",
    )


class ProviderNativeResult(StrictModel):
    provider_kind: Literal["openai_responses", "anthropic_messages"] = Field(
        alias="providerKind"
    )
    output_text: str = Field(alias="outputText")
    raw_response_persisted: bool = Field(default=False, alias="rawResponsePersisted")
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProviderPolicyDecision(StrictModel):
    decision: Literal["allow", "deny", "proposal_only", "require_approval"]
    reason_codes: list[str] = Field(default_factory=list, alias="reasonCodes")
    policy_hash: str = Field(alias="policyHash")


class ProviderRegistryEntry(StrictModel):
    provider_kind: Literal[
        "ollama",
        "transformers",
        "openai_responses",
        "anthropic_messages",
        "google_gemini",
        "deepseek_chat",
    ] = Field(alias="providerKind")
    display_name: str = Field(alias="displayName", min_length=1, max_length=80)
    status: Literal["available", "blocked", "conditional", "canary_only"] = "blocked"
    credential_state: Literal["missing", "configured", "not_required", "redacted"] = Field(
        default="missing",
        alias="credentialState",
    )
    canary_only: bool = Field(default=True, alias="canaryOnly")
    supports_streaming: bool = Field(default=False, alias="supportsStreaming")
    server_tools_policy: Literal["denied", "approval_required"] = Field(
        default="denied",
        alias="serverToolsPolicy",
    )
    custom_tools_policy: Literal["proposal_only", "approval_required", "execute"] = Field(
        default="proposal_only",
        alias="customToolsPolicy",
    )
    retention_policy: Literal["hash_only_store_false"] = Field(
        default="hash_only_store_false",
        alias="retentionPolicy",
    )
    last_conformance_status: Literal["pass", "fail", "unknown"] | None = Field(
        default=None,
        alias="lastConformanceStatus",
    )
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")


class ProviderGovernanceSnapshot(StrictModel):
    contract_version: Literal["control-plane.provider-governance/v1"] = Field(
        default="control-plane.provider-governance/v1",
        alias="contractVersion",
    )
    generated_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        alias="generatedAtUtc",
    )
    providers: list[ProviderRegistryEntry] = Field(default_factory=list)
    overall_status: Literal["ready", "conditional", "blocked"] = Field(
        default="conditional",
        alias="overallStatus",
    )
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")


class ProviderConformanceCheck(StrictModel):
    check_id: str = Field(alias="checkId")
    status: Literal["pass", "fail"]
    reason_code: str = Field(alias="reasonCode")
    summary: str


class ProviderConformanceReport(StrictModel):
    schema_version: Literal["control-plane.provider-conformance/v1"] = Field(
        default="control-plane.provider-conformance/v1",
        alias="schemaVersion",
    )
    status: Literal["pass", "fail", "conditional"] = "fail"
    provider_kind: Literal["openai_responses", "anthropic_messages"] = Field(
        alias="providerKind"
    )
    offline: bool = True
    fixtures_run: int = Field(default=0, alias="fixturesRun")
    policy_checks: list[ProviderConformanceCheck] = Field(
        default_factory=list,
        alias="policyChecks",
    )
    evidence_path: str | None = Field(default=None, alias="evidencePath")
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")
    raw_persistence: bool = Field(default=False, alias="rawPersistence")
    request_hashes: list[str] = Field(default_factory=list, alias="requestHashes")
    generated_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        alias="generatedAtUtc",
    )


class ProviderInvocationArtifact(StrictModel):
    schema_version: Literal["provider.invocation.v1"] = Field(
        default="provider.invocation.v1",
        alias="schemaVersion",
    )
    status: Literal["pass", "blocked", "conditional", "error"]
    invocation_id: str = Field(alias="invocationId")
    provider_kind: str = Field(alias="providerKind")
    model: str
    runtime_mode: Literal["offline_conformance", "dry_run", "canary_live", "disabled"] = Field(
        alias="runtimeMode",
    )
    policy_decision: dict[str, Any] = Field(alias="policyDecision")
    request_hash: str = Field(alias="requestHash")
    response_hash: str | None = Field(default=None, alias="responseHash")
    raw_persistence: Literal[False] = Field(default=False, alias="rawPersistence")
    evidence_mode: Literal["hash_only"] = Field(default="hash_only", alias="evidenceMode")
    tool_policy: ProviderToolPolicy = Field(alias="toolPolicy")
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")
    created_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        alias="createdAtUtc",
    )


class ProviderWorkflowProposal(StrictModel):
    proposal_id: str = Field(alias="proposalId")
    action_id: str = Field(alias="actionId")
    risk_class: Literal["read_only", "mutation", "destructive"] = Field(alias="riskClass")
    execution_mode: Literal["proposal_only"] = Field(default="proposal_only", alias="executionMode")
    effect_summary: str = Field(alias="effectSummary")


class ProviderWorkflowProofArtifact(StrictModel):
    schema_version: Literal["provider.workflow-proof.v1"] = Field(
        default="provider.workflow-proof.v1",
        alias="schemaVersion",
    )
    status: Literal["pass", "conditional", "blocked", "error"]
    workflow_id: str = Field(alias="workflowId")
    workflow_kind: Literal["read_only_ops_triage"] = Field(alias="workflowKind")
    agent_id: str = Field(alias="agentId")
    provider_invocations: list[str] = Field(default_factory=list, alias="providerInvocations")
    proposals: list[ProviderWorkflowProposal] = Field(default_factory=list)
    executed_mutations: int = Field(default=0, alias="executedMutations")
    approval_tickets_created: int = Field(default=0, alias="approvalTicketsCreated")
    evidence_artifacts: list[str] = Field(default_factory=list, alias="evidenceArtifacts")
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")
    generated_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        alias="generatedAtUtc",
    )


class ProviderRuntimeSnapshot(StrictModel):
    contract_version: Literal["control-plane.provider-runtime/v1"] = Field(
        default="control-plane.provider-runtime/v1",
        alias="contractVersion",
    )
    generated_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        alias="generatedAtUtc",
    )
    enabled: bool = False
    latest_invocations: list[ProviderInvocationArtifact] = Field(
        default_factory=list,
        alias="latestInvocations",
    )
    workflow_proofs: list[ProviderWorkflowProofArtifact] = Field(
        default_factory=list,
        alias="workflowProofs",
    )
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")


class TargetEvidenceItem(StrictModel):
    item_id: str = Field(alias="itemId")
    kind: str
    path: str
    sha256: str
    status: Literal["pass", "conditional", "blocked", "missing"] = "pass"
    required: bool = True


class TargetEvidenceClaimBoundary(StrictModel):
    public_desktop_installer: Literal["blocked", "conditional", "allowed"] = Field(
        default="blocked",
        alias="publicDesktopInstaller",
    )
    live_macos_computer_use: Literal["blocked", "conditional", "allowed"] = Field(
        default="blocked",
        alias="liveMacosComputerUse",
    )
    live_windows_computer_use: Literal["blocked", "conditional", "allowed"] = Field(
        default="blocked",
        alias="liveWindowsComputerUse",
    )
    live_linux_computer_use: Literal["blocked", "conditional", "allowed"] = Field(
        default="blocked",
        alias="liveLinuxComputerUse",
    )
    blocked_claims: list[str] = Field(default_factory=list, alias="blockedClaims")


class TargetEvidenceSession(StrictModel):
    version: Literal["control-plane.target-evidence-session/v1"] = (
        "control-plane.target-evidence-session/v1"
    )
    session_id: str = Field(alias="sessionId")
    profile: str
    environment_label: str = Field(alias="environmentLabel")
    mode: Literal["rehearsal", "target"]
    started_at_utc: datetime = Field(alias="startedAtUtc")
    operator_id_hash: str | None = Field(default=None, alias="operatorIdHash")
    allowed_claims: list[str] = Field(default_factory=list, alias="allowedClaims")
    blocked_claims: list[str] = Field(default_factory=list, alias="blockedClaims")
    raw_persistence: Literal[False] = Field(default=False, alias="rawPersistence")


class TargetEvidenceBundle(StrictModel):
    version: Literal["control-plane.target-evidence-bundle/v1"] = (
        "control-plane.target-evidence-bundle/v1"
    )
    session_id: str = Field(alias="sessionId")
    status: Literal["pass", "conditional", "blocked"] = "conditional"
    items: list[TargetEvidenceItem] = Field(default_factory=list)
    missing_items: list[str] = Field(default_factory=list, alias="missingItems")
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")
    warnings: list[str] = Field(default_factory=list)
    claim_boundary: TargetEvidenceClaimBoundary = Field(
        default_factory=TargetEvidenceClaimBoundary,
        alias="claimBoundary",
    )
    secret_material_written: bool = Field(default=False, alias="secretMaterialWritten")
    raw_prompt_persisted: bool = Field(default=False, alias="rawPromptPersisted")
    raw_response_persisted: bool = Field(default=False, alias="rawResponsePersisted")
    raw_screenshot_persisted: bool = Field(default=False, alias="rawScreenshotPersisted")


class TargetEvidenceVerificationResult(StrictModel):
    version: Literal["control-plane.target-evidence-verification/v1"] = (
        "control-plane.target-evidence-verification/v1"
    )
    status: Literal["pass", "blocked"]
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")
    warnings: list[str] = Field(default_factory=list)


class OperatorClaimReview(StrictModel):
    claim_id: str = Field(alias="claimId")
    status: Literal["accepted", "rejected", "not_reviewed"]
    boundary_status: Literal["blocked", "conditional", "allowed"] = Field(alias="boundaryStatus")
    notes_hash: str | None = Field(default=None, alias="notesHash")


class OperatorAttestationSignature(StrictModel):
    algorithm: str = "unsigned"
    key_id: str | None = Field(default=None, alias="keyId")
    signature: str | None = None


class OperatorAttestation(StrictModel):
    version: Literal["control-plane.operator-attestation/v1"] = (
        "control-plane.operator-attestation/v1"
    )
    attestation_id: str = Field(alias="attestationId")
    session_id: str = Field(alias="sessionId")
    operator_display_name_hash: str = Field(alias="operatorDisplayNameHash")
    reviewed_claims: list[OperatorClaimReview] = Field(default_factory=list, alias="reviewedClaims")
    accepted_boundaries: list[str] = Field(default_factory=list, alias="acceptedBoundaries")
    signed_at_utc: datetime | None = Field(default=None, alias="signedAtUtc")
    signature: OperatorAttestationSignature | None = None


class AttestationVerificationResult(StrictModel):
    version: Literal["control-plane.operator-attestation-verification/v1"] = (
        "control-plane.operator-attestation-verification/v1"
    )
    status: Literal["pass", "blocked"]
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")
    warnings: list[str] = Field(default_factory=list)


class PilotCandidateManifest(StrictModel):
    version: Literal["control-plane.pilot-candidate/v1"] = "control-plane.pilot-candidate/v1"
    status: Literal["pass", "conditional", "blocked"] = "conditional"
    profile: str = "enterprise"
    rc_status_path: str = Field(alias="rcStatusPath")
    target_evidence_path: str = Field(alias="targetEvidencePath")
    attestation_path: str | None = Field(default=None, alias="attestationPath")
    provider_runtime_proof_path: str = Field(alias="providerRuntimeProofPath")
    claim_guard_path: str = Field(alias="claimGuardPath")
    handoff_docs: list[str] = Field(default_factory=list, alias="handoffDocs")
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")
    warnings: list[str] = Field(default_factory=list)
    generated_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        alias="generatedAtUtc",
    )


class TargetEvidenceClosureSummary(StrictModel):
    contract_version: Literal["control-plane.target-evidence-closure/v1"] = Field(
        default="control-plane.target-evidence-closure/v1",
        alias="contractVersion",
    )
    generated_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        alias="generatedAtUtc",
    )
    status: Literal["pass", "conditional", "blocked", "unknown"] = "unknown"
    session_id: str | None = Field(default=None, alias="sessionId")
    mode: Literal["rehearsal", "target"] | None = None
    evidence_mode: Literal["hash_only"] | None = Field(default=None, alias="evidenceMode")
    raw_persistence: Literal[False] = Field(default=False, alias="rawPersistence")
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")
    warnings: list[str] = Field(default_factory=list)
    blocked_claims: list[str] = Field(default_factory=list, alias="blockedClaims")
    attestation_status: Literal["missing", "present", "signed", "invalid"] = Field(
        default="missing",
        alias="attestationStatus",
    )


class DesignPartnerFieldEvidenceSnapshot(StrictModel):
    schema_version: Literal["control-plane.design-partner-field-evidence/v1"] = Field(
        default="control-plane.design-partner-field-evidence/v1",
        alias="schemaVersion",
    )
    generated_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        alias="generatedAtUtc",
    )
    status: Literal["ready", "conditional", "blocked", "missing"] = "missing"
    mode: Literal["rehearsal", "target_environment"] | None = None
    session_id: str | None = Field(default=None, alias="sessionId")
    evidence_mode: Literal["hash_only"] = Field(default="hash_only", alias="evidenceMode")
    raw_persistence: bool = Field(default=False, alias="rawPersistence")
    attestation_status: Literal["missing", "valid", "invalid", "blocked"] = Field(
        default="missing",
        alias="attestationStatus",
    )
    strict_rc_status: Literal["ready", "conditional", "blocked", "missing"] = Field(
        default="missing",
        alias="strictRcStatus",
    )
    item_count: int = Field(default=0, alias="itemCount")
    blocked_claims: list[str] = Field(default_factory=list, alias="blockedClaims")
    latest_bundle_path: str | None = Field(default=None, alias="latestBundlePath")
    latest_attestation_path: str | None = Field(default=None, alias="latestAttestationPath")
    latest_promotion_path: str | None = Field(default=None, alias="latestPromotionPath")
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")
    warnings: list[str] = Field(default_factory=list)


class DesignPartnerHandoffSnapshot(StrictModel):
    schema_version: Literal["control-plane.design-partner-handoff-snapshot/v1"] = Field(
        default="control-plane.design-partner-handoff-snapshot/v1",
        alias="schemaVersion",
    )
    status: Literal["ready", "conditional", "blocked", "missing"] = "missing"
    handoff_pack_path: str | None = Field(default=None, alias="handoffPackPath")
    release_train_status: str = Field(default="missing", alias="releaseTrainStatus")
    first_run_drill_status: str = Field(default="missing", alias="firstRunDrillStatus")
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    last_generated_at_utc: datetime | None = Field(default=None, alias="lastGeneratedAtUtc")
    claim_boundary_summary: dict[str, str] = Field(
        default_factory=dict,
        alias="claimBoundarySummary",
    )


class MainlineRcFreezeSnapshot(StrictModel):
    schema_version: Literal["control-plane.mainline-rc-freeze-snapshot/v1"] = Field(
        default="control-plane.mainline-rc-freeze-snapshot/v1",
        alias="schemaVersion",
    )
    status: Literal["missing", "conditional", "ready", "blocked"] = "missing"
    freeze_id: str | None = Field(default=None, alias="freezeId")
    manifest_path: str | None = Field(default=None, alias="manifestPath")
    stack_status: str = Field(default="missing", alias="stackStatus")
    merge_rehearsal_status: str = Field(default="missing", alias="mergeRehearsalStatus")
    gate_evidence_status: str = Field(default="missing", alias="gateEvidenceStatus")
    artifact_scan_status: str = Field(default="missing", alias="artifactScanStatus")
    evidence_mode: str = Field(default="hash_only", alias="evidenceMode")
    raw_persistence: bool = Field(default=False, alias="rawPersistence")
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    last_generated_at_utc: datetime | None = Field(default=None, alias="lastGeneratedAtUtc")

class ControlPlaneSnapshot(StrictModel):
    contract_version: Literal["control-plane.snapshot/v1"] = Field(
        default="control-plane.snapshot/v1",
        alias="contractVersion",
    )
    generated_at_utc: datetime = Field(alias="generatedAtUtc")
    data_source: DataSourceState = Field(alias="dataSource")
    system: SystemSummary
    dashboard: DashboardSummary
    agents: list[AgentSummary] = Field(default_factory=list)
    runs: list[RunSnapshotSummary] = Field(default_factory=list)
    approvals: list[ApprovalSnapshotSummary] = Field(default_factory=list)
    evidence_packs: list[EvidencePackSummary] = Field(default_factory=list, alias="evidencePacks")
    policy_packs: list[PolicyPackSummary] = Field(default_factory=list, alias="policyPacks")
    execution_surfaces: list[ExecutionSurfaceSummary] = Field(
        default_factory=list,
        alias="executionSurfaces",
    )
    logs: list[LogEventSummary] = Field(default_factory=list)
    alerts: list[AlertSummary] = Field(default_factory=list)
    reports: list[ReportSummary] = Field(default_factory=list)
    operations: list[OperationDescriptor] = Field(default_factory=list)
    admin: AdminSummary
    design_partner_rc: DesignPartnerRcStatus = Field(
        default_factory=DesignPartnerRcStatus,
        alias="designPartnerRc",
    )
    pilot_launch: PilotLaunchReadinessStatus = Field(alias="pilotLaunch")
    code_intelligence: CodeIntelligenceSummary = Field(
        default_factory=CodeIntelligenceSummary,
        alias="codeIntelligence",
    )
    pilot_operations: PilotOperationsStatus = Field(
        default_factory=PilotOperationsStatus,
        alias="pilotOperations",
    )
    design_partner_beta: DesignPartnerBetaStatus = Field(
        default_factory=DesignPartnerBetaStatus,
        alias="designPartnerBeta",
    )
    provider_governance: ProviderGovernanceSnapshot = Field(
        default_factory=ProviderGovernanceSnapshot,
        alias="providerGovernance",
    )
    provider_runtime: ProviderRuntimeSnapshot = Field(
        default_factory=ProviderRuntimeSnapshot,
        alias="providerRuntime",
    )
    target_evidence_closure: TargetEvidenceClosureSummary = Field(
        default_factory=TargetEvidenceClosureSummary,
        alias="targetEvidenceClosure",
    )
    design_partner_field_evidence: DesignPartnerFieldEvidenceSnapshot = Field(
        default_factory=DesignPartnerFieldEvidenceSnapshot,
        alias="designPartnerFieldEvidence",
    )
    design_partner_handoff: DesignPartnerHandoffSnapshot = Field(
        default_factory=DesignPartnerHandoffSnapshot,
        alias="designPartnerHandoff",
    )
    mainline_rc_freeze: MainlineRcFreezeSnapshot = Field(
        default_factory=MainlineRcFreezeSnapshot,
        alias="mainlineRcFreeze",
    )
    rc_gate_evidence: RcGateEvidenceSnapshot = Field(
        default_factory=RcGateEvidenceSnapshot,
        alias="rcGateEvidence",
    )
    rc_release_decision: RcReleaseDecisionSnapshot = Field(
        default_factory=RcReleaseDecisionSnapshot,
        alias="rcReleaseDecision",
    )
    enterprise_workspace: EnterpriseWorkspaceSnapshot | None = Field(
        default=None,
        alias="enterpriseWorkspace",
    )
    memory_governance: MemoryAuthoritySnapshot = Field(
        default_factory=disabled_memory_authority_snapshot,
        alias="memoryGovernance",
    )
    memory_runtime: MemoryRuntimeSnapshot = Field(
        default_factory=MemoryRuntimeSnapshot,
        alias="memoryRuntime",
    )
    memory_sync: MemorySyncSnapshot = Field(
        default_factory=MemorySyncSnapshot,
        alias="memorySync",
    )
    memory_authority: WorkspaceMemoryAuthorityHealth = Field(
        default_factory=WorkspaceMemoryAuthorityHealth,
        alias="memoryAuthority",
    )
    memory_semantic_index: MemorySemanticIndexSnapshot = Field(
        default_factory=MemorySemanticIndexSnapshot,
        alias="memorySemanticIndex",
    )
    memory_policy_enforcement: MemoryPolicyEnforcementSnapshot = Field(
        default_factory=MemoryPolicyEnforcementSnapshot,
        alias="memoryPolicyEnforcement",
    )
    governed_pilot_workflow: GovernedPilotWorkflowSnapshot = Field(
        default_factory=GovernedPilotWorkflowSnapshot,
        alias="governedPilotWorkflow",
    )
    quick_actions: list[QuickActionSummary] = Field(default_factory=list, alias="quickActions")
    partial_reasons: list[str] = Field(default_factory=list, alias="partialReasons")
