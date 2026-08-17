from __future__ import annotations

import json

from typer.testing import CliRunner

from imperaos.cli import app
from imperaos.control_plane.rbac_admin import build_rbac_matrix, check_permission
from imperaos.runtime.config import RuntimeConfig

runner = CliRunner()


def test_rbac_matrix_uses_local_fixture_when_identity_disabled() -> None:
    matrix = build_rbac_matrix(RuntimeConfig.from_profile("lite"))

    assert matrix.source == "local_fixture"
    assert matrix.users[0].user_id == "identity-disabled"
    assert matrix.effective_permissions["identity-disabled"] == [
        "config.read",
        "evidence.read",
        "reports.read",
    ]
    assert {role.role_id for role in matrix.roles} >= {"viewer", "operator", "platform_admin"}


def test_rbac_permission_check_denies_by_default() -> None:
    config = RuntimeConfig.from_profile("lite")

    allowed = check_permission(
        config=config,
        actor_id="identity-disabled",
        permission="config.read",
    )
    denied = check_permission(
        config=config,
        actor_id="identity-disabled",
        permission="config.write",
    )
    unknown = check_permission(config=config, actor_id="unknown", permission="config.read")

    assert allowed.status == "allowed"
    assert denied.status == "denied"
    assert unknown.status == "denied"


def test_rbac_cli_matrix_and_check() -> None:
    matrix = runner.invoke(app, ["control-plane", "rbac", "matrix", "--profile", "lite", "--json"])
    assert matrix.exit_code == 0
    assert json.loads(matrix.stdout)["source"] == "local_fixture"

    check = runner.invoke(
        app,
        [
            "control-plane",
            "rbac",
            "check",
            "--profile",
            "lite",
            "--actor-id",
            "identity-disabled",
            "--permission",
            "config.read",
            "--json",
        ],
    )
    assert check.exit_code == 0
    assert json.loads(check.stdout)["status"] == "allowed"
