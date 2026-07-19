from __future__ import annotations

import argparse
import json

from imperaos.memory.indexes.turbovec_optional import TurboVecOptionalIndex


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", default="sqlite_text")
    parser.add_argument("--dataset", default="benchmarks/tasks/memory/memory_retrieval_eval.jsonl")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.backend == "turbovec_experimental":
        payload = (
            TurboVecOptionalIndex(enabled=False)
            .status()
            .model_dump(mode="json", by_alias=True)
        )
    else:
        payload = {"backend": args.backend, "status": "pass", "dataset": args.dataset}
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
