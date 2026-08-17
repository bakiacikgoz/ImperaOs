from imperaos.core.llm_ollama import StubLLM
from imperaos.core.planner import Planner
from imperaos.schemas.models import TaskType


def test_planner_falls_back_when_json_invalid() -> None:
    llm = StubLLM(responses=["not-json"])
    planner = Planner(llm=llm, default_latency_budget_ms=1234)

    run = planner.plan("Bana bir plan yap")

    assert run.parse_failed is True
    assert run.output.task_type == TaskType.PLAN
    assert run.output.needs_expert is True
    assert run.output.latency_budget_ms == 1234


def test_planner_extracts_json_from_markdown_block() -> None:
    llm = StubLLM(
        responses=[
            "```json\n"
            "{\n"
            '  "task_type": "plan",\n'
            '  "intent": "weekly_plan",\n'
            '  "needs_expert": true,\n'
            '  "expert_candidates": ["plan_expert"],\n'
            '  "confidence": 0.8,\n'
            '  "latency_budget_ms": 2000,\n'
            '  "can_fallback": true,\n'
            '  "response_mode": "tool-first"\n'
            "}\n"
            "```"
        ]
    )
    planner = Planner(llm=llm, default_latency_budget_ms=1234)

    run = planner.plan("Haftalık plan çıkar")

    assert run.parse_failed is False
    assert run.output.task_type == TaskType.PLAN
    assert run.output.needs_expert is True
