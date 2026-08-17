from __future__ import annotations

import json
import tempfile
from pathlib import Path

from imperaos.memory.semantic.evaluator import run_retrieval_quality_suite
from imperaos.memory.semantic.fixtures import build_semantic_fixture


def main() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        fixture = build_semantic_fixture(root)
        suite = root / "retrieval_quality.jsonl"
        suite.write_text(
            json.dumps(
                {
                    "query": "provider governance target evidence",
                    "workspaceId": "default",
                    "principalId": "operator-local",
                    "requestedScopes": ["personal:operator-local"],
                    "expectedMemoryIds": [fixture.expected_memory_id],
                    "hardNegativeMemoryIds": [fixture.hard_negative_memory_id],
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        report = run_retrieval_quality_suite(
            suite_path=suite,
            search_fn=fixture.service.search,
            output_path=Path("artifacts/memory-semantic/retrieval_quality_report.json"),
        )
        print(json.dumps(report.model_dump(mode="json", by_alias=True), indent=2, sort_keys=True))
        if report.status != "pass":
            raise SystemExit(1)


if __name__ == "__main__":
    main()
