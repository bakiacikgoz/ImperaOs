from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from imperaos.memory.models import StrictModel, sha256_text, stable_id, utc_now
from imperaos.memory.workspace_models import MemoryAccessDecision, WorkspaceScopeType

SemanticBackendKind = Literal["in_memory_fixture", "sqlite_text", "turbovec", "null"]
EmbeddingProviderKind = Literal["deterministic_fixture", "null"]
SemanticSearchMode = Literal["lexical", "semantic", "hybrid"]
SemanticIndexStatusValue = Literal[
    "available_disabled",
    "ready",
    "stale",
    "rebuild_required",
    "blocked",
    "error",
    "unavailable_optional",
]


class EmbeddingRequest(StrictModel):
    text: str = Field(min_length=1, max_length=4000)
    text_hash: str = Field(alias="textHash")
    profile_id: str = Field(default="deterministic-fixture-v1", alias="profileId")
    workspace_id: str = Field(alias="workspaceId")
    redaction_mode: Literal["redacted_summary_only"] = Field(
        default="redacted_summary_only",
        alias="redactionMode",
    )


class EmbeddingResult(StrictModel):
    status: Literal["pass", "blocked", "error"]
    provider: EmbeddingProviderKind = "deterministic_fixture"
    profile_id: str = Field(alias="profileId")
    dimensions: int = 0
    vector: tuple[float, ...] | None = None
    embedding_hash: str | None = Field(default=None, alias="embeddingHash")
    reason_codes: tuple[str, ...] = Field(default_factory=tuple, alias="reasonCodes")
    raw_content_included: Literal[False] = Field(default=False, alias="rawContentIncluded")


class MemoryIndexRecord(StrictModel):
    schema_version: Literal["memory-semantic-index-record/v1"] = Field(
        default="memory-semantic-index-record/v1",
        alias="schemaVersion",
    )
    memory_id: str = Field(alias="memoryId")
    workspace_id: str = Field(alias="workspaceId")
    scope_type: WorkspaceScopeType = Field(alias="scopeType")
    scope_id: str = Field(alias="scopeId")
    content_hash: str = Field(alias="contentHash")
    redacted_summary: str = Field(alias="redactedSummary", min_length=1, max_length=2000)
    summary_hash: str = Field(alias="summaryHash")
    embedding_hash: str = Field(alias="embeddingHash")
    embedding: tuple[float, ...] = Field(default_factory=tuple)
    state_version: int = Field(alias="stateVersion", ge=1)
    created_at_utc: datetime = Field(alias="createdAtUtc")
    updated_at_utc: datetime = Field(alias="updatedAtUtc")
    raw_content_included: Literal[False] = Field(default=False, alias="rawContentIncluded")

    @field_validator("summary_hash", "content_hash", "embedding_hash")
    @classmethod
    def _hash(cls, value: str) -> str:
        if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            raise ValueError("hash fields must be sha256 hex")
        return value


class SemanticIndexManifest(StrictModel):
    schema_version: Literal["memory-semantic-index-manifest/v1"] = Field(
        default="memory-semantic-index-manifest/v1",
        alias="schemaVersion",
    )
    index_id: str = Field(alias="indexId")
    workspace_id: str = Field(alias="workspaceId")
    backend_kind: SemanticBackendKind = Field(alias="backendKind")
    embedding_profile_id: str = Field(alias="embeddingProfileId")
    dimensions: int = Field(default=0, ge=0)
    source_state_version: int = Field(alias="sourceStateVersion", ge=0)
    index_state_version: int = Field(alias="indexStateVersion", ge=0)
    record_count: int = Field(alias="recordCount", ge=0)
    tombstone_count: int = Field(default=0, alias="tombstoneCount", ge=0)
    raw_persistence: Literal[False] = Field(default=False, alias="rawPersistence")
    redaction_mode: Literal["redacted_summary_only"] = Field(
        default="redacted_summary_only",
        alias="redactionMode",
    )
    status: SemanticIndexStatusValue = "ready"
    reason_codes: tuple[str, ...] = Field(default_factory=tuple, alias="reasonCodes")
    created_at_utc: datetime = Field(default_factory=utc_now, alias="createdAtUtc")
    updated_at_utc: datetime = Field(default_factory=utc_now, alias="updatedAtUtc")


class SemanticIndexStatus(StrictModel):
    status: SemanticIndexStatusValue
    enabled: bool = False
    backend_kind: SemanticBackendKind = Field(default="in_memory_fixture", alias="backendKind")
    embedding_profile_id: str = Field(
        default="deterministic-fixture-v1",
        alias="embeddingProfileId",
    )
    workspace_id: str | None = Field(default=None, alias="workspaceId")
    record_count: int = Field(default=0, alias="recordCount", ge=0)
    source_state_version: int = Field(default=0, alias="sourceStateVersion", ge=0)
    index_state_version: int = Field(default=0, alias="indexStateVersion", ge=0)
    raw_persistence: Literal[False] = Field(default=False, alias="rawPersistence")
    reason_codes: tuple[str, ...] = Field(default_factory=tuple, alias="reasonCodes")


class HybridRetrievalScore(StrictModel):
    semantic: float = Field(default=0.0, ge=0.0, le=1.0)
    lexical: float = Field(default=0.0, ge=0.0, le=1.0)
    recency: float = Field(default=0.0, ge=0.0, le=1.0)
    final: float = Field(default=0.0, ge=0.0, le=1.0)


class MemoryVectorHit(StrictModel):
    memory_id: str = Field(alias="memoryId")
    score: float = Field(ge=0.0, le=1.0)
    backend_kind: SemanticBackendKind = Field(alias="backendKind")


class MemorySearchRequest(StrictModel):
    query: str = Field(min_length=1, max_length=4000)
    principal_id: str = Field(alias="principalId")
    workspace_id: str = Field(alias="workspaceId")
    requested_scopes: tuple[str, ...] = Field(default_factory=tuple, alias="requestedScopes")
    limit: int = Field(default=8, ge=1, le=50)
    min_score: float = Field(default=0.0, alias="minScore", ge=0.0, le=1.0)
    mode: SemanticSearchMode = "hybrid"
    include_score_breakdown: bool = Field(default=True, alias="includeScoreBreakdown")
    allow_stale_index: bool = Field(default=False, alias="allowStaleIndex")
    evidence_mode: Literal["hash_only"] = Field(default="hash_only", alias="evidenceMode")


class MemoryRetrievalHit(StrictModel):
    memory_id: str = Field(alias="memoryId")
    workspace_id: str = Field(alias="workspaceId")
    scope_type: WorkspaceScopeType = Field(alias="scopeType")
    scope_id: str = Field(alias="scopeId")
    redacted_summary: str = Field(alias="redactedSummary")
    content_hash: str = Field(alias="contentHash")
    score_breakdown: HybridRetrievalScore = Field(alias="scoreBreakdown")
    policy_decision: MemoryAccessDecision = Field(alias="policyDecision")
    created_at_utc: datetime = Field(alias="createdAtUtc")
    state_version: int = Field(alias="stateVersion")
    raw_content_included: Literal[False] = Field(default=False, alias="rawContentIncluded")


class MemorySearchResult(StrictModel):
    status: Literal["pass", "degraded", "blocked", "error", "empty"]
    query_hash: str = Field(alias="queryHash")
    hits: tuple[MemoryRetrievalHit, ...] = Field(default_factory=tuple)
    index_status: SemanticIndexStatus = Field(alias="indexStatus")
    reason_codes: tuple[str, ...] = Field(default_factory=tuple, alias="reasonCodes")
    evidence_ref: str | None = Field(default=None, alias="evidenceRef")
    scope_violation_count: int = Field(default=0, alias="scopeViolationCount", ge=0)
    raw_leak_count: int = Field(default=0, alias="rawLeakCount", ge=0)
    stale_result_count: int = Field(default=0, alias="staleResultCount", ge=0)
    expired_result_count: int = Field(default=0, alias="expiredResultCount", ge=0)
    raw_content_included: Literal[False] = Field(default=False, alias="rawContentIncluded")


class IndexRebuildRequest(StrictModel):
    workspace_id: str = Field(alias="workspaceId")
    apply: bool = False
    dry_run: bool = Field(default=True, alias="dryRun")
    backend_kind: SemanticBackendKind | None = Field(default=None, alias="backendKind")


class IndexRebuildResult(StrictModel):
    status: Literal["pass", "blocked", "error", "dry_run"]
    manifest: SemanticIndexManifest | None = None
    indexed_record_count: int = Field(default=0, alias="indexedRecordCount", ge=0)
    skipped_record_count: int = Field(default=0, alias="skippedRecordCount", ge=0)
    reason_codes: tuple[str, ...] = Field(default_factory=tuple, alias="reasonCodes")
    raw_content_included: Literal[False] = Field(default=False, alias="rawContentIncluded")


class MemoryRetrievalQualityReport(StrictModel):
    schema_version: Literal["memory-retrieval-quality-report/v1"] = Field(
        default="memory-retrieval-quality-report/v1",
        alias="schemaVersion",
    )
    status: Literal["pass", "fail"]
    query_count: int = Field(alias="queryCount", ge=0)
    top_k_recall: float = Field(alias="topKRecall", ge=0.0, le=1.0)
    hard_negative_leak_count: int = Field(alias="hardNegativeLeakCount", ge=0)
    scope_violation_count: int = Field(default=0, alias="scopeViolationCount", ge=0)
    raw_leak_count: int = Field(default=0, alias="rawLeakCount", ge=0)
    stale_result_count: int = Field(default=0, alias="staleResultCount", ge=0)
    expired_result_count: int = Field(default=0, alias="expiredResultCount", ge=0)
    artifact_path: str | None = Field(default=None, alias="artifactPath")
    reason_codes: tuple[str, ...] = Field(default_factory=tuple, alias="reasonCodes")
    generated_at_utc: datetime = Field(default_factory=utc_now, alias="generatedAtUtc")
    raw_content_included: Literal[False] = Field(default=False, alias="rawContentIncluded")


class MemoryBackendBenchmarkReport(StrictModel):
    status: Literal["pass", "degraded", "unavailable_optional"]
    backend_kind: SemanticBackendKind = Field(alias="backendKind")
    indexed_record_count: int = Field(alias="indexedRecordCount", ge=0)
    query_count: int = Field(alias="queryCount", ge=0)
    p95_latency_ms: float = Field(alias="p95LatencyMs", ge=0.0)
    reason_codes: tuple[str, ...] = Field(default_factory=tuple, alias="reasonCodes")
    raw_content_included: Literal[False] = Field(default=False, alias="rawContentIncluded")


class MemorySemanticIndexSnapshot(StrictModel):
    status: SemanticIndexStatusValue = "available_disabled"
    enabled: bool = False
    runtime_injection_enabled: bool = Field(default=False, alias="runtimeInjectionEnabled")
    default_backend: SemanticBackendKind = Field(
        default="in_memory_fixture",
        alias="defaultBackend",
    )
    embedding_profile: str = Field(
        default="deterministic-fixture-v1",
        alias="embeddingProfile",
    )
    workspace_shard_count: int = Field(default=0, alias="workspaceShardCount", ge=0)
    record_count: int = Field(default=0, alias="recordCount", ge=0)
    last_evaluation_status: Literal["pass", "fail", "missing"] = Field(
        default="missing",
        alias="lastEvaluationStatus",
    )
    experimental_backends: dict[str, str] = Field(
        default_factory=dict,
        alias="experimentalBackends",
    )
    backend_status: dict[str, str] = Field(default_factory=dict, alias="backendStatus")
    raw_persistence: Literal[False] = Field(default=False, alias="rawPersistence")
    reason_codes: tuple[str, ...] = Field(default_factory=tuple, alias="reasonCodes")


def make_index_id(workspace_id: str, backend_kind: str, embedding_profile_id: str) -> str:
    return stable_id("mem_sem_idx", workspace_id, backend_kind, embedding_profile_id)


def query_hash(query: str) -> str:
    return sha256_text(" ".join(query.split()).lower())
