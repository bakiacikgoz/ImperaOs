from pydantic import ValidationError

from imperaos.schemas.models import PlannerOutput, ResponseMode, TaskType


def test_planner_output_validates() -> None:
    payload = PlannerOutput(
        task_type=TaskType.CHAT,
        intent="basic_chat",
        needs_expert=False,
        expert_candidates=[],
        confidence=0.8,
        latency_budget_ms=2000,
        can_fallback=True,
        response_mode=ResponseMode.DIRECT,
    )
    assert payload.task_type == TaskType.CHAT


def test_planner_output_rejects_invalid_confidence() -> None:
    try:
        PlannerOutput(
            task_type=TaskType.CHAT,
            intent="bad",
            needs_expert=False,
            expert_candidates=[],
            confidence=1.5,
            latency_budget_ms=1000,
            can_fallback=True,
            response_mode=ResponseMode.DIRECT,
        )
    except ValidationError:
        return
    raise AssertionError("ValidationError expected")
