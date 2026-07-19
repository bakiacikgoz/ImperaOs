from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from imperaos.control_plane.enterprise_workspace import (
    EnterpriseDevice,
    EnterpriseOrganization,
    EnterprisePrincipal,
    EnterpriseWorkspace,
    EnterpriseWorkspaceMembership,
    EnterpriseWorkspaceSnapshot,
    hash_identity_ref,
    make_membership_id,
)

NOW = datetime(2026, 6, 19, tzinfo=UTC)
HASH = "a" * 64


def test_enterprise_workspace_models_are_alias_safe_and_hash_only() -> None:
    organization = EnterpriseOrganization(
        organizationId="local-org",
        displayName="Local Org",
        status="active",
        createdByPrincipalId="principal-admin",
        createdAtUtc=NOW,
        updatedAtUtc=NOW,
    )
    workspace = EnterpriseWorkspace(
        workspaceId="pilot-workspace",
        organizationId=organization.organization_id,
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
    principal = EnterprisePrincipal(
        principalId="principal-admin",
        principalType="human_user",
        displayName="Admin",
        status="active",
        externalSubjectRefHash=hash_identity_ref(" admin@example.com "),
        issuerHash=hash_identity_ref("issuer"),
        createdAtUtc=NOW,
    )
    membership = EnterpriseWorkspaceMembership(
        membershipId=make_membership_id(workspace.workspace_id, principal.principal_id),
        workspaceId=workspace.workspace_id,
        principalId=principal.principal_id,
        roles=("platform_admin", "viewer", "platform_admin"),
        status="active",
        grantedByPrincipalId=principal.principal_id,
        grantedAtUtc=NOW,
    )
    device = EnterpriseDevice(
        deviceId="device-host-01",
        workspaceId=workspace.workspace_id,
        principalId="principal-device",
        displayName="Ops Host 01",
        platform="linux",
        hostFingerprintHash=HASH,
        status="active",
        createdAtUtc=NOW,
    )

    snapshot = EnterpriseWorkspaceSnapshot(
        status="ready",
        identity={"enabled": True, "verified": True, "actorId": "principal-admin"},
        organization={"organizationId": organization.organization_id, "displayName": "Local Org"},
        workspaces=[
            {"workspaceId": workspace.workspace_id, "displayName": workspace.display_name}
        ],
        currentWorkspaceId=workspace.workspace_id,
        principals=[
            {"principalId": principal.principal_id, "displayName": principal.display_name}
        ],
        memberships=[
            {"membershipId": membership.membership_id, "roles": list(membership.roles)}
        ],
        roles=[],
        devices=[{"deviceId": device.device_id, "status": device.status}],
        enrollments={"active": 0, "pendingApproval": 0, "revoked": 0},
        permissionMatrix={principal.principal_id: ["workspace.read"]},
        blockingReasons=[],
        generatedAtUtc=NOW,
    )

    payload = snapshot.model_dump(mode="json", by_alias=True)

    assert membership.roles == ("platform_admin", "viewer")
    assert payload["schemaVersion"] == "enterprise-workspace-snapshot/v1"
    assert payload["rawSecretsExposed"] is False
    assert payload["networkListenerEnabled"] is False
    assert "admin@example.com" not in str(payload)


def test_enterprise_workspace_models_reject_invalid_ids_and_hashes() -> None:
    with pytest.raises(ValidationError):
        EnterpriseOrganization(
            organizationId="../bad",
            displayName="Local Org",
            status="active",
            createdByPrincipalId="principal-admin",
            createdAtUtc=NOW,
            updatedAtUtc=NOW,
        )

    with pytest.raises(ValidationError):
        EnterpriseDevice(
            deviceId="device-host-01",
            workspaceId="pilot-workspace",
            principalId="principal-device",
            displayName="Ops Host 01",
            platform="linux",
            hostFingerprintHash="not-a-hash",
            status="active",
            createdAtUtc=NOW,
        )


def test_membership_requires_non_empty_roles() -> None:
    with pytest.raises(ValidationError):
        EnterpriseWorkspaceMembership(
            membershipId="membership-empty",
            workspaceId="pilot-workspace",
            principalId="principal-admin",
            roles=(),
            status="active",
            grantedByPrincipalId="principal-admin",
            grantedAtUtc=NOW,
        )
