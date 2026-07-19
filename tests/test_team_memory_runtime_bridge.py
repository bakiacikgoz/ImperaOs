from pathlib import Path

from imperaos.memory.authority import build_memory_authority, proposal_from_cli
from imperaos.memory.runtime_bridge import MemoryRuntimeBridge
from imperaos.runtime.config import RuntimeConfig
from imperaos.team.memory_scope import read_scoped_memory


def test_team_read_scoped_memory_uses_runtime_bridge(tmp_path: Path) -> None:
    config = RuntimeConfig.from_profile("balanced")
    config.memory.db_path = str(tmp_path / "memory.sqlite3")
    config.memory.v3_enabled = True
    config.memory.runtime.enabled = True
    authority = build_memory_authority(config, evidence_root=tmp_path / "evidence")
    authority.propose_write(
        proposal_from_cli(
            actor="agent-a",
            scope="team",
            owner_type="team",
            owner="team-a",
            visibility="team",
            text="Team uses ADR files for architecture decisions.",
            role="Code Expert",
            reason="test",
        )
    )

    result = read_scoped_memory(
        memory_manager=None,
        query="architecture decisions",
        scope="team",
        team_id="team-a",
        case_id="case-a",
        job_id="job-a",
        visibility="team",
        memory_runtime_bridge=MemoryRuntimeBridge(config=config, authority=authority),
        producer_agent_id="agent-a",
    )

    assert result["count"] == 1
    assert "ADR files" in result["snippets"][0]
