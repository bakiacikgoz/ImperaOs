from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from imperaos.control_plane.models import (
    AdminSummary,
    PolicyPackSummary,
    RbacBinding,
    RbacMatrixSnapshot,
    RbacPermissionDecision,
    RoleSummary,
    UserSummary,
)
from imperaos.enterprise.identity import describe_actor
from imperaos.runtime.config import RuntimeConfig

ROLE_CATALOG: dict[str, dict[str, object]] = {
    "viewer": {
        "label": "Viewer",
        "risk": "low",
        "permissions": ["config.read", "evidence.read", "reports.read"],
    },
    "operator": {
        "label": "Operator",
        "risk": "medium",
        "permissions": [
            "approval.decide",
            "config.read",
            "evidence.read",
            "reports.read",
            "runtime.run",
        ],
    },
    "platform_admin": {
        "label": "Platform Admin",
        "risk": "high",
        "permissions": [
            "backup.create",
            "config.read",
            "config.write",
            "evidence.read",
            "policy.promote",
            "restore.verify",
            "runtime.run",
        ],
    },
    "security_admin": {
        "label": "Security Admin",
        "risk": "high",
        "permissions": [
            "audit.export",
            "config.read",
            "evidence.read",
            "keys.rotate",
            "policy.promote",
            "reports.read",
        ],
    },
}


def build_rbac_matrix(config: RuntimeConfig) -> RbacMatrixSnapshot:
    identity = describe_actor_safe(config)
    source = _admin_source(config, identity)
    actor = identity.get("actor") if isinstance(identity.get("actor"), dict) else {}
    user = _user_from_actor(actor, source=source)
    role_ids = _role_ids(actor)
    roles = _roles_with_assignments(role_ids)
    bindings = [
        RbacBinding(actor_id=user.user_id, role_id=role_id, source=source)
        for role_id in role_ids
    ]
    effective_permissions = {user.user_id: sorted(_permissions_for_roles(role_ids))}
    permissions = {
        str(permission)
        for item in ROLE_CATALOG.values()
        for permission in item["permissions"]
    }
    return RbacMatrixSnapshot(
        users=[user],
        roles=roles,
        permissions=sorted(permissions),
        bindings=bindings,
        effective_permissions=effective_permissions,
        source=source,
    )


def build_admin_summary(
    config: RuntimeConfig,
    *,
    policy_pack: PolicyPackSummary,
) -> AdminSummary:
    matrix = build_rbac_matrix(config)
    return AdminSummary(
        users=matrix.users,
        roles=matrix.roles,
        policy_packs=[policy_pack],
        permission_matrix={role.role_id: role.permissions for role in matrix.roles},
        source=matrix.source,
    )


def check_permission(
    *,
    config: RuntimeConfig,
    actor_id: str,
    permission: str,
    dry_run: bool = True,
) -> RbacPermissionDecision:
    matrix = build_rbac_matrix(config)
    effective = matrix.effective_permissions.get(actor_id, [])
    bindings = [binding.role_id for binding in matrix.bindings if binding.actor_id == actor_id]
    allowed = permission in effective
    return RbacPermissionDecision(
        actor_id=actor_id,
        permission=permission,
        status="allowed" if allowed else "denied",
        dry_run=dry_run,
        reason_code="RBAC_PERMISSION_ALLOWED" if allowed else "RBAC_PERMISSION_DENIED",
        roles=bindings,
        permissions=effective,
        generated_at_utc=datetime.now(UTC),
    )


def describe_actor_safe(config: RuntimeConfig) -> dict[str, Any]:
    if not config.identity.enabled:
        return {
            "identity_enabled": False,
            "verified": True,
            "actor": {
                "actor_id": "identity-disabled",
                "subject": "identity disabled",
                "issuer": None,
                "roles": ["viewer"],
                "permissions": ROLE_CATALOG["viewer"]["permissions"],
            },
        }
    try:
        return describe_actor(config)
    except Exception as exc:  # noqa: BLE001
        return {
            "identity_enabled": True,
            "verified": False,
            "error_code": getattr(exc, "error_code", "IDENTITY_UNAVAILABLE"),
        }


def _user_from_actor(
    actor: object,
    *,
    source: str,
) -> UserSummary:
    actor_record = actor if isinstance(actor, dict) else {}
    role_ids = _role_ids(actor_record)
    permissions = sorted(_permissions_for_roles(role_ids))
    return UserSummary(
        user_id=str(actor_record.get("actor_id") or "operator-unresolved"),
        subject=str(actor_record.get("subject") or "identity disabled"),
        issuer=str(actor_record.get("issuer")) if actor_record.get("issuer") else None,
        status="active" if source != "external_idp_placeholder" else "unknown",
        roles=role_ids,
        permissions=permissions,
        last_seen_utc=datetime.now(UTC),
    )


def _role_ids(actor: object) -> list[str]:
    actor_record = actor if isinstance(actor, dict) else {}
    raw_roles = actor_record.get("roles")
    roles = [str(item) for item in raw_roles] if isinstance(raw_roles, list) else []
    known = [role for role in roles if role in ROLE_CATALOG]
    return known or ["viewer"]


def _roles_with_assignments(role_ids: list[str]) -> list[RoleSummary]:
    return [
        RoleSummary(
            role_id=role_id,
            label=str(ROLE_CATALOG[role_id]["label"]),
            risk_level=str(ROLE_CATALOG[role_id]["risk"]),
            permissions=sorted(_permissions_for_roles([role_id])),
            assignment_count=1 if role_id in role_ids else 0,
        )
        for role_id in sorted(ROLE_CATALOG)
    ]


def _permissions_for_roles(role_ids: list[str]) -> set[str]:
    permissions: set[str] = set()
    for role_id in role_ids:
        role = ROLE_CATALOG.get(role_id)
        if role is None:
            continue
        permissions.update(str(item) for item in role["permissions"])
    return permissions


def _admin_source(
    config: RuntimeConfig,
    identity: dict[str, Any],
) -> str:
    if config.identity.enabled and identity.get("verified"):
        return "identity_assertion"
    if config.identity.enabled:
        return "external_idp_placeholder"
    return "local_fixture"
