from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from imperaos.cli import app
from imperaos.control_plane.policy_pack_store import (
    plan_policy_pack_rollback,
    promote_policy_pack,
    stage_policy_pack,
    validate_lifecycle_policy_pack,
)
from imperaos.control_plane.policy_packs import load_policy_pack_manifest

runner = CliRunner()
REPO_ROOT = Path(__file__).resolve().parents[1]


def _manifest_path() -> Path:
    return REPO_ROOT / "contracts/control_plane/fixtures/policy_pack_valid_enterprise.json"


def test_policy_pack_lifecycle_validate_stage_promote_rollback(tmp_path: Path) -> None:
    manifest = load_policy_pack_manifest(_manifest_path())
    validated = validate_lifecycle_policy_pack(
        manifest=manifest,
        store_root=tmp_path / "control-plane",
    )
    staged = stage_policy_pack(manifest=manifest, store_root=tmp_path / "control-plane")
    active = promote_policy_pack(manifest=manifest, store_root=tmp_path / "control-plane")
    rollback = plan_policy_pack_rollback(
        policy_pack_id=manifest.policy_pack_id,
        store_root=tmp_path / "control-plane",
    )

    assert validated.status == "validated"
    assert staged.status == "staged"
    assert active.status == "active"
    assert rollback.status == "rollback_planned"


def test_policy_pack_lifecycle_cli(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "control-plane",
            "policy-pack",
            "stage",
            "--manifest",
            str(_manifest_path()),
            "--root-dir",
            str(tmp_path / "control-plane"),
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout)["status"] == "staged"
