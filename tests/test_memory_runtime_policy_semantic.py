from pathlib import Path

from imperaos.memory.runtime_bridge import RuntimeMemoryRequest
from imperaos.memory.runtime_policy_fixtures import build_memory_runtime_policy_fixture


def test_semantic_runtime_enforced_returns_only_allowed_prefiltered_hits(tmp_path: Path) -> None:
    fixture = build_memory_runtime_policy_fixture(
        tmp_path,
        profile="enterprise",
        semantic_mode="enforced",
        semantic_enabled=True,
    )
    pack = fixture.bridge.retrieve_context(
        RuntimeMemoryRequest(
            run_id="run-semantic-enforced",
            query="runtime policy evidence",
            actor_id="agent-alpha",
            requester_role="agent",
            agent_id="agent-alpha",
            team_id="team-alpha",
            workspace_id="workspace-main",
        )
    )

    assert pack.status == "pass"
    assert pack.hits
    assert all(hit.source_kind == "semantic_runtime" for hit in pack.hits)
    assert all(hit.scope in {"agent:agent-alpha", "team:team-alpha"} for hit in pack.hits)
