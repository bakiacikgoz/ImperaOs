from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator, model_validator

from imperaos.memory.models import StrictModel, sha256_text, stable_id, utc_now

WorkspaceStatus = Literal["active", "archived", "blocked"]
PrincipalType = Literal["user", "agent", "service", "operator"]
PrincipalStatus = Literal["active", "disabled", "revoked"]
WorkspaceRole = Literal["owner", "admin", "operator", "agent", "viewer", "auditor"]
MembershipStatus = Literal["active", "suspended"]
WorkspaceScopeType = Literal[
    "personal",
    "agent",
    "team",
    "project",
    "case",
    "organization",
    "global_readonly",
]
MemoryClassification = Literal["public", "internal", "restricted", "secret_like"]
MemoryAccessAction = Literal["read", "write", "admin", "sync_export", "sync_import", "audit_read"]
MemoryAccessDecisionAction = Literal["allow", "deny", "proposal_only", "requires_approval"]

SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{1,127}$")
PERMISSION_RE = re.compile(r"^memory\.[a-z_]+\.[a-z_]+$")


class MemoryWorkspace(StrictModel):
    schema_version: Literal["memory-workspace/v1"] = Field(
        default="memory-workspace/v1",
        alias="schemaVersion",
    )
    workspace_id: str = Field(alias="workspaceId")
    display_name: str = Field(alias="displayName", min_length=1, max_length=160)
    owner_principal_id: str = Field(alias="ownerPrincipalId")
    status: WorkspaceStatus = "active"
    policy_pack_id: str | None = Field(default=None, alias="policyPackId")
    created_at_utc: datetime = Field(default_factory=utc_now, alias="createdAtUtc")
    updated_at_utc: datetime = Field(default_factory=utc_now, alias="updatedAtUtc")

    @field_validator("workspace_id", "owner_principal_id", "policy_pack_id")
    @classmethod
    def _safe_id(cls, value: str | None) -> str | None:
        return _validate_optional_id(value)


class MemoryPrincipal(StrictModel):
    schema_version: Literal["memory-principal/v1"] = Field(
        default="memory-principal/v1",
        alias="schemaVersion",
    )
    principal_id: str = Field(alias="principalId")
    principal_type: PrincipalType = Field(alias="principalType")
    display_name: str = Field(alias="displayName", min_length=1, max_length=160)
    status: PrincipalStatus = "active"
    external_subject_ref_hash: str | None = Field(default=None, alias="externalSubjectRefHash")
    created_at_utc: datetime = Field(default_factory=utc_now, alias="createdAtUtc")

    @field_validator("principal_id")
    @classmethod
    def _principal_id(cls, value: str) -> str:
        return _validate_id(value)

    @field_validator("external_subject_ref_hash")
    @classmethod
    def _subject_ref_hash(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return sha256_text(value) if not re.fullmatch(r"[a-f0-9]{64}", value) else value


class MemoryWorkspaceMembership(StrictModel):
    schema_version: Literal["memory-membership/v1"] = Field(
        default="memory-membership/v1",
        alias="schemaVersion",
    )
    membership_id: str = Field(alias="membershipId")
    workspace_id: str = Field(alias="workspaceId")
    principal_id: str = Field(alias="principalId")
    roles: tuple[WorkspaceRole, ...]
    status: MembershipStatus = "active"
    granted_by: str = Field(alias="grantedBy")
    granted_at_utc: datetime = Field(default_factory=utc_now, alias="grantedAtUtc")

    @field_validator("membership_id", "workspace_id", "principal_id", "granted_by")
    @classmethod
    def _safe_id(cls, value: str) -> str:
        return _validate_id(value)

    @field_validator("roles")
    @classmethod
    def _roles_non_empty(cls, value: tuple[WorkspaceRole, ...]) -> tuple[WorkspaceRole, ...]:
        if not value:
            raise ValueError("roles must not be empty")
        return tuple(sorted(set(value)))


class MemoryScopeDescriptor(StrictModel):
    scope_type: WorkspaceScopeType = Field(alias="scopeType")
    scope_id: str = Field(alias="scopeId")
    workspace_id: str = Field(alias="workspaceId")
    owner_principal_id: str | None = Field(default=None, alias="ownerPrincipalId")
    classification: MemoryClassification = "internal"
    default_visibility: Literal["private", "team", "workspace", "readonly"] = Field(
        default="private",
        alias="defaultVisibility",
    )

    @field_validator("scope_id", "workspace_id", "owner_principal_id")
    @classmethod
    def _safe_id(cls, value: str | None) -> str | None:
        return _validate_optional_id(value)


class MemoryScopeAclRule(StrictModel):
    schema_version: Literal["memory-scope-acl/v1"] = Field(
        default="memory-scope-acl/v1",
        alias="schemaVersion",
    )
    acl_id: str = Field(alias="aclId")
    workspace_id: str = Field(alias="workspaceId")
    scope_type: WorkspaceScopeType = Field(alias="scopeType")
    scope_id: str = Field(alias="scopeId")
    principal_id: str | None = Field(default=None, alias="principalId")
    role: WorkspaceRole | None = None
    permissions: tuple[str, ...]
    effect: Literal["allow", "deny"]
    reason: str = Field(min_length=1, max_length=400)
    created_at_utc: datetime = Field(default_factory=utc_now, alias="createdAtUtc")

    @field_validator("acl_id", "workspace_id", "scope_id", "principal_id")
    @classmethod
    def _safe_id(cls, value: str | None) -> str | None:
        return _validate_optional_id(value)

    @field_validator("permissions")
    @classmethod
    def _permissions(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("permissions must not be empty")
        for item in value:
            if not PERMISSION_RE.fullmatch(item):
                raise ValueError(f"invalid memory permission: {item}")
        return tuple(sorted(set(value)))

    @model_validator(mode="after")
    def _principal_or_role_required(self) -> MemoryScopeAclRule:
        if self.principal_id is None and self.role is None:
            raise ValueError("principal_id or role is required")
        return self


class WorkspaceMemoryRecord(StrictModel):
    schema_version: Literal["workspace-memory-record/v1"] = Field(
        default="workspace-memory-record/v1",
        alias="schemaVersion",
    )
    memory_id: str = Field(alias="memoryId")
    workspace_id: str = Field(alias="workspaceId")
    scope_type: WorkspaceScopeType = Field(alias="scopeType")
    scope_id: str = Field(alias="scopeId")
    owner_principal_id: str = Field(alias="ownerPrincipalId")
    source_agent_id: str | None = Field(default=None, alias="sourceAgentId")
    source_run_id: str | None = Field(default=None, alias="sourceRunId")
    source_user_id: str | None = Field(default=None, alias="sourceUserId")
    memory_target: str | None = Field(default=None, alias="memoryTarget", max_length=160)
    state_version: int = Field(default=1, ge=1, alias="stateVersion")
    content_hash: str = Field(alias="contentHash")
    summary: str = Field(min_length=1, max_length=2000)
    redacted_preview: str | None = Field(default=None, alias="redactedPreview", max_length=500)
    embedding_ref: str | None = Field(default=None, alias="embeddingRef")
    salience: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    classification: MemoryClassification = "internal"
    policy_tags: tuple[str, ...] = Field(default_factory=tuple, alias="policyTags")
    ttl_days: int | None = Field(default=None, ge=1, alias="ttlDays")
    expires_at_utc: datetime | None = Field(default=None, alias="expiresAtUtc")
    created_at_utc: datetime = Field(default_factory=utc_now, alias="createdAtUtc")
    updated_at_utc: datetime = Field(default_factory=utc_now, alias="updatedAtUtc")
    tombstoned_at_utc: datetime | None = Field(default=None, alias="tombstonedAtUtc")

    @field_validator(
        "memory_id",
        "workspace_id",
        "scope_id",
        "owner_principal_id",
        "source_agent_id",
        "source_run_id",
        "source_user_id",
    )
    @classmethod
    def _safe_id(cls, value: str | None) -> str | None:
        return _validate_optional_id(value)

    @field_validator("content_hash")
    @classmethod
    def _content_hash(cls, value: str) -> str:
        if not re.fullmatch(r"[a-f0-9]{64}", value):
            raise ValueError("content_hash must be sha256 hex")
        return value


class WorkspaceMemoryVersion(StrictModel):
    memory_id: str = Field(alias="memoryId")
    state_version: int = Field(alias="stateVersion", ge=1)
    previous_state_version: int | None = Field(default=None, alias="previousStateVersion")
    content_hash: str = Field(alias="contentHash")
    summary_hash: str = Field(alias="summaryHash")
    changed_by_principal_id: str = Field(alias="changedByPrincipalId")
    change_reason: str = Field(alias="changeReason")
    created_at_utc: datetime = Field(default_factory=utc_now, alias="createdAtUtc")


class WorkspaceMemoryConflict(StrictModel):
    conflict_id: str = Field(alias="conflictId")
    workspace_id: str = Field(alias="workspaceId")
    memory_id: str | None = Field(default=None, alias="memoryId")
    memory_target: str | None = Field(default=None, alias="memoryTarget")
    local_state_version: int | None = Field(default=None, alias="localStateVersion")
    incoming_state_version: int | None = Field(default=None, alias="incomingStateVersion")
    conflict_type: Literal[
        "state_version_mismatch",
        "same_target_different_hash",
        "tombstone_vs_update",
        "acl_denied",
        "classification_upgrade_required",
    ] = Field(alias="conflictType")
    decision: Literal["pending", "accepted", "rejected", "merged"] = "pending"
    requires_approval: bool = Field(default=True, alias="requiresApproval")
    created_at_utc: datetime = Field(default_factory=utc_now, alias="createdAtUtc")


class MemoryAccessRequest(StrictModel):
    workspace_id: str = Field(alias="workspaceId")
    principal_id: str = Field(alias="principalId")
    action: MemoryAccessAction
    scope_type: WorkspaceScopeType = Field(alias="scopeType")
    scope_id: str = Field(alias="scopeId")
    permission: str
    purpose: str = "runtime"
    classification: MemoryClassification | None = None


class MemoryAccessDecision(StrictModel):
    action: MemoryAccessDecisionAction
    reason_code: str = Field(alias="reasonCode")
    matched_rules: tuple[str, ...] = Field(default_factory=tuple, alias="matchedRules")
    requires_approval: bool = Field(default=False, alias="requiresApproval")
    redaction_required: bool = Field(default=True, alias="redactionRequired")
    evidence_ref: str | None = Field(default=None, alias="evidenceRef")


class WorkspaceMemoryQueryRequest(StrictModel):
    workspace_id: str = Field(alias="workspaceId")
    principal_id: str = Field(alias="principalId")
    scope_type: WorkspaceScopeType = Field(alias="scopeType")
    scope_id: str = Field(alias="scopeId")
    query: str = Field(default="", max_length=4000)
    purpose: str = "context_injection"
    limit: int = Field(default=5, ge=1, le=50)
    classification: MemoryClassification | None = None


class WorkspaceMemoryQueryResult(StrictModel):
    status: Literal["pass", "empty", "denied", "error"]
    decision: MemoryAccessDecision
    records: list[WorkspaceMemoryRecord] = Field(default_factory=list)
    query_hash: str = Field(alias="queryHash")
    evidence_ref: str | None = Field(default=None, alias="evidenceRef")
    raw_content_included: Literal[False] = Field(default=False, alias="rawContentIncluded")


class WorkspaceMemoryWriteRequest(StrictModel):
    workspace_id: str = Field(alias="workspaceId")
    principal_id: str = Field(alias="principalId")
    scope_type: WorkspaceScopeType = Field(alias="scopeType")
    scope_id: str = Field(alias="scopeId")
    summary: str = Field(min_length=1, max_length=4000)
    memory_target: str | None = Field(default=None, alias="memoryTarget")
    expected_state_version: int | None = Field(default=None, ge=0, alias="expectedStateVersion")
    source_agent_id: str | None = Field(default=None, alias="sourceAgentId")
    source_run_id: str | None = Field(default=None, alias="sourceRunId")
    classification: MemoryClassification = "internal"
    reason: str = "workspace memory write"


class WorkspaceMemoryWriteDecision(StrictModel):
    status: Literal["committed", "proposal_only", "requires_approval", "denied", "conflict"]
    decision: MemoryAccessDecision
    memory_id: str | None = Field(default=None, alias="memoryId")
    proposal_id: str | None = Field(default=None, alias="proposalId")
    conflict_id: str | None = Field(default=None, alias="conflictId")
    state_version: int | None = Field(default=None, alias="stateVersion")
    content_hash: str | None = Field(default=None, alias="contentHash")
    evidence_ref: str | None = Field(default=None, alias="evidenceRef")
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")
    raw_content_included: Literal[False] = Field(default=False, alias="rawContentIncluded")


class WorkspaceMemoryTombstoneRequest(StrictModel):
    workspace_id: str = Field(alias="workspaceId")
    principal_id: str = Field(alias="principalId")
    memory_id: str = Field(alias="memoryId")
    reason: str = Field(min_length=1, max_length=500)


class WorkspaceMemoryTombstoneResult(StrictModel):
    status: Literal["tombstoned", "denied", "missing"]
    memory_id: str = Field(alias="memoryId")
    evidence_ref: str | None = Field(default=None, alias="evidenceRef")
    raw_content_included: Literal[False] = Field(default=False, alias="rawContentIncluded")


class WorkspaceMemoryAuthorityHealth(StrictModel):
    status: Literal["available", "disabled", "setup_required", "blocked"] = "disabled"
    mode: Literal["local_authority"] = "local_authority"
    workspace_count: int = Field(default=0, alias="workspaceCount")
    principal_count: int = Field(default=0, alias="principalCount")
    active_scope_count: int = Field(default=0, alias="activeScopeCount")
    pending_proposal_count: int = Field(default=0, alias="pendingProposalCount")
    pending_conflict_count: int = Field(default=0, alias="pendingConflictCount")
    last_sync_pack_status: str | None = Field(default=None, alias="lastSyncPackStatus")
    raw_content_exposed: Literal[False] = Field(default=False, alias="rawContentExposed")
    network_listener_enabled: Literal[False] = Field(default=False, alias="networkListenerEnabled")
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")


class StoreWriteResult(StrictModel):
    status: Literal["created", "updated", "unchanged"]
    id: str


class WorkspaceMemoryCommitResult(StrictModel):
    status: Literal["committed", "conflict"]
    memory_id: str | None = Field(default=None, alias="memoryId")
    state_version: int | None = Field(default=None, alias="stateVersion")
    conflict: WorkspaceMemoryConflict | None = None


class WorkspaceMemorySyncClient(StrictModel):
    client_id: str = Field(alias="clientId")
    workspace_id: str = Field(alias="workspaceId")
    principal_id: str = Field(alias="principalId")
    client_kind: Literal["cli", "operator_panel", "agent_host", "import_tool"] = Field(
        alias="clientKind"
    )
    status: Literal["active", "revoked"] = "active"
    last_export_cursor: str | None = Field(default=None, alias="lastExportCursor")
    last_import_cursor: str | None = Field(default=None, alias="lastImportCursor")
    created_at_utc: datetime = Field(default_factory=utc_now, alias="createdAtUtc")


class WorkspaceMemorySyncPackManifest(StrictModel):
    schema_version: Literal["workspace-memory-sync-pack/v2"] = Field(
        default="workspace-memory-sync-pack/v2",
        alias="schemaVersion",
    )
    pack_id: str = Field(alias="packId")
    workspace_id: str = Field(alias="workspaceId")
    source_client_id: str = Field(alias="sourceClientId")
    generated_at_utc: datetime = Field(default_factory=utc_now, alias="generatedAtUtc")
    cursor_from: str | None = Field(default=None, alias="cursorFrom")
    cursor_to: str = Field(alias="cursorTo")
    record_count: int = Field(alias="recordCount", ge=0)
    tombstone_count: int = Field(default=0, alias="tombstoneCount", ge=0)
    conflict_count: int = Field(default=0, alias="conflictCount", ge=0)
    evidence_mode: Literal["hash_only"] = Field(default="hash_only", alias="evidenceMode")
    raw_content_included: Literal[False] = Field(default=False, alias="rawContentIncluded")
    item_hashes: dict[str, str] = Field(default_factory=dict, alias="itemHashes")
    manifest_hash: str = Field(alias="manifestHash")


class WorkspaceMemorySyncPack(StrictModel):
    manifest: WorkspaceMemorySyncPackManifest
    records: list[WorkspaceMemoryRecord] = Field(default_factory=list)
    tombstones: list[WorkspaceMemoryTombstoneResult] = Field(default_factory=list)


class WorkspaceMemorySyncVerifyResult(StrictModel):
    status: Literal["pass", "fail"]
    pack_id: str | None = Field(default=None, alias="packId")
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")
    raw_content_included: Literal[False] = Field(default=False, alias="rawContentIncluded")


class WorkspaceMemorySyncImportReport(StrictModel):
    status: Literal["pass", "blocked", "applied"]
    pack_id: str | None = Field(default=None, alias="packId")
    dry_run: bool = Field(alias="dryRun")
    records_seen: int = Field(default=0, alias="recordsSeen")
    records_applied: int = Field(default=0, alias="recordsApplied")
    conflicts: list[WorkspaceMemoryConflict] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")
    approval_id: str | None = Field(default=None, alias="approvalId")
    raw_content_included: Literal[False] = Field(default=False, alias="rawContentIncluded")


class LegacyMemoryMigrationPlanRequest(StrictModel):
    legacy_db_path: str = Field(alias="legacyDbPath")
    workspace_id: str = Field(alias="workspaceId")
    default_scope: str = Field(alias="defaultScope")
    output_path: str | None = Field(default=None, alias="outputPath")


class LegacyMemoryRecordPlan(StrictModel):
    source_record_id: str = Field(alias="sourceRecordId")
    target_scope_type: WorkspaceScopeType = Field(alias="targetScopeType")
    target_scope_id: str = Field(alias="targetScopeId")
    summary_hash: str = Field(alias="summaryHash")
    content_hash: str = Field(alias="contentHash")
    warnings: list[str] = Field(default_factory=list)


class LegacyMemoryMigrationPlanResult(StrictModel):
    schema_version: Literal["memory-migration-plan/v1"] = Field(
        default="memory-migration-plan/v1",
        alias="schemaVersion",
    )
    status: Literal["pass", "warning", "blocked"]
    workspace_id: str = Field(alias="workspaceId")
    records_seen: int = Field(default=0, alias="recordsSeen")
    records_planned: int = Field(default=0, alias="recordsPlanned")
    plans: list[LegacyMemoryRecordPlan] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    raw_content_included: Literal[False] = Field(default=False, alias="rawContentIncluded")


def make_memory_id(*parts: object) -> str:
    return stable_id("wm", *parts)


def _validate_id(value: str) -> str:
    if not SAFE_ID_RE.fullmatch(value):
        raise ValueError("identifier must be 2-128 safe characters")
    return value


def _validate_optional_id(value: str | None) -> str | None:
    if value is None:
        return None
    return _validate_id(value)
