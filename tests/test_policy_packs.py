from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from imperaos.cli import app
from imperaos.control_plane.policy_packs import (
    diff_policy_packs,
    load_policy_pack_manifest,
    promote_policy_pack_dry_run,
    validate_policy_pack,
)

runner = CliRunner()


def test_policy_pack_validation_passes_valid_enterprise_fixture() -> None:
    manifest = load_policy_pack_manifest(
        "contracts/control_plane/fixtures/policy_pack_valid_enterprise.json"
    )

    result = validate_policy_pack(manifest)

    assert result.status == "pass"
    assert result.rule_count == 3
    assert result.blocking_reasons == []


def test_policy_pack_validation_blocks_unsafe_allow() -> None:
    manifest = load_policy_pack_manifest(
        "contracts/control_plane/fixtures/policy_pack_invalid_unsafe_allow.json"
    )

    result = validate_policy_pack(manifest)

    assert result.status == "blocked"
    assert "DEFAULT_DECISION_NOT_DENY" in result.blocking_reasons
    assert "UNSAFE_ALLOW:destructive-allow" in result.blocking_reasons


def test_policy_pack_diff_and_promotion_dry_run_write_audit(tmp_path: Path) -> None:
    base = load_policy_pack_manifest(
        "contracts/control_plane/fixtures/policy_pack_valid_enterprise.json"
    )
    candidate = base.model_copy(update={"version": "2026.06.03-rc"})

    diff = diff_policy_packs(base=base, candidate=candidate)
    promotion = promote_policy_pack_dry_run(manifest=candidate, root_dir=tmp_path)

    assert diff.status == "pass"
    assert promotion.status == "pass"
    assert promotion.would_promote is True
    assert promotion.activation_audit_ref is not None
    assert (tmp_path / promotion.activation_audit_ref).exists()


def test_policy_pack_cli_validate_and_promote_dry_run(tmp_path: Path) -> None:
    manifest = "contracts/control_plane/fixtures/policy_pack_valid_enterprise.json"

    validate = runner.invoke(
        app,
        ["control-plane", "policy", "pack-validate", "--manifest", manifest, "--json"],
    )
    assert validate.exit_code == 0
    assert json.loads(validate.stdout)["status"] == "pass"

    promote = runner.invoke(
        app,
        [
            "control-plane",
            "policy",
            "pack-promote-dry-run",
            "--manifest",
            manifest,
            "--root-dir",
            str(tmp_path),
            "--json",
        ],
    )
    assert promote.exit_code == 0
    payload = json.loads(promote.stdout)
    assert payload["wouldPromote"] is True
    assert (tmp_path / payload["activationAuditRef"]).exists()
