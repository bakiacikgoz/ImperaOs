from pathlib import Path

from imperaos.core.llm_ollama import StubLLM
from imperaos.core.orchestrator import Orchestrator
from imperaos.memory.runtime_policy_fixtures import build_memory_runtime_policy_fixture
from imperaos.router.rule_router import RuleRouter
from imperaos.telemetry.tracer import Tracer


class UnusedPlanner:
    pass


def test_orchestrator_uses_policy_enforced_runtime_context(tmp_path: Path) -> None:
    fixture = build_memory_runtime_policy_fixture(tmp_path, profile="enterprise")
    llm = StubLLM(responses=["ok"])
    orchestrator = Orchestrator(
        planner=UnusedPlanner(),
        llm=llm,
        router=RuleRouter(),
        experts={},
        tracer=Tracer(),
        config=fixture.config,
        memory_runtime_bridge=fixture.bridge,
    )

    result = orchestrator.process_fast_chat(
        "hash only policy evidence",
        session_context={"actor_id": "operator-main"},
    )

    assert result.metrics["memory_context_status"] == "pass"
    assert "Operator prefers hash only policy evidence." in llm.calls[0]["prompt"]
