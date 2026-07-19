from __future__ import annotations

import argparse
import json
from pathlib import Path

from imperaos.memory.evaluation import run_memory_retrieval_eval
from imperaos.runtime.config import RuntimeConfig


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="enterprise")
    parser.add_argument("--suite", default="benchmarks/tasks/memory/memory_retrieval_eval.jsonl")
    parser.add_argument("--output", default="artifacts/memory-governance/memory_eval_report.json")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    payload = run_memory_retrieval_eval(
        config=RuntimeConfig.from_profile(args.profile),
        suite=args.suite,
    )
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
