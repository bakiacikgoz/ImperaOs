from __future__ import annotations

from pathlib import Path

from imperaos.experts.code_expert import CodeExpert
from imperaos.experts.memory_plan_expert import MemoryPlanExpert
from imperaos.experts.research_expert import ResearchExpert
from imperaos.schemas.expert_payloads import (
    CodeExpertPayload,
    PlanExpertPayload,
    ResearchExpertPayload,
)
from imperaos.schemas.models import ExpertRequest, TaskType


def _request(task_type: TaskType, user_input: str) -> ExpertRequest:
    return ExpertRequest(
        request_id="req-1",
        task_type=task_type,
        intent="test",
        user_input=user_input,
        context={},
        latency_budget_ms=2000,
    )


def test_code_expert_payload_contract(tmp_path: Path) -> None:
    expert = CodeExpert(workspace=tmp_path)
    result = expert.run(_request(TaskType.CODE, "Python unique sort fonksiyonu ver"))

    payload = CodeExpertPayload.model_validate(result.payload)
    assert payload.issue_type in {
        "syntax",
        "runtime",
        "test",
        "import",
        "config",
        "refactor",
        "generic",
    }
    assert payload.patch_plan


def test_research_expert_payload_contract(tmp_path: Path) -> None:
    sample = tmp_path / "sample.md"
    sample.write_text("Fallback policy and router summary lines", encoding="utf-8")

    expert = ResearchExpert(workspace=tmp_path)
    result = expert.run(_request(TaskType.RESEARCH, "router summary"))

    payload = ResearchExpertPayload.model_validate(result.payload)
    assert payload.summary
    assert 0.0 <= payload.uncertainty <= 1.0


def test_plan_expert_payload_contract() -> None:
    expert = MemoryPlanExpert()
    result = expert.run(_request(TaskType.PLAN, "Önce analiz et. Sonra uygula. En son test et."))

    payload = PlanExpertPayload.model_validate(result.payload)
    assert len(payload.plan_steps) >= 2
    assert payload.state_summary
