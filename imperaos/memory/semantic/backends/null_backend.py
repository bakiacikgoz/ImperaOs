from __future__ import annotations

from imperaos.memory.semantic.models import (
    MemoryIndexRecord,
    MemoryVectorHit,
    SemanticIndexManifest,
    SemanticIndexStatus,
)


class NullSemanticBackend:
    backend_kind = "null"

    def status(self, workspace_id: str) -> SemanticIndexStatus:
        return SemanticIndexStatus(
            status="available_disabled",
            enabled=False,
            backendKind="null",
            workspaceId=workspace_id,
            reasonCodes=("MEMORY_SEMANTIC_BACKEND_DISABLED",),
        )

    def read_manifest(self, workspace_id: str) -> SemanticIndexManifest | None:
        return None

    def write_index(
        self,
        *,
        manifest: SemanticIndexManifest,
        records: tuple[MemoryIndexRecord, ...],
    ) -> None:
        _ = manifest, records

    def read_records(self, workspace_id: str) -> tuple[MemoryIndexRecord, ...]:
        _ = workspace_id
        return ()

    def search(
        self,
        *,
        workspace_id: str,
        query_vector: tuple[float, ...],
        allowed_memory_ids: set[str],
        limit: int,
    ) -> tuple[MemoryVectorHit, ...]:
        _ = workspace_id, query_vector, allowed_memory_ids, limit
        return ()
