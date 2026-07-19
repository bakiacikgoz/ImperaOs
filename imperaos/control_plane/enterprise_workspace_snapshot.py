from __future__ import annotations

from pathlib import Path
from typing import Any

from imperaos.control_plane.enterprise_rbac import ROLE_CATALOG, permissions_for_roles
from imperaos.control_plane.enterprise_workspace import (
    CanonicalRoleSummary,
    EnterpriseDeviceSummary,
    EnterpriseEnrollmentSummary,
    EnterpriseIdentitySummary,
    EnterpriseMembershipSummary,
    EnterpriseOrganizationSummary,
    EnterprisePrincipalSummary,
    EnterpriseWorkspaceSnapshot,
    EnterpriseWorkspaceSummary,
)
from imperaos.control_plane.enterprise_workspace_store import EnterpriseWorkspaceStore
from imperaos.enterprise.identity import describe_actor
from imperaos.runtime.paths import CONTROL_PLANE_STATE_ROOT


def build_enterprise_workspace_snapshot(
    *,
    config: Any,
    root_dir: str | Path = CONTROL_PLANE_STATE_ROOT,
    env: dict[str, str] | None = None,
) -> EnterpriseWorkspaceSnapshot:
    store = EnterpriseWorkspaceStore(root_dir)
    identity_payload = (
        {"identity_enabled": False, "verified": False, "error_code": "IDENTITY_DISABLED"}
        if not config.identity.enabled
        else describe_actor(config, env=env)
    )
    identity = EnterpriseIdentitySummary(
        enabled=bool(identity_payload.get("identity_enabled")),
        verified=bool(identity_payload.get("verified")),
        actorId=_actor_id(identity_payload),
        errorCode=str(identity_payload.get("error_code"))
        if identity_payload.get("error_code")
        else None,
    )
    organization = store.get_organization()
    workspaces = store.list_workspaces()
    principals = store.list_principals()
    memberships = store.list_memberships()
    devices = store.list_devices()
    enrolled_agents = store.list_enrolled_agents()
    tokens = store.list_enrollment_tokens()
    requests = store.list_enrollment_requests()
    blocking_reasons: list[str] = []
    if config.profile_name == "enterprise" and not identity.verified:
        blocking_reasons.append(identity.error_code or "IDENTITY_REQUIRED")
    if organization is None or not workspaces:
        blocking_reasons.append("ENTERPRISE_WORKSPACE_SETUP_REQUIRED")

    if not config.identity.enabled:
        status = "disabled"
    elif blocking_reasons and blocking_reasons != ["ENTERPRISE_WORKSPACE_SETUP_REQUIRED"]:
        status = "blocked"
    elif organization is None or not workspaces:
        status = "setup_required"
    else:
        status = "ready"

    permission_matrix = {
        membership.principal_id: sorted(permissions_for_roles(membership.roles))
        for membership in memberships
        if membership.status == "active"
    }
    return EnterpriseWorkspaceSnapshot(
        status=status,
        identity=identity,
        organization=EnterpriseOrganizationSummary(
            organizationId=organization.organization_id,
            displayName=organization.display_name,
            status=organization.status,
        )
        if organization
        else None,
        workspaces=[
            EnterpriseWorkspaceSummary(
                workspaceId=workspace.workspace_id,
                displayName=workspace.display_name,
                status=workspace.status,
                environment=workspace.environment,
            )
            for workspace in workspaces
        ],
        currentWorkspaceId=workspaces[0].workspace_id if workspaces else None,
        principals=[
            EnterprisePrincipalSummary(
                principalId=principal.principal_id,
                displayName=principal.display_name,
                principalType=principal.principal_type,
                status=principal.status,
            )
            for principal in principals
        ],
        memberships=[
            EnterpriseMembershipSummary(
                membershipId=membership.membership_id,
                principalId=membership.principal_id,
                workspaceId=membership.workspace_id,
                roles=list(membership.roles),
                status=membership.status,
            )
            for membership in memberships
        ],
        roles=[
            CanonicalRoleSummary(
                roleId=role.role_id,
                label=role.label,
                risk=role.risk,
                permissions=list(role.permissions),
            )
            for role in ROLE_CATALOG.values()
        ],
        devices=[
            EnterpriseDeviceSummary(
                deviceId=device.device_id,
                workspaceId=device.workspace_id,
                principalId=device.principal_id,
                displayName=device.display_name,
                platform=device.platform,
                status=device.status,
            )
            for device in devices
        ],
        enrollments=EnterpriseEnrollmentSummary(
            active=sum(1 for item in enrolled_agents if item.status == "active"),
            pendingApproval=sum(1 for item in requests if item.status == "pending_approval"),
            revoked=sum(1 for item in enrolled_agents if item.status == "revoked"),
            expiredTokens=sum(1 for item in tokens if item.status == "expired"),
        ),
        permissionMatrix=permission_matrix,
        blockingReasons=blocking_reasons,
    )


def _actor_id(identity_payload: dict[str, Any]) -> str | None:
    actor = identity_payload.get("actor")
    if isinstance(actor, dict) and actor.get("actor_id"):
        return str(actor["actor_id"])
    return None
