from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from imperaos.memory.models import (
    MemoryHit,
    MemoryRetrievalResult,
    StrictModel,
    sha256_text,
    stable_id,
    utc_now,
)


class MemoryContextHit(StrictModel):
    memory_id: str = Field(alias="memoryId")
    scope: str
    visibility: str
    redacted_summary: str = Field(alias="redactedSummary")
    content_hash: str = Field(alias="contentHash")
    score: float = Field(ge=0.0)
    created_at: datetime = Field(alias="createdAt")
    policy_tags: list[str] = Field(default_factory=list, alias="policyTags")
    source_kind: str = Field(default="runtime_bridge", alias="sourceKind")
    policy_decision_ref: str | None = Field(default=None, alias="policyDecisionRef")
    semantic_score_breakdown: dict[str, float] = Field(
        default_factory=dict,
        alias="semanticScoreBreakdown",
    )


class MemoryContextPack(StrictModel):
    version: Literal["memory.context-pack/v1"] = "memory.context-pack/v1"
    pack_id: str = Field(alias="packId")
    run_id: str = Field(alias="runId")
    query_hash: str = Field(alias="queryHash")
    status: Literal["pass", "empty", "denied", "degraded", "disabled", "error"]
    hits: list[MemoryContextHit] = Field(default_factory=list)
    retrieval_fingerprint: str | None = Field(default=None, alias="retrievalFingerprint")
    evidence_ref: str | None = Field(default=None, alias="evidenceRef")
    denied_scopes: list[str] = Field(default_factory=list, alias="deniedScopes")
    raw_content_included: Literal[False] = Field(default=False, alias="rawContentIncluded")
    truncated: bool = False
    degraded_reason: str | None = Field(default=None, alias="degradedReason")
    created_at_utc: datetime = Field(default_factory=utc_now, alias="createdAtUtc")

    @model_validator(mode="after")
    def _no_raw_content(self) -> MemoryContextPack:
        if self.raw_content_included is not False:
            raise ValueError("MemoryContextPack cannot include raw content")
        return self


def empty_context_pack(
    *,
    run_id: str,
    query: str,
    status: Literal["empty", "disabled", "degraded", "error"] = "empty",
    degraded_reason: str | None = None,
) -> MemoryContextPack:
    return MemoryContextPack(
        packId=stable_id("mem_ctx", run_id, query, status),
        runId=run_id,
        queryHash=sha256_text(query),
        status=status,
        hits=[],
        degradedReason=degraded_reason,
    )


def context_pack_from_retrieval(
    *,
    run_id: str,
    result: MemoryRetrievalResult,
    max_context_chars: int,
) -> MemoryContextPack:
    used_chars = 0
    truncated = False
    hits: list[MemoryContextHit] = []
    for hit in result.hits:
        packed, used_chars, hit_truncated = _pack_hit(hit, used_chars, max_context_chars)
        if packed is None:
            truncated = True
            break
        truncated = truncated or hit_truncated
        hits.append(packed)
    status = "pass" if hits else ("denied" if result.status == "denied" else "empty")
    if result.status in {"degraded", "error"}:
        status = result.status
    return MemoryContextPack(
        packId=stable_id(
            "mem_ctx",
            run_id,
            result.query_hash,
            result.retrieval_fingerprint or "none",
        ),
        runId=run_id,
        queryHash=result.query_hash,
        status=status,
        hits=hits,
        retrievalFingerprint=result.retrieval_fingerprint,
        evidenceRef=result.evidence_ref,
        deniedScopes=result.denied_scopes,
        rawContentIncluded=False,
        truncated=truncated,
        degradedReason="MEMORY_RETRIEVAL_DENIED" if result.status == "denied" else None,
    )


def _pack_hit(
    hit: MemoryHit,
    used_chars: int,
    max_context_chars: int,
) -> tuple[MemoryContextHit | None, int, bool]:
    summary = (hit.content_summary or "").strip()
    if not summary:
        return None, used_chars, False
    remaining = max(0, max_context_chars - used_chars)
    if remaining <= 0:
        return None, used_chars, True
    truncated = len(summary) > remaining
    if truncated:
        summary = summary[: max(0, remaining - 3)].rstrip() + "..."
    return (
        MemoryContextHit(
            memoryId=hit.memory_id,
            scope=str(hit.scope),
            visibility=str(hit.visibility),
            redactedSummary=summary,
            contentHash=hit.content_hash,
            score=hit.score,
            createdAt=hit.created_at,
            policyTags=hit.policy_tags,
        ),
        used_chars + len(summary),
        truncated,
    )
