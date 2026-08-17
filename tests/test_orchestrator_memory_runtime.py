from pathlib import Path

from imperaos.core.llm_ollama import StubLLM
from imperaos.core.orchestrator import Orchestrator
from imperaos.memory.authority import build_memory_authority, proposal_from_cli
from imperaos.memory.runtime_bridge import MemoryRuntimeBridge
from imperaos.router.rule_router import RuleRouter
from imperaos.runtime.config import RuntimeConfig
from imperaos.telemetry.tracer import Tracer


class UnusedPlanner:
    pass


def test_fast_chat_injects_runtime_memory_context(tmp_path: Path) -> None:
    config = RuntimeConfig.from_profile("balanced")
    config.memory.db_path = str(tmp_path / "memory.sqlite3")
    config.memory.v3_enabled = True
    config.memory.runtime.enabled = True
    authority = build_memory_authority(config, evidence_root=tmp_path / "evidence")
    authority.propose_write(
        proposal_from_cli(
            actor="session-1",
            scope="personal",
            owner_type="user",
            owner="session-1",
            visibility="private",
            text="User prefers minimalist dashboards.",
            role="operator",
            reason="test",
        )
    )
    llm = StubLLM(responses=["ok"])
    orchestrator = Orchestrator(
        planner=UnusedPlanner(),
        llm=llm,
        router=RuleRouter(),
        experts={},
        tracer=Tracer(),
        config=config,
        memory_runtime_bridge=MemoryRuntimeBridge(config=config, authority=authority),
    )

    result = orchestrator.process_fast_chat(
        "build dashboard",
        session_context={"session_id": "session-1"},
    )

    assert result.metrics["memory_context_hit_count"] == 1
    assert "User prefers minimalist dashboards." in llm.calls[0]["prompt"]
