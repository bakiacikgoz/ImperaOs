from pathlib import Path

from imperaos.memory.authority import build_memory_authority, proposal_from_cli
from imperaos.memory.runtime_bridge import MemoryRuntimeBridge, RuntimeMemoryRequest
from imperaos.runtime.config import RuntimeConfig


def _config(tmp_path: Path) -> RuntimeConfig:
    config = RuntimeConfig.from_profile("balanced")
    config.memory.db_path = str(tmp_path / "memory.sqlite3")
    return config


def test_runtime_bridge_disabled_returns_disabled_pack(tmp_path: Path) -> None:
    config = _config(tmp_path)
    bridge = MemoryRuntimeBridge(
        config=config,
        authority=build_memory_authority(config, evidence_root=tmp_path / "evidence"),
    )

    pack = bridge.retrieve_context(
        RuntimeMemoryRequest(
            run_id="run-1",
            query="preference",
            actor_id="operator",
            requester_role="operator",
        )
    )

    assert pack.status == "disabled"
    assert pack.raw_content_included is False


def test_runtime_bridge_retrieves_redacted_context(tmp_path: Path) -> None:
    config = _config(tmp_path)
    config.memory.v3_enabled = True
    config.memory.runtime.enabled = True
    authority = build_memory_authority(config, evidence_root=tmp_path / "evidence")
    authority.propose_write(
        proposal_from_cli(
            actor="operator",
            scope="personal",
            owner_type="user",
            owner="operator",
            visibility="private",
            text="User prefers concise release notes.",
            role="operator",
            reason="test",
        )
    )
    bridge = MemoryRuntimeBridge(config=config, authority=authority)

    pack = bridge.retrieve_context(
        RuntimeMemoryRequest(
            run_id="run-1",
            query="release notes",
            actor_id="operator",
            requester_role="operator",
        )
    )

    assert pack.status == "pass"
    assert pack.hits[0].redacted_summary == "User prefers concise release notes."
    assert pack.raw_content_included is False
