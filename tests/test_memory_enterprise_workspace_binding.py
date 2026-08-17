from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from imperaos.control_plane.enterprise_workspace import (
    EnterpriseOrganization,
    EnterprisePrincipal,
    EnterpriseWorkspace,
    EnterpriseWorkspaceMembership,
)
from imperaos.control_plane.enterprise_workspace_store import EnterpriseWorkspaceStore
from imperaos.memory.principal_resolver import (
    AgentMemoryPrincipalResolver,
    PrincipalResolutionInput,
)
from imperaos.runtime.config import RuntimeConfig

NOW = datetime(2026, 6, 19, tzinfo=UTC)


def test_memory_principal_resolver_uses_enterprise_workspace_membership(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_enterprise_membership(tmp_path, workspace_id="pilot-workspace")
    config = RuntimeConfig.from_profile("enterprise")
    config.memory.workspace_authority.enabled = True

    resolved = AgentMemoryPrincipalResolver(config=config).resolve(
        PrincipalResolutionInput(
            actor_id="alice",
            requester_role="operator",
            principal_id="principal-admin",
            workspace_id="pilot-workspace",
            requested_scopes=("personal:principal-admin",),
        )
    )

    assert resolved.status == "pass"
    assert resolved.roles == ("operator",)
    assert resolved.raw_content_included is False


def test_memory_principal_resolver_denies_cross_workspace_without_membership(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_enterprise_membership(tmp_path, workspace_id="workspace-a")
    config = RuntimeConfig.from_profile("enterprise")
    config.memory.workspace_authority.enabled = True

    resolved = AgentMemoryPrincipalResolver(config=config).resolve(
        PrincipalResolutionInput(
            actor_id="alice",
            requester_role="operator",
            principal_id="principal-admin",
            workspace_id="workspace-b",
            requested_scopes=("personal:principal-admin",),
        )
    )

    assert resolved.status == "denied"
    assert "MEMORY_WORKSPACE_MEMBERSHIP_DENIED" in resolved.reason_codes


def _write_enterprise_membership(root: Path, *, workspace_id: str) -> None:
    store = EnterpriseWorkspaceStore(root / ".imperaos" / "control-plane")
    store.write_organization(
        EnterpriseOrganization(
            organizationId="local-org",
            displayName="Local Org",
            status="active",
            createdByPrincipalId="principal-admin",
            createdAtUtc=NOW,
            updatedAtUtc=NOW,
        )
    )
    store.write_workspace(
        EnterpriseWorkspace(
            workspaceId=workspace_id,
            organizationId="local-org",
            displayName="Pilot Workspace",
            environment="pilot",
            status="active",
            defaultPolicyPackId=None,
            memoryAuthorityMode="local_authority",
            providerPolicyProfile="enterprise",
            evidenceMode="hash_only",
            createdByPrincipalId="principal-admin",
            createdAtUtc=NOW,
            updatedAtUtc=NOW,
        )
    )
    store.write_principal(
        EnterprisePrincipal(
            principalId="principal-admin",
            principalType="human_user",
            displayName="Admin",
            status="active",
            externalSubjectRefHash="a" * 64,
            issuerHash="b" * 64,
            createdAtUtc=NOW,
        )
    )
    store.write_membership(
        EnterpriseWorkspaceMembership(
            membershipId=f"membership-{workspace_id}",
            workspaceId=workspace_id,
            principalId="principal-admin",
            roles=("operator",),
            status="active",
            grantedByPrincipalId="principal-admin",
            grantedAtUtc=NOW,
        )
    )
