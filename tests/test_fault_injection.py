from __future__ import annotations

import time

from imperaos.core.llm_ollama import StubLLM
from imperaos.core.orchestrator import Orchestrator
from imperaos.core.planner import PlannerRun
from imperaos.experts.base import ExpertBase
from imperaos.router.rule_router import RuleRouter
from imperaos.runtime.config import RuntimeConfig, RuntimeLimits
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
                task_type=TaskType.RESEARCH,
                intent="research",
                needs_expert=True,
                expert_candidates=[ExpertName.RESEARCH, ExpertName.PLAN],
                confidence=0.9,
                latency_budget_ms=500,
                can_fallback=True,
                response_mode=ResponseMode.TOOL_FIRST,
            ),
            raw_output="{}",
            parse_failed=False,
            error=None,
            elapsed_ms=1,
            reason_code=ReasonCode.PLANNER_OK,
        )


class SlowExpert(ExpertBase):
    name = ExpertName.RESEARCH

    def run(self, request: ExpertRequest) -> ExpertResult:
        del request
        time.sleep(0.05)
        return ExpertResult(
            expert_name=self.name,
            status=ExpertStatus.OK,
            confidence=0.5,
            payload={"summary": "slow"},
            elapsed_ms=50,
        )


class PlanExpert(ExpertBase):
    name = ExpertName.PLAN

    def run(self, request: ExpertRequest) -> ExpertResult:
        del request
        return ExpertResult(
            expert_name=self.name,
            status=ExpertStatus.OK,
            confidence=0.8,
            payload={
                "plan_steps": ["a", "b"],
                "state_summary": "ok",
                "memory_candidates": [],
                "confidence": 0.8,
            },
            elapsed_ms=1,
        )


def test_fault_injection_timeout_falls_back_to_secondary_expert() -> None:
    cfg = RuntimeConfig.from_profile("lite").model_copy(
        update={
            "limits": RuntimeLimits(
                expert_timeout_ms=10,
                max_retries=0,
                circuit_breaker_threshold=3,
                circuit_breaker_cooldown_s=60,
                llm_timeout_ms=2000,
                max_tool_calls=4,
                max_recursion_depth=2,
            )
        }
    )
    orchestrator = Orchestrator(
        planner=StaticPlanner(),
        llm=StubLLM(responses=["final"]),
        router=RuleRouter(confidence_threshold=0.6),
        experts={
            ExpertName.RESEARCH.value: SlowExpert(),
            ExpertName.PLAN.value: PlanExpert(),
        },
        tracer=Tracer(),
        config=cfg,
    )

    result = orchestrator.process("araştır", use_router=True)

    assert any("fallback_expert_used:plan_expert" in item for item in result.fallback_events)
