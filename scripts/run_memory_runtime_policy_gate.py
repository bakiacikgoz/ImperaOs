from __future__ import annotations

import json
from pathlib import Path

from imperaos.memory.runtime_policy_evaluator import run_policy_evaluation


def main() -> None:
    output = Path("artifacts/memory-runtime-policy/gate.json")
    report = run_policy_evaluation(
        suite_path=Path("benchmarks/tasks/memory/runtime_policy_cases.jsonl"),
        output_path=output,
        profile="enterprise",
    )
    payload = report.model_dump(mode="json", by_alias=True)
    print(json.dumps(payload, indent=2, sort_keys=True))
    if report.status != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
