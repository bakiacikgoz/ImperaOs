from pathlib import Path

from imperaos.memory.runtime_policy_fixtures import build_memory_runtime_policy_fixture
from imperaos.team.memory_scope import read_scoped_memory, write_scoped_memory


def test_team_memory_policy_enforced_read_and_write_paths(tmp_path: Path) -> None:
    fixture = build_memory_runtime_policy_fixture(tmp_path, profile="enterprise")

    read = read_scoped_memory(
        memory_manager=None,
        query="provider governance",
        scope="team",
        team_id="team-alpha",
        case_id="case-42",
        job_id="job-42",
        visibility="team",
        memory_runtime_bridge=fixture.bridge,
        producer_agent_id="agent-alpha",
    )
    write = write_scoped_memory(
        memory_manager=None,
        session_id="team-policy-session",
        task_type="implementation",
        user_input="remember team note",
        assistant_output="Team alpha memory writes require proposal.",
        scope="team",
        team_id="team-alpha",
        case_id="case-42",
        job_id="job-42",
        producer_agent_id="agent-alpha",
        producer_role="agent",
        visibility="team",
        memory_runtime_bridge=fixture.bridge,
    )

    assert read["count"] >= 1
    assert write["reason"] == "proposal_only"
