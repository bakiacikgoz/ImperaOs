from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from imperaos.control_plane.enterprise_workspace import (
    EnterpriseOrganization,
    EnterpriseWorkspace,
    EnterpriseWorkspaceMembership,
)
from imperaos.control_plane.enterprise_workspace_store import EnterpriseWorkspaceStore

NOW = datetime(2026, 6, 19, tzinfo=UTC)


def _organization(display_name: str = "Local Org") -> EnterpriseOrganization:
    return EnterpriseOrganization(
        organizationId="local-org",
        displayName=display_name,
        status="active",
        createdByPrincipalId="principal-admin",
        createdAtUtc=NOW,
        updatedAtUtc=NOW,
    )


def _workspace(display_name: str = "Pilot Workspace") -> EnterpriseWorkspace:
    return EnterpriseWorkspace(
        workspaceId="pilot-workspace",
        organizationId="local-org",
        displayName=display_name,
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


def test_enterprise_workspace_store_writes_reads_and_lists(tmp_path: Path) -> None:
    store = EnterpriseWorkspaceStore(tmp_path)
    org_result = store.write_organization(_organization())
    workspace_result = store.write_workspace(_workspace())

    assert org_result.status == "written"
    assert workspace_result.status == "written"
    assert store.get_organization().organization_id == "local-org"
    assert store.get_workspace("pilot-workspace").display_name == "Pilot Workspace"
    assert [workspace.workspace_id for workspace in store.list_workspaces()] == ["pilot-workspace"]


def test_enterprise_workspace_store_duplicate_hash_semantics(tmp_path: Path) -> None:
    store = EnterpriseWorkspaceStore(tmp_path)

    assert store.write_organization(_organization()).status == "written"
    assert store.write_organization(_organization()).status == "unchanged"
    conflict = store.write_organization(_organization(display_name="Other Org"))

    assert conflict.status == "conflict"
    assert conflict.existing_hash != conflict.new_hash


def test_enterprise_workspace_store_ignores_corrupted_list_entries(tmp_path: Path) -> None:
    store = EnterpriseWorkspaceStore(tmp_path)
    assert store.write_workspace(_workspace()).status == "written"
    corrupt = tmp_path / "enterprise-workspace" / "memberships" / "bad.json"
    corrupt.parent.mkdir(parents=True, exist_ok=True)
    corrupt.write_text("{not-json", encoding="utf-8")

    membership = EnterpriseWorkspaceMembership(
        membershipId="membership-admin",
        workspaceId="pilot-workspace",
        principalId="principal-admin",
        roles=("platform_admin",),
        status="active",
        grantedByPrincipalId="principal-admin",
        grantedAtUtc=NOW,
    )
    assert store.write_membership(membership).status == "written"

    assert [item.membership_id for item in store.list_memberships()] == ["membership-admin"]
