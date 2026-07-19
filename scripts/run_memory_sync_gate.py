from __future__ import annotations

import json
from pathlib import Path

from imperaos.memory.sync_importer import import_memory_sync_pack
from imperaos.memory.sync_pack import export_memory_sync_pack, verify_memory_sync_pack
from imperaos.runtime.config import RuntimeConfig


def main() -> None:
    config = RuntimeConfig.from_profile("balanced")
    config.memory.sync.enabled = True
    output = Path("artifacts/memory-sync/gate_sync_pack.json")
    pack = export_memory_sync_pack(
        config=config,
        output_path=output,
        source_environment="memory-sync-gate",
        limit=10,
    )
    verify = verify_memory_sync_pack(output)
    if verify.status != "pass":
        raise SystemExit(json.dumps(verify.model_dump(mode="json", by_alias=True)))
    report = import_memory_sync_pack(config=config, input_path=output, dry_run=True)
    if report.raw_content_included is not False:
        raise SystemExit("sync import report leaked raw content")
    print(
        json.dumps(
            {
                "status": "pass",
                "gate": "memory-sync",
                "packId": pack.manifest.pack_id,
                "records": pack.manifest.record_count,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
