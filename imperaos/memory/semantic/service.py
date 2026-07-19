from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from imperaos.memory.models import sha256_text, utc_now
from imperaos.memory.semantic.backends.in_memory_fixture import InMemoryFixtureSemanticBackend
from imperaos.memory.semantic.backends.null_backend import NullSemanticBackend
from imperaos.memory.semantic.backends.sqlite_text import SQLiteTextSemanticBackend
from imperaos.memory.semantic.backends.turbovec_backend import TurboVecSemanticBackend
from imperaos.memory.semantic.embedding_provider import build_embedding_provider
from imperaos.memory.semantic.evidence import write_semantic_evidence
from imperaos.memory.semantic.hybrid_retriever import score_record
from imperaos.memory.semantic.index_base import SemanticIndexBackend
from imperaos.memory.semantic.index_router import (
    AllowedSemanticScope,
    build_semantic_query_plan,
    parse_requested_scope,
)
from imperaos.memory.semantic.models import (
    EmbeddingRequest,
    IndexRebuildRequest,
    IndexRebuildResult,
    MemoryIndexRecord,
    MemoryRetrievalHit,
    MemorySearchRequest,
    MemorySearchResult,
    MemorySemanticIndexSnapshot,
    SemanticBackendKind,
    SemanticIndexManifest,
    SemanticIndexStatus,
    make_index_id,
    query_hash,
)
from imperaos.memory.workspace_models import (
    MemoryAccessDecision,
    MemoryAccessRequest,
    WorkspaceMemoryRecord,
)
from imperaos.runtime.config import RuntimeConfig


class SemanticMemoryService:
    def __init__(
        self,
        *,
        config: RuntimeConfig,
        authority: Any,
        index_root: str | Path = "artifacts/memory-semantic/indexes",
        evidence_root: str | Path = "artifacts/memory-semantic/events",
    ) -> None:
        self.config = config
        self.authority = authority
        self.index_root = Path(index_root)
        self.evidence_root = Path(evidence_root)
        self.embedding_provider = build_embedding_provider(config.memory.semantic.embedding_profile)

    @property
    def enabled(self) -> bool:
        return bool(self.config.memory.semantic.enabled)

    def backend(self, backend_kind: SemanticBackendKind | None = None) -> SemanticIndexBackend:
        selected = backend_kind or self.config.memory.semantic.backend
        if selected == "in_memory_fixture":
            return InMemoryFixtureSemanticBackend(self.index_root)
        if selected == "sqlite_text":
            return SQLiteTextSemanticBackend(self.index_root)
        if selected == "turbovec":
            return TurboVecSemanticBackend()
        return NullSemanticBackend()

    def status(self, workspace_id: str | None = None) -> SemanticIndexStatus:
        workspace = workspace_id or self.config.memory.workspace_authority.default_workspace_id
        if not self.enabled:
            return SemanticIndexStatus(
                status="available_disabled",
                enabled=False,
                backendKind=self.config.memory.semantic.backend,
                embeddingProfileId=self.config.memory.semantic.embedding_profile,
                workspaceId=workspace,
                reasonCodes=("MEMORY_SEMANTIC_DISABLED",),
            )
        status = self.backend().status(workspace)
        return status.model_copy(
            update={
                "embedding_profile_id": self.config.memory.semantic.embedding_profile,
                "raw_persistence": False,
            }
        )

    def rebuild(self, request: IndexRebuildRequest) -> IndexRebuildResult:
        if not self.enabled:
            return IndexRebuildResult(
                status="blocked",
                reasonCodes=("MEMORY_SEMANTIC_DISABLED",),
            )
        backend_kind = request.backend_kind or self.config.memory.semantic.backend
        if backend_kind == "turbovec" and not self.config.memory.semantic.backends.turbovec.enabled:
            return IndexRebuildResult(
                status="blocked",
                reasonCodes=("MEMORY_TURBOVEC_EXPERIMENTAL_DISABLED",),
            )
        records = self.authority.store.records_for_sync(request.workspace_id)
        index_records: list[MemoryIndexRecord] = []
        skipped = 0
        for record in records:
            if _record_expired(record):
                skipped += 1
                continue
            summary = _record_summary(record)
            text_hash = sha256_text(summary)
            embedding = self.embedding_provider.embed(
                EmbeddingRequest(
                    text=summary,
                    textHash=text_hash,
                    profileId=self.config.memory.semantic.embedding_profile,
                    workspaceId=request.workspace_id,
                )
            )
            if (
                embedding.status != "pass"
                or embedding.vector is None
                or embedding.embedding_hash is None
            ):
                skipped += 1
                continue
            index_records.append(
                MemoryIndexRecord(
                    memoryId=record.memory_id,
                    workspaceId=record.workspace_id,
                    scopeType=record.scope_type,
                    scopeId=record.scope_id,
                    contentHash=record.content_hash,
                    redactedSummary=summary,
                    summaryHash=text_hash,
                    embeddingHash=embedding.embedding_hash,
                    embedding=embedding.vector,
                    stateVersion=record.state_version,
                    createdAtUtc=record.created_at_utc,
                    updatedAtUtc=record.updated_at_utc,
                )
            )
        source_state_version = _source_state_version(tuple(records))
        manifest = SemanticIndexManifest(
            indexId=make_index_id(
                request.workspace_id,
                backend_kind,
                self.config.memory.semantic.embedding_profile,
            ),
            workspaceId=request.workspace_id,
            backendKind=backend_kind,
            embeddingProfileId=self.config.memory.semantic.embedding_profile,
            dimensions=getattr(self.embedding_provider, "dimensions", 0),
            sourceStateVersion=source_state_version,
            indexStateVersion=source_state_version,
            recordCount=len(index_records),
            tombstoneCount=0,
            rawPersistence=False,
            status="ready",
        )
        if request.dry_run or not request.apply:
            return IndexRebuildResult(
                status="dry_run",
                manifest=manifest,
                indexedRecordCount=len(index_records),
                skippedRecordCount=skipped,
            )
        self.backend(backend_kind).write_index(
            manifest=manifest,
            records=tuple(index_records),
        )
        write_semantic_evidence(
            evidence_root=self.evidence_root,
            event_type="semantic_index_rebuild",
            principal_id=self.config.memory.workspace_authority.default_principal_id,
            workspace_id=request.workspace_id,
            hit_ids=tuple(record.memory_id for record in index_records),
        )
        return IndexRebuildResult(
            status="pass",
            manifest=manifest,
            indexedRecordCount=len(index_records),
            skippedRecordCount=skipped,
        )

    def search(self, request: MemorySearchRequest) -> MemorySearchResult:
        q_hash = query_hash(request.query)
        status = self.status(request.workspace_id)
        if not self.enabled:
            return self._blocked_search(
                request,
                status=status,
                query_hash_value=q_hash,
                reason_codes=("MEMORY_SEMANTIC_DISABLED",),
            )
        allowed_scopes, denied_reasons, decisions = self._allowed_scopes(request)
        plan = build_semantic_query_plan(
            allowed_scopes=tuple(allowed_scopes),
            denied_reason_codes=tuple(denied_reasons),
        )
        if plan.status != "pass":
            return self._blocked_search(
                request,
                status=status,
                query_hash_value=q_hash,
                reason_codes=plan.reason_codes,
            )
        workspace_records = tuple(self.authority.store.records_for_sync(request.workspace_id))
        source_records = self._allowed_source_records(
            workspace_records=workspace_records,
            allowed_scopes=tuple(allowed_scopes),
        )
        source_state_version = _source_state_version(workspace_records)
        if (
            status.status == "ready"
            and source_state_version > status.index_state_version
            and not request.allow_stale_index
            and not self.config.memory.semantic.allow_stale_index
        ):
            return self._blocked_search(
                request,
                status=status.model_copy(
                    update={
                        "status": "stale",
                        "reason_codes": ("MEMORY_SEMANTIC_INDEX_STALE",),
                    }
                ),
                query_hash_value=q_hash,
                reason_codes=("MEMORY_SEMANTIC_INDEX_STALE",),
            )
        indexed_records = {
            record.memory_id: record
            for record in self.backend().read_records(request.workspace_id)
        }
        if not indexed_records:
            return self._blocked_search(
                request,
                status=status,
                query_hash_value=q_hash,
                reason_codes=("MEMORY_SEMANTIC_INDEX_MISSING",),
            )
        query_text = " ".join(request.query.split())
        embedding = self.embedding_provider.embed(
            EmbeddingRequest(
                text=query_text,
                textHash=sha256_text(query_text),
                profileId=self.config.memory.semantic.embedding_profile,
                workspaceId=request.workspace_id,
            )
        )
        if embedding.status != "pass" or embedding.vector is None:
            return self._blocked_search(
                request,
                status=status,
                query_hash_value=q_hash,
                reason_codes=embedding.reason_codes,
            )
        source_by_id = {record.memory_id: record for record in source_records}
        allowed_ids = set(source_by_id)
        scored: list[MemoryRetrievalHit] = []
        decision_by_scope = {
            (scope.scope_type, scope.scope_id): decisions[(scope.scope_type, scope.scope_id)]
            for scope in allowed_scopes
        }
        for memory_id in allowed_ids:
            index_record = indexed_records.get(memory_id)
            source_record = source_by_id[memory_id]
            if index_record is None or _record_expired(source_record):
                continue
            score = score_record(
                query=request.query,
                query_vector=embedding.vector,
                record=index_record,
            )
            if score.final < request.min_score:
                continue
            policy_decision = decision_by_scope[(source_record.scope_type, source_record.scope_id)]
            scored.append(
                MemoryRetrievalHit(
                    memoryId=source_record.memory_id,
                    workspaceId=source_record.workspace_id,
                    scopeType=source_record.scope_type,
                    scopeId=source_record.scope_id,
                    redactedSummary=index_record.redacted_summary,
                    contentHash=source_record.content_hash,
                    scoreBreakdown=score,
                    policyDecision=policy_decision,
                    createdAtUtc=source_record.created_at_utc,
                    stateVersion=source_record.state_version,
                )
            )
        hits = tuple(
            sorted(scored, key=lambda item: item.score_breakdown.final, reverse=True)[
                : min(request.limit, self.config.memory.semantic.max_hits)
            ]
        )
        evidence_ref = write_semantic_evidence(
            evidence_root=self.evidence_root,
            event_type="semantic_memory_search",
            principal_id=request.principal_id,
            workspace_id=request.workspace_id,
            query_hash=q_hash,
            hit_ids=tuple(hit.memory_id for hit in hits),
            reason_codes=(),
        )
        return MemorySearchResult(
            status="pass" if hits else "empty",
            queryHash=q_hash,
            hits=hits,
            indexStatus=status,
            evidenceRef=evidence_ref,
        )

    def _blocked_search(
        self,
        request: MemorySearchRequest,
        *,
        status: SemanticIndexStatus,
        query_hash_value: str,
        reason_codes: tuple[str, ...],
    ) -> MemorySearchResult:
        evidence_ref = write_semantic_evidence(
            evidence_root=self.evidence_root,
            event_type="semantic_memory_search_blocked",
            principal_id=request.principal_id,
            workspace_id=request.workspace_id,
            query_hash=query_hash_value,
            reason_codes=reason_codes,
        )
        return MemorySearchResult(
            status="blocked",
            queryHash=query_hash_value,
            indexStatus=status,
            reasonCodes=reason_codes,
            evidenceRef=evidence_ref,
        )

    def _allowed_scopes(
        self,
        request: MemorySearchRequest,
    ) -> tuple[list[AllowedSemanticScope], list[str], dict[tuple[str, str], MemoryAccessDecision]]:
        requested = request.requested_scopes or (f"personal:{request.principal_id}",)
        allowed: list[AllowedSemanticScope] = []
        denied: list[str] = []
        decisions: dict[tuple[str, str], MemoryAccessDecision] = {}
        for raw_scope in requested:
            try:
                scope_type, scope_id = parse_requested_scope(raw_scope)
            except ValueError:
                denied.append("MEMORY_SEMANTIC_SCOPE_INVALID")
                continue
            decision = self.authority.evaluator.evaluate(
                MemoryAccessRequest(
                    workspaceId=request.workspace_id,
                    principalId=request.principal_id,
                    action="read",
                    scopeType=scope_type,
                    scopeId=scope_id,
                    permission=f"memory.read.{scope_type}",
                    purpose="semantic memory retrieval",
                )
            )
            decisions[(scope_type, scope_id)] = decision
            if decision.action == "allow":
                allowed.append(
                    AllowedSemanticScope(
                        scope_type=scope_type,
                        scope_id=scope_id,
                        reason_code=decision.reason_code,
                    )
                )
            else:
                denied.append(decision.reason_code)
        return allowed, denied, decisions

    def _allowed_source_records(
        self,
        *,
        workspace_records: tuple[WorkspaceMemoryRecord, ...],
        allowed_scopes: tuple[AllowedSemanticScope, ...],
    ) -> tuple[WorkspaceMemoryRecord, ...]:
        allowed = {(scope.scope_type, scope.scope_id) for scope in allowed_scopes}
        records = []
        for record in workspace_records:
            if (record.scope_type, record.scope_id) in allowed and not _record_expired(record):
                records.append(record)
        return tuple(records)


def build_memory_semantic_snapshot(
    *,
    config: RuntimeConfig,
    evidence_root: str | Path = "artifacts",
    generated_at: datetime | None = None,
) -> MemorySemanticIndexSnapshot:
    _ = generated_at
    semantic = config.memory.semantic
    if not semantic.enabled:
        return MemorySemanticIndexSnapshot(
            status="available_disabled",
            enabled=False,
            runtimeInjectionEnabled=False,
            defaultBackend=semantic.backend,
            embeddingProfile=semantic.embedding_profile,
            experimentalBackends={"turbovec": "disabled"},
            backendStatus={semantic.backend: "disabled"},
            reasonCodes=("MEMORY_SEMANTIC_DISABLED",),
        )
    evaluation_status = "missing"
    quality_path = Path(evidence_root) / "memory-semantic" / "retrieval_quality_report.json"
    if quality_path.exists():
        evaluation_status = "pass" if '"status": "pass"' in quality_path.read_text() else "fail"
    return MemorySemanticIndexSnapshot(
        status="rebuild_required",
        enabled=True,
        runtimeInjectionEnabled=semantic.runtime_injection_enabled,
        defaultBackend=semantic.backend,
        embeddingProfile=semantic.embedding_profile,
        experimentalBackends={
            "turbovec": "enabled" if semantic.backends.turbovec.enabled else "disabled"
        },
        backendStatus={semantic.backend: "configured"},
        lastEvaluationStatus=evaluation_status,
    )


def _record_summary(record: WorkspaceMemoryRecord) -> str:
    return " ".join((record.redacted_preview or record.summary).split())[:2000]


def _record_expired(record: WorkspaceMemoryRecord) -> bool:
    if record.tombstoned_at_utc is not None:
        return True
    if record.expires_at_utc is None:
        return False
    expires = record.expires_at_utc
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    return expires <= utc_now()


def _source_state_version(records: tuple[WorkspaceMemoryRecord, ...]) -> int:
    return len(records) + sum(record.state_version for record in records)
