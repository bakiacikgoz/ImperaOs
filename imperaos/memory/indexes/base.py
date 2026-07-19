from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

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


class SemanticMemoryIndex(Protocol):
    backend_name: str

    def status(self) -> MemoryIndexStatus: ...

    def add(self, records: list[MemoryIndexRecord]) -> MemoryIndexWriteResult: ...

    def search(
        self,
        *,
        query: str,
        scope_filters: list[MemoryScopeFilter],
        visibility_filters: list[MemoryVisibility],
        limit: int,
    ) -> list[MemoryHit]: ...

    def delete(self, memory_ids: list[str]) -> MemoryIndexDeleteResult: ...

    def rebuild(self, records: Iterable[MemoryIndexRecord]) -> MemoryIndexRebuildResult: ...
