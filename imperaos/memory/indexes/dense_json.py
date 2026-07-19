from __future__ import annotations

import math
from collections.abc import Iterable

from imperaos.memory.models import (
    MemoryHit,
    MemoryIndexDeleteResult,
    MemoryIndexRebuildResult,
    MemoryIndexRecord,
    MemoryIndexStatus,
    MemoryIndexWriteResult,
    MemoryScopeFilter,
    MemoryVisibility,
    sha256_text,
)


class DenseJsonMemoryIndex:
    backend_name = "dense_json"

    def __init__(self) -> None:
        self._records: dict[str, MemoryIndexRecord] = {}

    def status(self) -> MemoryIndexStatus:
        return MemoryIndexStatus(
            backend=self.backend_name,
            status="pass",
            recordCount=len(self._records),
        )

    def add(self, records: list[MemoryIndexRecord]) -> MemoryIndexWriteResult:
        for record in records:
            self._records[record.memory_id] = record.model_copy(
                update={"vector": record.vector or deterministic_embedding(record.text)}
            )
        return MemoryIndexWriteResult(status="pass", indexedCount=len(records))

    def search(
        self,
        *,
        query: str,
        scope_filters: list[MemoryScopeFilter],
        visibility_filters: list[MemoryVisibility],
        limit: int,
    ) -> list[MemoryHit]:
        query_vec = deterministic_embedding(query)
        filters = {_scope_filter_key(item) for item in scope_filters}
        visibility = {str(item) for item in visibility_filters}
        scored: list[tuple[float, MemoryIndexRecord]] = []
        for record in self._records.values():
            key = (
                str(record.scope),
                str(record.owner_type),
                record.owner_id_hash,
                record.namespace,
            )
            if filters and key not in filters:
                continue
            if visibility and str(record.visibility) not in visibility:
                continue
            scored.append((_cosine(query_vec, record.vector or []), record))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            MemoryHit(
                memoryId=record.memory_id,
                scope=record.scope,
                visibility=record.visibility,
                ownerIdHash=record.owner_id_hash,
                contentSummary=record.text,
                contentHash=record.content_hash,
                score=max(0.0, score),
                createdAt="1970-01-01T00:00:00Z",
                policyTags=[],
            )
            for score, record in scored[:limit]
        ]

    def delete(self, memory_ids: list[str]) -> MemoryIndexDeleteResult:
        deleted = 0
        for memory_id in memory_ids:
            if self._records.pop(memory_id, None) is not None:
                deleted += 1
        return MemoryIndexDeleteResult(status="pass", deletedCount=deleted)

    def rebuild(self, records: Iterable[MemoryIndexRecord]) -> MemoryIndexRebuildResult:
        self._records = {}
        added = self.add(list(records))
        return MemoryIndexRebuildResult(
            status=added.status,
            indexedCount=added.indexed_count,
            blockingReasons=added.blocking_reasons,
        )


def deterministic_embedding(text: str, dim: int = 16) -> list[float]:
    digest = sha256_text(text)
    values = [int(digest[idx : idx + 2], 16) / 255.0 for idx in range(0, dim * 2, 2)]
    norm = math.sqrt(sum(value * value for value in values)) or 1.0
    return [value / norm for value in values]


def _scope_filter_key(item: MemoryScopeFilter | dict[str, object]) -> tuple[str, str, str, str]:
    if isinstance(item, dict):
        owner_type = item.get("owner_type", item.get("ownerType"))
        owner_hash = item.get("owner_id_hash", item.get("ownerIdHash"))
        return (
            str(item.get("scope")),
            str(owner_type),
            str(owner_hash),
            str(item.get("namespace", "default")),
        )
    return (str(item.scope), str(item.owner_type), item.owner_id_hash, item.namespace)


def _cosine(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=True))
