from __future__ import annotations

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
)
from imperaos.memory.store_v3 import MemoryStoreV3


class SqliteTextMemoryIndex:
    backend_name = "sqlite_text"

    def __init__(self, *, store: MemoryStoreV3):
        self.store = store

    def status(self) -> MemoryIndexStatus:
        stats = self.store.stats()
        return MemoryIndexStatus(
            backend=self.backend_name,
            status="pass",
            recordCount=int(stats["records"]["active"]),
        )

    def add(self, records: list[MemoryIndexRecord]) -> MemoryIndexWriteResult:
        return MemoryIndexWriteResult(status="pass", indexedCount=len(records))

    def search(
        self,
        *,
        query: str,
        scope_filters: list[MemoryScopeFilter],
        visibility_filters: list[MemoryVisibility],
        limit: int,
    ) -> list[MemoryHit]:
        records = self.store.search_records(
            query=query,
            scope_filters=scope_filters,
            visibility_filters=visibility_filters,
            limit=limit,
        )
        return [
            MemoryHit(
                memoryId=record.memory_id,
                scope=record.scope,
                visibility=record.visibility,
                ownerIdHash=record.owner_id_hash,
                contentSummary=record.content_summary,
                contentHash=record.content_hash,
                score=max(0.01, record.salience),
                createdAt=record.created_at,
                policyTags=record.policy_tags,
            )
            for record in records
        ]

    def delete(self, memory_ids: list[str]) -> MemoryIndexDeleteResult:
        return MemoryIndexDeleteResult(status="pass", deletedCount=len(memory_ids))

    def rebuild(self, records: Iterable[MemoryIndexRecord]) -> MemoryIndexRebuildResult:
        count = sum(1 for _ in records)
        return MemoryIndexRebuildResult(status="pass", indexedCount=count)
