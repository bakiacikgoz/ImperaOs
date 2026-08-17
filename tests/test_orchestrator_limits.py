from __future__ import annotations

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
    def __init__(self, output: PlannerOutput):
        self.output = output

    def plan(self, user_input: str) -> PlannerRun:
        del user_input
        return PlannerRun(
            output=self.output,
            raw_output="{}",
            parse_failed=False,
            error=None,
            elapsed_ms=1,
            reason_code=ReasonCode.PLANNER_OK,
        )


class HeavyToolExpert(ExpertBase):
    name = ExpertName.CODE
    estimated_tool_calls_per_run = 5

    def run(self, request: ExpertRequest) -> ExpertResult:
        del request
        return ExpertResult(
            expert_name=self.name,
            status=ExpertStatus.OK,
            confidence=0.9,
            payload={"ok": True},
            elapsed_ms=1,
        )


def _config(max_tool_calls: int = 1, max_recursion_depth: int = 2) -> RuntimeConfig:
    limits = RuntimeLimits(
        expert_timeout_ms=200,
        max_retries=0,
        circuit_breaker_threshold=3,
        circuit_breaker_cooldown_s=60,
        llm_timeout_ms=2000,
        max_tool_calls=max_tool_calls,
        max_recursion_depth=max_recursion_depth,
    )
    return RuntimeConfig(
        model_name="fake",
        profile_name="test",
        llm_provider="auto",
        fallback_provider="transformers",
        fallback_enabled=True,
        planner_temperature=0.0,
        answer_temperature=0.0,
        router_confidence_threshold=0.6,
        latency_budget_ms=1000,
        debug_mode=False,
        privacy_mode=True,
        enable_persistent_memory=False,
        web_enabled=False,
        trace_dir=".imperaos/test-traces",
        limits=limits,
    )


def test_orchestrator_enforces_tool_budget() -> None:
    planner_output = PlannerOutput(
        task_type=TaskType.CODE,
        intent="code",
        needs_expert=True,
        expert_candidates=[ExpertName.CODE],
        confidence=0.95,
        latency_budget_ms=1000,
        can_fallback=True,
        response_mode=ResponseMode.TOOL_FIRST,
    )
    orchestrator = Orchestrator(
        planner=StaticPlanner(planner_output),
        llm=StubLLM(responses=["fallback"]),
        router=RuleRouter(confidence_threshold=0.6),
        experts={ExpertName.CODE.value: HeavyToolExpert()},
        tracer=Tracer(),
        config=_config(max_tool_calls=1),
    )

    result = orchestrator.process("fix code", use_router=True)

    assert result.used_path == "llm_only"
    assert any("expert_failed:code_expert:skipped" in item for item in result.fallback_events)


def test_orchestrator_enforces_recursion_depth() -> None:
    planner_output = PlannerOutput(
        task_type=TaskType.CHAT,
        intent="chat",
        needs_expert=False,
        expert_candidates=[],
        confidence=0.5,
        latency_budget_ms=1000,
        can_fallback=True,
        response_mode=ResponseMode.DIRECT,
    )
    orchestrator = Orchestrator(
        planner=StaticPlanner(planner_output),
        llm=StubLLM(responses=["unused"]),
        router=RuleRouter(confidence_threshold=0.6),
        experts={},
        tracer=Tracer(),
        config=_config(max_recursion_depth=2),
    )

    result = orchestrator.process("hello", session_context={"_depth": "2"}, use_router=True)

    assert result.metrics["router_reason_code"] == ReasonCode.RECURSION_DEPTH_EXCEEDED.value
