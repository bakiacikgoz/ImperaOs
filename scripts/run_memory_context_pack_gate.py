from __future__ import annotations

import json
from pathlib import Path

from imperaos.memory.context_pack import MemoryContextPack


def main() -> None:
    pack = MemoryContextPack(
        packId="mem_ctx_gate",
        runId="gate",
        queryHash="0" * 64,
        status="empty",
        rawContentIncluded=False,
    )
    payload = pack.model_dump(mode="json", by_alias=True)
    if payload.get("rawContentIncluded") is not False:
        raise SystemExit("MemoryContextPack rawContentIncluded must be false")
    Path("artifacts/memory-runtime").mkdir(parents=True, exist_ok=True)
    Path("artifacts/memory-runtime/context_pack_gate.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": "pass", "gate": "memory-context-pack"}, sort_keys=True))


if __name__ == "__main__":
    main()
