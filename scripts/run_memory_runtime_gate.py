from __future__ import annotations

import json
from pathlib import Path

from imperaos.memory.runtime_bridge import RuntimeMemoryRequest, build_memory_runtime_bridge
from imperaos.runtime.config import RuntimeConfig


def main() -> None:
    config = RuntimeConfig.from_profile("balanced")
    bridge = build_memory_runtime_bridge(config)
    pack = bridge.retrieve_context(
        RuntimeMemoryRequest(
            run_id="memory-runtime-gate",
            query="operator preference",
            actor_id="gate:operator",
            requester_role="operator",
        )
    )
    payload = pack.model_dump(mode="json", by_alias=True)
    if payload.get("rawContentIncluded") is not False:
        raise SystemExit("runtime context pack leaked raw content")
    Path("artifacts/memory-runtime").mkdir(parents=True, exist_ok=True)
    Path("artifacts/memory-runtime/runtime_gate.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": "pass", "gate": "memory-runtime"}, sort_keys=True))


if __name__ == "__main__":
    main()
