from pathlib import Path

from imperaos.memory.principal_resolver import (
    AgentMemoryPrincipalResolver,
    PrincipalResolutionInput,
    parse_memory_scope,
)
from imperaos.memory.runtime_policy_fixtures import build_memory_runtime_policy_fixture


def test_principal_resolver_derives_team_agent_scopes(tmp_path: Path) -> None:
    fixture = build_memory_runtime_policy_fixture(tmp_path, profile="enterprise")
    resolved = AgentMemoryPrincipalResolver(
        config=fixture.config,
        workspace_authority=fixture.bridge.workspace_authority,
    ).resolve(
        PrincipalResolutionInput(
            actor_id="agent-alpha",
            requester_role="agent",
            agent_id="agent-alpha",
            team_id="team-alpha",
        )
    )

    assert resolved.status == "pass"
    assert resolved.principal_id == "agent-alpha"
    assert "team:team-alpha" in resolved.allowed_scopes


def test_principal_resolver_strict_denies_missing_membership(tmp_path: Path) -> None:
    fixture = build_memory_runtime_policy_fixture(tmp_path, profile="enterprise")
    resolved = AgentMemoryPrincipalResolver(
        config=fixture.config,
        workspace_authority=fixture.bridge.workspace_authority,
    ).resolve(PrincipalResolutionInput(actor_id="unknown-user", requester_role="operator"))

    assert resolved.status == "denied"
    assert "MEMORY_WORKSPACE_MEMBERSHIP_DENIED" in resolved.reason_codes


def test_parse_memory_scope_requires_type_and_id() -> None:
    assert parse_memory_scope("case:case-42").scope_type == "case"
