from __future__ import annotations

from typing import Literal

from pydantic import Field

from imperaos.control_plane.enterprise_workspace import StrictModel

CanonicalRoleId = Literal[
    "viewer",
    "operator",
    "approver",
    "auditor",
    "policy_admin",
    "security_admin",
    "platform_admin",
    "break_glass_admin",
]

HIGH_RISK_ROLES = {"platform_admin", "security_admin", "break_glass_admin"}

CANONICAL_PERMISSIONS = {
    "workspace.read",
    "workspace.bootstrap",
    "workspace.membership.read",
    "workspace.membership.write",
    "workspace.role.read",
    "workspace.role.assign",
    "agent.read",
    "agent.enrollment.create",
    "agent.enrollment.revoke",
    "agent.enrollment.import",
    "agent.enrollment.approve",
    "agent.enrollment.reject",
    "agent.run",
    "approval.read",
    "approval.decide",
    "approval.execute",
    "audit.read",
    "audit.export",
    "replay.verify",
    "policy.read",
    "policy.write",
    "policy.promote",
    "memory.read",
    "memory.write",
    "memory.admin",
    "support.export",
    "keys.read",
    "keys.rotate",
    "config.read",
    "config.write",
}


class CanonicalRole(StrictModel):
    role_id: str = Field(alias="roleId")
    label: str
    risk: Literal["low", "medium", "high", "critical"]
    permissions: tuple[str, ...]


class WorkspacePermissionDecision(StrictModel):
    allowed: bool
    permission: str
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    reason_code: str = Field(alias="reasonCode")


VIEWER_PERMISSIONS = {
    "workspace.read",
    "workspace.role.read",
    "agent.read",
    "audit.read",
    "config.read",
}

ROLE_CATALOG: dict[str, CanonicalRole] = {
    "viewer": CanonicalRole(
        roleId="viewer",
        label="Viewer",
        risk="low",
        permissions=tuple(sorted(VIEWER_PERMISSIONS)),
    ),
    "operator": CanonicalRole(
        roleId="operator",
        label="Operator",
        risk="medium",
        permissions=tuple(
            sorted(VIEWER_PERMISSIONS | {"agent.run", "memory.read", "approval.read"})
        ),
    ),
    "approver": CanonicalRole(
        roleId="approver",
        label="Approver",
        risk="medium",
        permissions=tuple(sorted(VIEWER_PERMISSIONS | {"approval.decide"})),
    ),
    "auditor": CanonicalRole(
        roleId="auditor",
        label="Auditor",
        risk="medium",
        permissions=tuple(sorted(VIEWER_PERMISSIONS | {"audit.export", "replay.verify"})),
    ),
    "policy_admin": CanonicalRole(
        roleId="policy_admin",
        label="Policy Admin",
        risk="high",
        permissions=tuple(
            sorted(VIEWER_PERMISSIONS | {"policy.read", "policy.write", "policy.promote"})
        ),
    ),
    "security_admin": CanonicalRole(
        roleId="security_admin",
        label="Security Admin",
        risk="high",
        permissions=tuple(
            sorted(
                VIEWER_PERMISSIONS
                | {
                    "audit.export",
                    "keys.read",
                    "keys.rotate",
                    "support.export",
                    "approval.execute",
                    "replay.verify",
                }
            )
        ),
    ),
    "platform_admin": CanonicalRole(
        roleId="platform_admin",
        label="Platform Admin",
        risk="high",
        permissions=tuple(
            sorted(
                CANONICAL_PERMISSIONS
                - {
                    "keys.rotate",
                    "keys.read",
                    "approval.execute",
                    "audit.export",
                    "support.export",
                }
            )
        ),
    ),
    "break_glass_admin": CanonicalRole(
        roleId="break_glass_admin",
        label="Break Glass Admin",
        risk="critical",
        permissions=tuple(sorted(CANONICAL_PERMISSIONS)),
    ),
}


def build_canonical_role_catalog() -> dict[str, CanonicalRole]:
    return dict(ROLE_CATALOG)


def permissions_for_roles(role_ids: list[str] | tuple[str, ...]) -> set[str]:
    permissions: set[str] = set()
    for role_id in role_ids:
        role = ROLE_CATALOG.get(role_id)
        if role is None:
            continue
        permissions.update(role.permissions)
    return permissions


def check_roles_for_permission(
    role_ids: list[str] | tuple[str, ...],
    permission: str,
) -> WorkspacePermissionDecision:
    permissions = permissions_for_roles(role_ids)
    known_roles = [role_id for role_id in role_ids if role_id in ROLE_CATALOG]
    allowed = permission in permissions
    return WorkspacePermissionDecision(
        allowed=allowed,
        permission=permission,
        roles=sorted(set(known_roles)),
        permissions=sorted(permissions),
        reasonCode="WORKSPACE_PERMISSION_ALLOWED" if allowed else "WORKSPACE_PERMISSION_DENIED",
    )
