from __future__ import annotations

import json
from pathlib import Path

from imperaos.memory.semantic.models import (
    IndexRebuildResult,
    MemoryBackendBenchmarkReport,
    MemoryIndexRecord,
    MemoryRetrievalQualityReport,
    MemorySearchResult,
    MemorySemanticIndexSnapshot,
    SemanticIndexManifest,
    SemanticIndexStatus,
)

SCHEMAS = {
    "semantic_index_manifest.schema.json": SemanticIndexManifest,
    "semantic_index_record.schema.json": MemoryIndexRecord,
    "semantic_index_status.schema.json": SemanticIndexStatus,
    "semantic_search_result.schema.json": MemorySearchResult,
    "semantic_rebuild_result.schema.json": IndexRebuildResult,
    "retrieval_quality_report.schema.json": MemoryRetrievalQualityReport,
    "backend_benchmark_report.schema.json": MemoryBackendBenchmarkReport,
    "semantic_index_snapshot.schema.json": MemorySemanticIndexSnapshot,
}


def main() -> None:
    output_dir = Path("contracts/memory/semantic")
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename, model in SCHEMAS.items():
        (output_dir / filename).write_text(
            json.dumps(model.model_json_schema(by_alias=True), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
