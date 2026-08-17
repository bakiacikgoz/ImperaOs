from __future__ import annotations

import json
from pathlib import Path

from imperaos.memory.context_pack import MemoryContextPack
from imperaos.memory.models import (
    MemoryAuthoritySnapshot,
    MemoryEvidenceEvent,
    MemoryIndexStatus,
    MemoryPolicyDecision,
    MemoryRecordV3,
    MemoryRetrievalResult,
    MemoryWriteProposal,
)
from imperaos.memory.runtime_snapshot import MemoryRuntimeSnapshot
from imperaos.memory.sync_conflicts import MemorySyncConflict
from imperaos.memory.sync_importer import MemorySyncImportReport
from imperaos.memory.sync_pack import MemorySyncPackManifest

SCHEMAS = {
    "memory_record_v3.schema.json": MemoryRecordV3,
    "memory_write_proposal.schema.json": MemoryWriteProposal,
    "memory_policy_decision.schema.json": MemoryPolicyDecision,
    "memory_retrieval_result.schema.json": MemoryRetrievalResult,
    "memory_evidence_event.schema.json": MemoryEvidenceEvent,
    "memory_index_status.schema.json": MemoryIndexStatus,
    "memory_authority_snapshot.schema.json": MemoryAuthoritySnapshot,
    "memory_context_pack.schema.json": MemoryContextPack,
    "memory_runtime_event.schema.json": MemoryRuntimeSnapshot,
    "memory_sync_pack_manifest.schema.json": MemorySyncPackManifest,
    "memory_sync_import_report.schema.json": MemorySyncImportReport,
    "memory_sync_conflict.schema.json": MemorySyncConflict,
}


def main() -> None:
    output_dir = Path("contracts/memory")
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename, model in SCHEMAS.items():
        schema = model.model_json_schema(by_alias=True)
        (output_dir / filename).write_text(
            json.dumps(schema, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
