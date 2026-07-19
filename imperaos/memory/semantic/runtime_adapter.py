from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field

from imperaos.memory.context_pack import MemoryContextHit, MemoryContextPack
from imperaos.memory.models import StrictModel, hash_identity, stable_id
from imperaos.memory.principal_resolver import ResolvedMemoryPrincipal
from imperaos.memory.semantic import MemorySearchRequest, SemanticMemoryService
from imperaos.runtime.config import RuntimeConfig

SemanticRuntimeMode = Literal["disabled", "shadow", "enforced"]


class SemanticRuntimeRetrieval(StrictModel):
    status: Literal["disabled", "pass", "empty", "shadow", "blocked", "error"]
    mode: SemanticRuntimeMode = "disabled"
    hit_count: int = Field(default=0, alias="hitCount", ge=0)
    hit_id_hashes: tuple[str, ...] = Field(default_factory=tuple, alias="hitIdHashes")
    reason_codes: tuple[str, ...] = Field(default_factory=tuple, alias="reasonCodes")
    evidence_ref: str | None = Field(default=None, alias="evidenceRef")
    context_pack: MemoryContextPack | None = Field(default=None, alias="contextPack")
    raw_content_included: Literal[False] = Field(default=False, alias="rawContentIncluded")


class SemanticRuntimeAdapter:
    def __init__(
        self,
        *,
        config: RuntimeConfig,
        workspace_authority: object | None,
        evidence_root: str | Path = "artifacts/memory-runtime-policy/semantic",
    ) -> None:
        self.config = config
        self.workspace_authority = workspace_authority
        self.evidence_root = Path(evidence_root)

    def retrieve(
        self,
        *,
        run_id: str,
        query: str,
        resolved: ResolvedMemoryPrincipal,
        mode: SemanticRuntimeMode,
        limit: int,
        max_context_chars: int,
    ) -> SemanticRuntimeRetrieval:
        if mode == "disabled":
            return SemanticRuntimeRetrieval(
                status="disabled",
                mode=mode,
                reasonCodes=("MEMORY_SEMANTIC_RUNTIME_DISABLED",),
            )
        if (
            not self.config.memory.semantic.enabled
            or not self.config.memory.semantic.runtime_injection_enabled
            or self.workspace_authority is None
        ):
            return SemanticRuntimeRetrieval(
                status="disabled",
                mode=mode,
                reasonCodes=("MEMORY_SEMANTIC_RUNTIME_UNAVAILABLE",),
            )
        service = SemanticMemoryService(
            config=self.config,
            authority=self.workspace_authority,
            index_root=self.evidence_root.parent.parent / "memory-semantic" / "indexes",
            evidence_root=self.evidence_root,
        )
        result = service.search(
            MemorySearchRequest(
                query=query,
                principalId=resolved.principal_id,
                workspaceId=resolved.workspace_id,
                requestedScopes=resolved.allowed_scopes,
                limit=max(1, limit),
                allowStaleIndex=False,
            )
        )
        hit_hashes = tuple(hash_identity(hit.memory_id) for hit in result.hits)
        if mode == "shadow":
            return SemanticRuntimeRetrieval(
                status="shadow",
                mode=mode,
                hitCount=len(result.hits),
                hitIdHashes=hit_hashes,
                reasonCodes=result.reason_codes,
                evidenceRef=result.evidence_ref,
            )
        if result.status == "blocked":
            return SemanticRuntimeRetrieval(
                status="blocked",
                mode=mode,
                hitCount=0,
                reasonCodes=result.reason_codes,
                evidenceRef=result.evidence_ref,
            )
        hits = [
            MemoryContextHit(
                memoryId=hit.memory_id,
                scope=f"{hit.scope_type}:{hit.scope_id}",
                visibility=hit.scope_type,
                redactedSummary=hit.redacted_summary[: max_context_chars or 0],
                contentHash=hit.content_hash,
                score=hit.score_breakdown.final,
                createdAt=hit.created_at_utc,
                policyTags=[],
                sourceKind="semantic_runtime",
                policyDecisionRef=hit.policy_decision.evidence_ref,
                semanticScoreBreakdown=hit.score_breakdown.model_dump(mode="json"),
            )
            for hit in result.hits
        ]
        status: Literal["pass", "empty"] = "pass" if hits else "empty"
        pack = MemoryContextPack(
            packId=stable_id(
                "mem_ctx",
                run_id,
                result.query_hash,
                resolved.workspace_id,
                resolved.principal_hash,
                "semantic-runtime",
            ),
            runId=run_id,
            queryHash=result.query_hash,
            status=status,
            hits=hits,
            retrievalFingerprint=stable_id(
                "mem_sem_fp",
                resolved.workspace_id,
                resolved.principal_hash,
                ",".join(hit_hashes),
            ),
            evidenceRef=result.evidence_ref,
            rawContentIncluded=False,
            degradedReason=None,
        )
        return SemanticRuntimeRetrieval(
            status=status,
            mode=mode,
            hitCount=len(hits),
            hitIdHashes=hit_hashes,
            reasonCodes=result.reason_codes,
            evidenceRef=result.evidence_ref,
            contextPack=pack,
        )
