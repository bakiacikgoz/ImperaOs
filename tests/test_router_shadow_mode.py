from __future__ import annotations

from imperaos.core.llm_ollama import StubLLM
from imperaos.core.orchestrator import Orchestrator
from imperaos.core.planner import PlannerRun
from imperaos.experts.base import ExpertBase
from imperaos.router.rule_router import RuleRouter
from imperaos.router.sltc_router import SLTCRouter
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
                task_type=TaskType.RESEARCH,
                intent="research",
                needs_expert=True,
                expert_candidates=[ExpertName.RESEARCH, ExpertName.PLAN],
                confidence=0.9,
                latency_budget_ms=1200,
                can_fallback=True,
                response_mode=ResponseMode.TOOL_FIRST,
            ),
            raw_output="{}",
            parse_failed=False,
            error=None,
            elapsed_ms=1,
            reason_code=ReasonCode.PLANNER_OK,
        )


class ResearchExpert(ExpertBase):
    name = ExpertName.RESEARCH

    def run(self, request: ExpertRequest) -> ExpertResult:
        del request
        return ExpertResult(
            expert_name=self.name,
            status=ExpertStatus.OK,
            confidence=0.8,
            payload={
                "summary": "ok",
                "evidence": [],
                "citations": [],
                "uncertainty": 0.2,
            },
            elapsed_ms=1,
        )


def test_orchestrator_records_shadow_router_metrics() -> None:
    cfg = RuntimeConfig.from_profile("balanced")
    orchestrator = Orchestrator(
        planner=StaticPlanner(),
        llm=StubLLM(responses=["final"]),
        router=RuleRouter(confidence_threshold=cfg.router_confidence_threshold),
        shadow_router=SLTCRouter(
            confidence_threshold=cfg.sltc.confidence_threshold,
            decay=cfg.sltc.decay,
            spike_threshold=cfg.sltc.spike_threshold,
        ),
        experts={ExpertName.RESEARCH.value: ResearchExpert()},
        tracer=Tracer(),
        config=cfg,
    )

    result = orchestrator.process("araştırma yap", use_router=True)

    assert result.metrics["router_shadow_enabled"] is True
    assert result.metrics["active_router_choice"] == "research_expert"
    assert result.metrics["shadow_router_choice"] in {"research_expert", "llm_only", "plan_expert"}
