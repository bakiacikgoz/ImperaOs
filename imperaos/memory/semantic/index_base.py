from __future__ import annotations

from typing import Protocol

from imperaos.memory.semantic.models import (
    MemoryIndexRecord,
    MemoryVectorHit,
    SemanticIndexManifest,
    SemanticIndexStatus,
)


class SemanticIndexBackend(Protocol):
    def status(self, workspace_id: str) -> SemanticIndexStatus: ...

    def read_manifest(self, workspace_id: str) -> SemanticIndexManifest | None: ...

    def write_index(
        self,
        *,
        manifest: SemanticIndexManifest,
        records: tuple[MemoryIndexRecord, ...],
    ) -> None: ...

    def read_records(self, workspace_id: str) -> tuple[MemoryIndexRecord, ...]: ...

    def search(
        self,
        *,
        workspace_id: str,
        query_vector: tuple[float, ...],
        allowed_memory_ids: set[str],
        limit: int,
    ) -> tuple[MemoryVectorHit, ...]: ...
