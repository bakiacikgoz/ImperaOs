from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        use_enum_values=True,
    )


class MemoryScope(StrEnum):
    PERSONAL = "personal"
    AGENT = "agent"
    TEAM = "team"
    CASE = "case"
    PROJECT = "project"
    ORGANIZATION = "organization"
    GLOBAL_READONLY = "global_readonly"


class MemoryVisibility(StrEnum):
    PRIVATE = "private"
    AGENT = "agent"
    TEAM = "team"
    PROJECT = "project"
    ORGANIZATION = "organization"
    PUBLIC_READONLY = "public_readonly"


class MemoryOwnerType(StrEnum):
    USER = "user"
    AGENT = "agent"
    TEAM = "team"
    PROJECT = "project"
    CASE = "case"
    ORG = "org"


class MemorySourceType(StrEnum):
    RUN = "run"
    OPERATOR = "operator"
    SYSTEM = "system"
    MIGRATION = "migration"
    EVAL = "eval"


class RetentionClass(StrEnum):
    EPHEMERAL = "ephemeral"
    STANDARD = "standard"
    REGULATED = "regulated"


class MemoryRecordStatus(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    TOMBSTONED = "tombstoned"
    DENIED = "denied"


class MemoryPolicyAction(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"
    PROPOSAL_ONLY = "proposal_only"


class MemoryIndexBackendStatus(StrEnum):
    PASS = "pass"
    DEGRADED = "degraded"
    DISABLED = "disabled"
    UNAVAILABLE = "unavailable"
    ERROR = "error"


SAFE_REF_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/@ -]{0,159}$")
SAFE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$")
HEX_64_PATTERN = re.compile(r"^[a-f0-9]{64}$")


def utc_now() -> datetime:
    return datetime.now(UTC)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def stable_id(prefix: str, *parts: object) -> str:
    digest = sha256_text("|".join(str(part) for part in parts))[:24]
    return f"{prefix}_{digest}"


def hash_identity(value: str) -> str:
    normalized = value.strip()
    if HEX_64_PATTERN.fullmatch(normalized):
        return normalized
    return sha256_text(normalized)


class MemoryScopeFilter(StrictModel):
    scope: MemoryScope
    owner_type: MemoryOwnerType = Field(alias="ownerType")
    owner_id_hash: str = Field(alias="ownerIdHash")
    namespace: str = "default"

    @field_validator("owner_id_hash")
    @classmethod
    def _hash_valid(cls, value: str) -> str:
        if not HEX_64_PATTERN.fullmatch(value):
            raise ValueError("owner_id_hash must be sha256 hex")
        return value


class MemoryPolicyDecision(StrictModel):
    decision: MemoryPolicyAction
    reason_code: str = Field(alias="reasonCode")
    matched_rule_path: str | None = Field(default=None, alias="matchedRulePath")
    approval_id: str | None = Field(default=None, alias="approvalId")
    redaction_required: bool = Field(default=True, alias="redactionRequired")
    index_write_allowed: bool = Field(default=True, alias="indexWriteAllowed")
    evidence_required: bool = Field(default=True, alias="evidenceRequired")
    retention_override: RetentionClass | None = Field(default=None, alias="retentionOverride")
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")


class MemoryWriteProposal(StrictModel):
    proposal_id: str = Field(alias="proposalId")
    actor_id_hash: str = Field(alias="actorIdHash")
    agent_id: str | None = Field(default=None, alias="agentId")
    producer_role: str = Field(alias="producerRole", min_length=1, max_length=120)
    scope: MemoryScope
    owner_type: MemoryOwnerType = Field(alias="ownerType")
    owner_id_hash: str = Field(alias="ownerIdHash")
    visibility: MemoryVisibility
    namespace: str = Field(default="default", min_length=1, max_length=80)
    memory_target: str | None = Field(default=None, alias="memoryTarget", max_length=160)
    expected_state_version: int | None = Field(default=None, ge=0, alias="expectedStateVersion")
    candidate_text: str = Field(alias="candidateText", min_length=1, max_length=8000)
    candidate_summary: str | None = Field(default=None, alias="candidateSummary", max_length=4000)
    source_run_id: str | None = Field(default=None, alias="sourceRunId", max_length=160)
    reason: str = Field(min_length=1, max_length=500)
    idempotency_key: str = Field(alias="idempotencyKey", min_length=8, max_length=160)

    @field_validator("actor_id_hash", "owner_id_hash")
    @classmethod
    def _hash_valid(cls, value: str) -> str:
        if not HEX_64_PATTERN.fullmatch(value):
            raise ValueError("identity fields must be sha256 hex")
        return value

    @field_validator("proposal_id")
    @classmethod
    def _proposal_id_valid(cls, value: str) -> str:
        if not re.fullmatch(r"mem_prop_[A-Za-z0-9_-]{8,80}", value):
            raise ValueError("proposal_id must start with mem_prop_")
        return value

    @field_validator("memory_target")
    @classmethod
    def _target_valid(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if not SAFE_REF_PATTERN.fullmatch(normalized):
            raise ValueError("memory_target contains unsupported characters")
        return normalized

    @model_validator(mode="after")
    def _target_requires_state_version(self) -> MemoryWriteProposal:
        if self.memory_target and self.expected_state_version is None:
            raise ValueError("expected_state_version is required for targeted memory writes")
        return self


class MemoryRecordV3(StrictModel):
    memory_id: str = Field(alias="memoryId")
    schema_version: Literal["memory.v3"] = Field(default="memory.v3", alias="schemaVersion")
    scope: MemoryScope
    owner_type: MemoryOwnerType = Field(alias="ownerType")
    owner_id_hash: str = Field(alias="ownerIdHash")
    visibility: MemoryVisibility
    namespace: str = "default"
    memory_target: str | None = Field(default=None, alias="memoryTarget")
    state_version: int = Field(default=1, ge=1, alias="stateVersion")
    content_summary: str = Field(alias="contentSummary", min_length=1, max_length=4000)
    content_hash: str = Field(alias="contentHash")
    embedding_ref: str | None = Field(default=None, alias="embeddingRef")
    salience: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    source_type: MemorySourceType = Field(default=MemorySourceType.RUN, alias="sourceType")
    source_run_id: str | None = Field(default=None, alias="sourceRunId")
    source_agent_id: str | None = Field(default=None, alias="sourceAgentId")
    source_user_hash: str | None = Field(default=None, alias="sourceUserHash")
    policy_tags: list[str] = Field(default_factory=list, alias="policyTags")
    retention_class: RetentionClass = Field(default=RetentionClass.STANDARD, alias="retentionClass")
    ttl_days: int | None = Field(default=None, ge=1, alias="ttlDays")
    expires_at: datetime | None = Field(default=None, alias="expiresAt")
    status: MemoryRecordStatus = MemoryRecordStatus.ACTIVE
    created_at: datetime = Field(default_factory=utc_now, alias="createdAt")
    updated_at: datetime = Field(default_factory=utc_now, alias="updatedAt")
    provenance: dict[str, Any] = Field(default_factory=dict)

    @field_validator("memory_id")
    @classmethod
    def _memory_id_valid(cls, value: str) -> str:
        if not re.fullmatch(r"mem_[A-Za-z0-9_-]{8,80}", value):
            raise ValueError("memory_id must start with mem_")
        return value

    @field_validator("owner_id_hash", "content_hash", "source_user_hash")
    @classmethod
    def _optional_hash_valid(cls, value: str | None) -> str | None:
        if value is not None and not HEX_64_PATTERN.fullmatch(value):
            raise ValueError("hash fields must be sha256 hex")
        return value

    @field_validator("namespace")
    @classmethod
    def _namespace_valid(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}", value):
            raise ValueError("namespace must be a safe identifier")
        return value

    @model_validator(mode="after")
    def _content_hash_matches_summary(self) -> MemoryRecordV3:
        if self.content_hash != sha256_text(self.content_summary):
            raise ValueError("content_hash must match content_summary")
        return self


class MemoryHit(StrictModel):
    memory_id: str = Field(alias="memoryId")
    scope: MemoryScope
    visibility: MemoryVisibility
    owner_id_hash: str = Field(alias="ownerIdHash")
    content_summary: str | None = Field(default=None, alias="contentSummary")
    content_hash: str = Field(alias="contentHash")
    score: float = Field(ge=0.0)
    created_at: datetime = Field(alias="createdAt")
    policy_tags: list[str] = Field(default_factory=list, alias="policyTags")


class MemoryRetrievalRequest(StrictModel):
    actor_id_hash: str = Field(alias="actorIdHash")
    agent_id: str | None = Field(default=None, alias="agentId")
    requester_role: str = Field(alias="requesterRole", min_length=1, max_length=120)
    query: str = Field(min_length=1, max_length=4000)
    allowed_scopes: list[MemoryScope] = Field(alias="allowedScopes")
    scope_filters: list[MemoryScopeFilter] = Field(default_factory=list, alias="scopeFilters")
    visibility_filters: list[MemoryVisibility] = Field(
        default_factory=lambda: [MemoryVisibility.PRIVATE],
        alias="visibilityFilters",
    )
    limit: int = Field(default=8, ge=1, le=50)
    include_content: bool = Field(default=False, alias="includeContent")
    include_hashes: bool = Field(default=True, alias="includeHashes")
    purpose: Literal["context_injection", "operator_review", "audit", "eval"] = "context_injection"

    @field_validator("actor_id_hash")
    @classmethod
    def _actor_hash_valid(cls, value: str) -> str:
        if not HEX_64_PATTERN.fullmatch(value):
            raise ValueError("actor_id_hash must be sha256 hex")
        return value


class MemoryRetrievalResult(StrictModel):
    status: Literal["pass", "denied", "empty", "degraded", "error"]
    query_hash: str = Field(alias="queryHash")
    hits: list[MemoryHit] = Field(default_factory=list)
    denied_scopes: list[str] = Field(default_factory=list, alias="deniedScopes")
    policy_decision: MemoryPolicyDecision = Field(alias="policyDecision")
    retrieval_fingerprint: str | None = Field(default=None, alias="retrievalFingerprint")
    evidence_ref: str | None = Field(default=None, alias="evidenceRef")
    index_backend: str = Field(alias="indexBackend")
    raw_content_included: bool = Field(default=False, alias="rawContentIncluded")


class MemoryWriteResult(StrictModel):
    status: Literal["written", "denied", "approval_required", "proposal_only", "conflict", "error"]
    proposal_id: str = Field(alias="proposalId")
    memory_id: str | None = Field(default=None, alias="memoryId")
    policy_decision: MemoryPolicyDecision = Field(alias="policyDecision")
    evidence_ref: str | None = Field(default=None, alias="evidenceRef")
    content_hash: str | None = Field(default=None, alias="contentHash")
    state_version: int | None = Field(default=None, alias="stateVersion")
    conflict_detected: bool = Field(default=False, alias="conflictDetected")
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")
    raw_content_included: bool = Field(default=False, alias="rawContentIncluded")


class MemoryTombstoneRequest(StrictModel):
    memory_id: str = Field(alias="memoryId")
    actor_id_hash: str = Field(alias="actorIdHash")
    reason: str = Field(min_length=1, max_length=500)


class MemoryLifecycleResult(StrictModel):
    status: Literal["tombstoned", "missing", "denied", "error"]
    memory_id: str = Field(alias="memoryId")
    evidence_ref: str | None = Field(default=None, alias="evidenceRef")
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")


class MemoryEvidenceEvent(StrictModel):
    event_id: str = Field(alias="eventId")
    event_type: str = Field(alias="eventType")
    memory_id: str | None = Field(default=None, alias="memoryId")
    proposal_id: str | None = Field(default=None, alias="proposalId")
    actor_hash: str | None = Field(default=None, alias="actorHash")
    content_hash: str | None = Field(default=None, alias="contentHash")
    policy_decision: MemoryPolicyDecision = Field(alias="policyDecision")
    raw_content_included: bool = Field(default=False, alias="rawContentIncluded")
    raw_prompt_included: bool = Field(default=False, alias="rawPromptIncluded")
    raw_response_included: bool = Field(default=False, alias="rawResponseIncluded")
    scope: MemoryScope | None = None
    visibility: MemoryVisibility | None = None
    event_hash: str = Field(alias="eventHash")
    created_at_utc: datetime = Field(default_factory=utc_now, alias="createdAtUtc")


class MemoryIndexStatus(StrictModel):
    backend: str
    status: MemoryIndexBackendStatus
    record_count: int = Field(default=0, ge=0, alias="recordCount")
    last_rebuild_at: datetime | None = Field(default=None, alias="lastRebuildAt")
    degraded_reason: str | None = Field(default=None, alias="degradedReason")
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")
    experimental: bool = False


class MemoryAuthorityRecordsSummary(StrictModel):
    active: int = 0
    expired: int = 0
    tombstoned: int = 0
    denied_writes: int = Field(default=0, alias="deniedWrites")
    pending_proposals: int = Field(default=0, alias="pendingProposals")


class MemoryScopeSummary(StrictModel):
    scope: MemoryScope
    visibility: MemoryVisibility
    active_records: int = Field(alias="activeRecords")
    policy: str


class MemoryPrivacySummary(StrictModel):
    raw_prompt_persistence: bool = Field(default=False, alias="rawPromptPersistence")
    raw_response_persistence: bool = Field(default=False, alias="rawResponsePersistence")
    primary_ui_raw_content: bool = Field(default=False, alias="primaryUiRawContent")


class MemoryEvidenceSummary(StrictModel):
    mode: Literal["hash_only_redacted"] = "hash_only_redacted"
    last_artifact_ref: str | None = Field(default=None, alias="lastArtifactRef")


class MemoryAuthoritySnapshot(StrictModel):
    contract_version: Literal["memory.authority-snapshot/v1"] = Field(
        default="memory.authority-snapshot/v1",
        alias="contractVersion",
    )
    enabled: bool
    authority_status: Literal["pass", "disabled", "degraded", "blocked"] = Field(
        alias="authorityStatus"
    )
    store_schema_version: Literal["memory.v3"] = Field(
        default="memory.v3",
        alias="storeSchemaVersion",
    )
    records: MemoryAuthorityRecordsSummary = Field(default_factory=MemoryAuthorityRecordsSummary)
    scopes: list[MemoryScopeSummary] = Field(default_factory=list)
    index: MemoryIndexStatus
    privacy: MemoryPrivacySummary = Field(default_factory=MemoryPrivacySummary)
    evidence: MemoryEvidenceSummary = Field(default_factory=MemoryEvidenceSummary)
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")
    warnings: list[str] = Field(default_factory=list)


def disabled_memory_authority_snapshot() -> MemoryAuthoritySnapshot:
    return MemoryAuthoritySnapshot(
        enabled=False,
        authorityStatus="disabled",
        index=MemoryIndexStatus(backend="sqlite_text", status="disabled", recordCount=0),
        warnings=["MEMORY_V3_DISABLED"],
    )


class MemoryIndexRecord(StrictModel):
    memory_id: str = Field(alias="memoryId")
    scope: MemoryScope
    owner_type: MemoryOwnerType = Field(alias="ownerType")
    owner_id_hash: str = Field(alias="ownerIdHash")
    visibility: MemoryVisibility
    namespace: str = "default"
    text: str
    content_hash: str = Field(alias="contentHash")
    vector: list[float] | None = None


class MemoryIndexWriteResult(StrictModel):
    status: Literal["pass", "degraded", "disabled", "error"]
    indexed_count: int = Field(default=0, alias="indexedCount")
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")


class MemoryIndexDeleteResult(StrictModel):
    status: Literal["pass", "degraded", "disabled", "error"]
    deleted_count: int = Field(default=0, alias="deletedCount")
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")


class MemoryIndexRebuildResult(StrictModel):
    status: Literal["pass", "degraded", "disabled", "error"]
    indexed_count: int = Field(default=0, alias="indexedCount")
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")
