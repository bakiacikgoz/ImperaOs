from pathlib import Path

from imperaos.memory.workspace_authority import build_workspace_memory_authority
from imperaos.memory.workspace_models import (
    MemoryPrincipal,
    MemoryScopeAclRule,
    MemoryWorkspace,
    MemoryWorkspaceMembership,
    WorkspaceMemoryQueryRequest,
    WorkspaceMemoryWriteRequest,
)
from imperaos.runtime.config import RuntimeConfig


def _authority(tmp_path: Path):
    config = RuntimeConfig.from_profile("balanced")
    config.memory.workspace_authority.enabled = True
    config.memory.workspace_authority.db_path = str(tmp_path / "workspace_memory.sqlite3")
    authority = build_workspace_memory_authority(config, evidence_root=tmp_path / "evidence")
    authority.store.upsert_principal(
        MemoryPrincipal(principalId="operator-local", principalType="operator", displayName="OP")
    )
    authority.store.create_workspace(
        MemoryWorkspace(
            workspaceId="default",
            displayName="Default",
            ownerPrincipalId="operator-local",
        )
    )
    authority.store.grant_membership(
        MemoryWorkspaceMembership(
            membershipId="member-operator-local",
            workspaceId="default",
            principalId="operator-local",
            roles=("owner",),
            grantedBy="operator-local",
        )
    )
    return authority


def test_workspace_authority_commits_and_queries_personal_memory(tmp_path: Path) -> None:
    authority = _authority(tmp_path)

    write = authority.propose_or_write(
        WorkspaceMemoryWriteRequest(
            workspaceId="default",
            principalId="operator-local",
            scopeType="personal",
            scopeId="operator-local",
            summary="Remember the release checklist is owned by platform.",
            memoryTarget="release-checklist",
        )
    )
    assert write.status == "committed"
    assert write.raw_content_included is False

    query = authority.query(
        WorkspaceMemoryQueryRequest(
            workspaceId="default",
            principalId="operator-local",
            scopeType="personal",
            scopeId="operator-local",
            query="release",
        )
    )
    assert query.status == "pass"
    assert query.records[0].memory_target == "release-checklist"
    assert query.raw_content_included is False


def test_workspace_authority_blocks_secret_like_memory(tmp_path: Path) -> None:
    authority = _authority(tmp_path)

    write = authority.propose_or_write(
        WorkspaceMemoryWriteRequest(
            workspaceId="default",
            principalId="operator-local",
            scopeType="personal",
            scopeId="operator-local",
            summary="api_key = sk-testsecret123456789",
        )
    )

    assert write.status == "denied"
    assert "MEMORY_CLASSIFICATION_SECRET_LIKE_DENIED" in write.blocking_reasons


def test_workspace_authority_routes_team_write_to_proposal(tmp_path: Path) -> None:
    authority = _authority(tmp_path)
    authority.store.upsert_principal(
        MemoryPrincipal(principalId="agent-local", principalType="agent", displayName="Agent")
    )
    authority.store.grant_membership(
        MemoryWorkspaceMembership(
            membershipId="member-agent-local",
            workspaceId="default",
            principalId="agent-local",
            roles=("agent",),
            grantedBy="operator-local",
        )
    )
    authority.store.upsert_acl_rule(
        MemoryScopeAclRule(
            aclId="acl-agent-team-write",
            workspaceId="default",
            scopeType="team",
            scopeId="platform",
            principalId="agent-local",
            permissions=("memory.write.team",),
            effect="allow",
            reason="team write proposal",
        )
    )

    write = authority.propose_or_write(
        WorkspaceMemoryWriteRequest(
            workspaceId="default",
            principalId="agent-local",
            scopeType="team",
            scopeId="platform",
            summary="Platform team wants weekly evidence exports.",
        )
    )

    assert write.status == "proposal_only"
    assert write.proposal_id is not None
