from __future__ import annotations

from imperaos.cli import _is_realtime_candidate
from imperaos.core.llm_ollama import StubLLM
from imperaos.core.orchestrator import Orchestrator
from imperaos.core.planner import PlannerRun
from imperaos.router.rule_router import RuleRouter
from imperaos.runtime.config import RuntimeConfig, RuntimeLimits
from imperaos.schemas.models import PlannerOutput, ResponseMode, TaskType
from imperaos.schemas.reason_codes import ReasonCode
from imperaos.telemetry.tracer import Tracer


class DummyPlanner:
    def plan(self, user_input: str) -> PlannerRun:
        del user_input
        return PlannerRun(
            output=PlannerOutput(
                task_type=TaskType.CHAT,
                intent="chat",
                needs_expert=False,
                expert_candidates=[],
                confidence=0.9,
                latency_budget_ms=1000,
                can_fallback=True,
                response_mode=ResponseMode.DIRECT,
            ),
            raw_output="{}",
            parse_failed=False,
            error=None,
            elapsed_ms=1,
            reason_code=ReasonCode.PLANNER_OK,
        )


def _config() -> RuntimeConfig:
    limits = RuntimeLimits(llm_timeout_ms=5000)
    return RuntimeConfig(
        model_name="fake",
        profile_name="test",
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


def test_realtime_candidate_classifier() -> None:
    assert _is_realtime_candidate("selam") is True
    assert _is_realtime_candidate("merhaba") is True
    assert _is_realtime_candidate("python testini düzelt") is False


def test_orchestrator_fast_chat_streams_tokens() -> None:
    llm = StubLLM(responses=["Merhaba hızlı yanıt"])
    orchestrator = Orchestrator(
        planner=DummyPlanner(),
        llm=llm,
        router=RuleRouter(confidence_threshold=0.6),
        experts={},
        tracer=Tracer(),
        config=_config(),
    )

    collected: list[str] = []
    result = orchestrator.process_fast_chat(
        "selam",
        session_context={"session_id": "s1"},
        stream=True,
        on_token=collected.append,
    )

    assert result.used_path == "llm_stream_fast"
    assert result.final_text == "Merhaba hızlı yanıt"
    assert "".join(collected) == result.final_text
