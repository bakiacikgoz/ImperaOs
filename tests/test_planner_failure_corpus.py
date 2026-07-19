from __future__ import annotations

import json
from pathlib import Path

from imperaos.core.llm_ollama import StubLLM
from imperaos.core.planner import Planner
from imperaos.schemas.reason_codes import ReasonCode


def test_planner_failure_corpus_cases() -> None:
    path = Path("benchmarks/tasks/planner_failures/planner_failure_cases.jsonl")
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert rows

    for row in rows:
        planner = Planner(
            llm=StubLLM(responses=[row["raw_planner_output"]]),
            default_latency_budget_ms=1234,
        )
        run = planner.plan(str(row["input_text"]))
        expected_reason = ReasonCode(str(row["expected_reason_code"]))
        assert run.reason_code == expected_reason
