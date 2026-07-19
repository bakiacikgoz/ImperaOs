from __future__ import annotations

import json
from pathlib import Path

from imperaos.memory.indexes.dense_json import DenseJsonMemoryIndex
from imperaos.memory.indexes.turbovec_optional import TurboVecOptionalIndex
from imperaos.memory.models import MemoryIndexRecord, hash_identity, sha256_text


def main() -> None:
    owner = hash_identity("index-gate")
    text = "minimalist black and white interface preference"
    record = MemoryIndexRecord(
        memoryId="mem_index_gate_001",
        scope="personal",
        ownerType="user",
        ownerIdHash=owner,
        visibility="private",
        text=text,
        contentHash=sha256_text(text),
    )
    dense = DenseJsonMemoryIndex()
    dense.add([record])
    hits = dense.search(
        query="black interface",
        scope_filters=[
            {"scope": "personal", "ownerType": "user", "ownerIdHash": owner, "namespace": "default"}
        ],
        visibility_filters=["private"],
        limit=3,
    )
    turbo = TurboVecOptionalIndex(enabled=False).status()
    status = "pass" if hits and turbo.status == "disabled" else "fail"
    payload = {
        "status": status,
        "denseJsonHits": len(hits),
        "turbovec": turbo.model_dump(mode="json", by_alias=True),
    }
    out = Path("artifacts/memory-governance/memory_index_gate.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, indent=2, sort_keys=True))
    if status != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
