from __future__ import annotations

from imperaos.core.llm_ollama import StubLLM
from imperaos.core.orchestrator import Orchestrator
from imperaos.core.planner import PlannerRun
from imperaos.experts.base import ExpertBase
from imperaos.router.rule_router import RuleRouter
from imperaos.runtime.config import RuntimeConfig
from imperaos.schemas.models import (
    ExpertName,
    ExpertRequest,
    ExpertResult,
    ExpertStatus,
    PlannerOutput,
    ResponseMode,
    TaskType,
)
from imperaos.schemas.reason_codes import ReasonCode
from imperaos.telemetry.tracer import Tracer


class StaticPlanner:
    def plan(self, user_input: str) -> PlannerRun:
        del user_input
        return PlannerRun(
            output=PlannerOutput(
                task_type=TaskType.CODE,
                intent="fix",
                needs_expert=True,
                expert_candidates=[ExpertName.CODE],
                confidence=0.95,
                latency_budget_ms=1000,
                can_fallback=True,
                response_mode=ResponseMode.TOOL_FIRST,
            ),
            raw_output="{}",
            parse_failed=False,
            error=None,
            elapsed_ms=1,
            reason_code=ReasonCode.PLANNER_OK,
        )


class InvalidPayloadCodeExpert(ExpertBase):
    name = ExpertName.CODE

    def run(self, request: ExpertRequest) -> ExpertResult:
        del request
        return ExpertResult(
            expert_name=self.name,
            status=ExpertStatus.OK,
            confidence=0.95,
            payload={"broken": True},
            elapsed_ms=1,
        )


def test_invalid_expert_payload_degrades_without_crash() -> None:
    cfg = RuntimeConfig.from_profile("lite")
    orchestrator = Orchestrator(
        planner=StaticPlanner(),
        llm=StubLLM(responses=["llm fallback"]),
        router=RuleRouter(confidence_threshold=0.6),
        experts={ExpertName.CODE.value: InvalidPayloadCodeExpert()},
        tracer=Tracer(),
        config=cfg,
    )

    result = orchestrator.process("kod düzelt", use_router=True)

    assert result.final_text
    assert result.used_path == "llm_only"
    assert any("expert_failed:code_expert:partial" in item for item in result.fallback_events)
    assert result.metrics["expert_schema_invalid"] is True
