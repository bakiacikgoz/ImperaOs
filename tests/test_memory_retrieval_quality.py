import json
from pathlib import Path

from imperaos.memory.semantic.evaluator import run_retrieval_quality_suite
from imperaos.memory.semantic.fixtures import build_semantic_fixture


def test_retrieval_quality_suite_passes_fixture(tmp_path: Path) -> None:
    fixture = build_semantic_fixture(tmp_path)
    suite = tmp_path / "suite.jsonl"
    suite.write_text(
        json.dumps(
            {
                "query": "provider governance target evidence",
                "workspaceId": "default",
                "principalId": "operator-local",
                "requestedScopes": ["personal:operator-local"],
                "expectedMemoryIds": [fixture.expected_memory_id],
                "hardNegativeMemoryIds": [fixture.hard_negative_memory_id],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = run_retrieval_quality_suite(
        suite_path=suite,
        search_fn=fixture.service.search,
        output_path=tmp_path / "report.json",
    )

    assert report.status == "pass"
    assert report.scope_violation_count == 0
    assert report.raw_leak_count == 0
