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
                intent="code",
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


class CodeExpert(ExpertBase):
    name = ExpertName.CODE

    def run(self, request: ExpertRequest) -> ExpertResult:
        del request
        return ExpertResult(
            expert_name=self.name,
            status=ExpertStatus.OK,
            confidence=0.8,
            payload={
                "issue_type": "runtime",
                "strategy": "minimal_patch",
                "patch_plan": ["a"],
                "candidate_snippet": None,
                "verification": {
                    "parse_ok": True,
                    "lint_ok": True,
                    "tests_ok": None,
                    "details": {},
                },
                "notes": "ok",
            },
            elapsed_ms=1,
        )


def test_fast_path_regret_flag_after_followup_expert_need() -> None:
    cfg = RuntimeConfig.from_profile("balanced").model_copy(
        update={"fast_path_regret_window": 2, "fast_path_regret_threshold": 0.1}
    )
    orchestrator = Orchestrator(
        planner=StaticPlanner(),
        llm=StubLLM(responses=["hızlı", "final"]),
        router=RuleRouter(confidence_threshold=cfg.router_confidence_threshold),
        experts={ExpertName.CODE.value: CodeExpert()},
        tracer=Tracer(),
        config=cfg,
    )

    session = {"session_id": "s1"}
    fast = orchestrator.process_fast_chat("selam", session_context=session, stream=False)
    normal = orchestrator.process("kodu düzelt", session_context=session, use_router=True)

    assert fast.metrics["fast_path_taken"] is True
    assert normal.metrics["expert_needed_after_fast_path"] is True
    assert normal.metrics["fast_path_regret_flag"] is True
    assert normal.metrics["followup_correction_rate"] >= 1.0
