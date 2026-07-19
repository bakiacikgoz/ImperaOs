from __future__ import annotations

from imperaos.control_plane.enterprise_rbac import (
    HIGH_RISK_ROLES,
    ROLE_CATALOG,
    build_canonical_role_catalog,
    check_roles_for_permission,
    permissions_for_roles,
)


def test_canonical_roles_have_non_empty_permission_sets() -> None:
    catalog = build_canonical_role_catalog()

    assert set(catalog) >= {
        "viewer",
        "operator",
        "approver",
        "auditor",
        "policy_admin",
        "security_admin",
        "platform_admin",
        "break_glass_admin",
    }
    assert all(role.permissions for role in catalog.values())
    assert ROLE_CATALOG["platform_admin"].risk == "high"


def test_unknown_role_produces_no_permissions() -> None:
    assert permissions_for_roles(["unknown"]) == set()
    assert check_roles_for_permission(["unknown"], "workspace.read").allowed is False


def test_viewer_cannot_create_enrollment_token_but_platform_admin_can() -> None:
    denied = check_roles_for_permission(["viewer"], "agent.enrollment.create")
    allowed = check_roles_for_permission(["platform_admin"], "agent.enrollment.create")

    assert denied.allowed is False
    assert denied.reason_code == "WORKSPACE_PERMISSION_DENIED"
    assert allowed.allowed is True
    assert allowed.reason_code == "WORKSPACE_PERMISSION_ALLOWED"


def test_high_risk_roles_are_explicit() -> None:
    assert {"platform_admin", "security_admin", "break_glass_admin"} == HIGH_RISK_ROLES
