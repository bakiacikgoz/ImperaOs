from __future__ import annotations

import json
from pathlib import Path

from imperaos.memory.semantic.embedding_provider import cosine_similarity
from imperaos.memory.semantic.index_manifest import (
    manifest_path,
    read_manifest,
    records_path,
    write_manifest,
)
from imperaos.memory.semantic.models import (
    MemoryIndexRecord,
    MemoryVectorHit,
    SemanticIndexManifest,
    SemanticIndexStatus,
)


class InMemoryFixtureSemanticBackend:
    backend_kind = "in_memory_fixture"

    def __init__(self, index_root: str | Path):
        self.index_root = Path(index_root)

    def status(self, workspace_id: str) -> SemanticIndexStatus:
        manifest = self.read_manifest(workspace_id)
        if manifest is None:
            return SemanticIndexStatus(
                status="rebuild_required",
                enabled=True,
                backendKind="in_memory_fixture",
                workspaceId=workspace_id,
                reasonCodes=("MEMORY_SEMANTIC_INDEX_MISSING",),
            )
        return SemanticIndexStatus(
            status=manifest.status,
            enabled=True,
            backendKind=manifest.backend_kind,
            embeddingProfileId=manifest.embedding_profile_id,
            workspaceId=workspace_id,
            recordCount=manifest.record_count,
            sourceStateVersion=manifest.source_state_version,
            indexStateVersion=manifest.index_state_version,
            rawPersistence=False,
            reasonCodes=manifest.reason_codes,
        )

    def read_manifest(self, workspace_id: str) -> SemanticIndexManifest | None:
        return read_manifest(manifest_path(self.index_root, workspace_id))

    def write_index(
        self,
        *,
        manifest: SemanticIndexManifest,
        records: tuple[MemoryIndexRecord, ...],
    ) -> None:
        write_manifest(manifest_path(self.index_root, manifest.workspace_id), manifest)
        record_file = records_path(self.index_root, manifest.workspace_id)
        record_file.parent.mkdir(parents=True, exist_ok=True)
        record_file.write_text(
            json.dumps(
                [record.model_dump(mode="json", by_alias=True) for record in records],
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

    def read_records(self, workspace_id: str) -> tuple[MemoryIndexRecord, ...]:
        path = records_path(self.index_root, workspace_id)
        if not path.exists():
            return ()
        payload = json.loads(path.read_text(encoding="utf-8"))
        return tuple(MemoryIndexRecord.model_validate(item) for item in payload)

    def search(
        self,
        *,
        workspace_id: str,
        query_vector: tuple[float, ...],
        allowed_memory_ids: set[str],
        limit: int,
    ) -> tuple[MemoryVectorHit, ...]:
        hits = []
        for record in self.read_records(workspace_id):
            if record.memory_id not in allowed_memory_ids:
                continue
            hits.append(
                MemoryVectorHit(
                    memoryId=record.memory_id,
                    score=cosine_similarity(query_vector, record.embedding),
                    backendKind="in_memory_fixture",
                )
            )
        return tuple(sorted(hits, key=lambda item: item.score, reverse=True)[:limit])
