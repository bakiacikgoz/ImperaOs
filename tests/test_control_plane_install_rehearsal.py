from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from typer.testing import CliRunner

from imperaos.cli import app
from imperaos.control_plane.install_rehearsal import run_install_rehearsal
from imperaos.enterprise.signing import canonical_payload_hash
from imperaos.runtime.config import RuntimeConfig

runner = CliRunner()


def test_install_rehearsal_generates_safe_report(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    _write_enterprise_fixture(tmp_path)
    _write_enterprise_docs(tmp_path)
    report = run_install_rehearsal(
        target_root=tmp_path / "rehearsal",
        profile="enterprise",
        mode="source_cli",
        output_path=tmp_path / "artifacts" / "install-rehearsal" / "report.json",
        config=RuntimeConfig.from_profile("enterprise"),
    )

    assert report.status == "pass"
    assert report.support_bundle_safe is True
    assert report.rollback_plan_present is True
    assert (tmp_path / "artifacts" / "install-rehearsal" / "INSTALL_REHEARSAL_REPORT.md").exists()


def test_install_rehearsal_rejects_unsafe_target_root(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    _write_enterprise_fixture(tmp_path)
    _write_enterprise_docs(tmp_path)
    report = run_install_rehearsal(
        target_root=tmp_path,
        profile="enterprise",
        mode="source_cli",
        output_path=tmp_path / "report.json",
        config=RuntimeConfig.from_profile("enterprise"),
        dry_run=True,
    )

    assert report.status == "fail"
    assert "REHEARSAL_TARGET_ROOT_UNSAFE" in report.blocking_reasons


def test_install_rehearsal_cli(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    _write_enterprise_fixture(tmp_path)
    _write_enterprise_docs(tmp_path)

    result = runner.invoke(
        app,
        [
            "control-plane",
            "install",
            "rehearsal",
            "--profile",
            "enterprise",
            "--target-root",
            str(tmp_path / "rehearsal"),
            "--output",
            str(tmp_path / "report.json"),
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout)["status"] == "pass"


def _write_enterprise_docs(root: Path) -> None:
    for name in (
        "SECURITY_BASELINE.md",
        "KEY_MANAGEMENT.md",
        "UPGRADE_AND_RECOVERY.md",
        "OBSERVABILITY_AND_SLO.md",
        "QUALIFICATION_MATRIX.md",
        "INSTALL.md",
        "DEPLOYMENT_GUIDE.md",
        "SUPPORT_BUNDLE.md",
    ):
        (root / name).write_text(f"# {name}\n", encoding="utf-8")


def _write_enterprise_fixture(root: Path) -> None:
    private_key = Ed25519PrivateKey.generate()
    private_raw = private_key.private_bytes_raw()
    public_raw = private_key.public_key().public_bytes_raw()
    private_dir = root / ".imperaos" / "enterprise" / "keys" / "private"
    trusted_dir = root / ".imperaos" / "enterprise" / "keys" / "trusted"
    identity_dir = root / ".imperaos" / "enterprise" / "identity"
    private_dir.mkdir(parents=True, exist_ok=True)
    trusted_dir.mkdir(parents=True, exist_ok=True)
    identity_dir.mkdir(parents=True, exist_ok=True)
    key_id = "enterprise-signing-current"
    private_payload = {
        "schema_version": "1",
        "key_id": key_id,
        "algorithm": "ed25519",
        "purpose": "artifact-signing",
        "private_key": base64.b64encode(private_raw).decode("ascii"),
        "public_key": base64.b64encode(public_raw).decode("ascii"),
        "created_at": datetime.now(UTC).isoformat(),
    }
    public_payload = {
        "schema_version": "1",
        "key_id": key_id,
        "algorithm": "ed25519",
        "purpose": "artifact-signing",
        "public_key": base64.b64encode(public_raw).decode("ascii"),
        "state": "active",
        "created_at": datetime.now(UTC).isoformat(),
    }
    assertion = {
        "schema_version": "1",
        "assertion_type": "external",
        "actor_id": "enterprise-admin",
        "subject": "enterprise-admin@example.local",
        "issuer": "idp.local",
        "roles": ["platform_admin", "security_admin"],
        "permissions": ["runtime.run", "policy.promote", "support.export"],
        "issued_at": datetime.now(UTC).isoformat(),
        "expires_at": (datetime.now(UTC) + timedelta(hours=4)).isoformat(),
        "key_id": key_id,
    }
    assertion["signature"] = base64.b64encode(
        private_key.sign(canonical_payload_hash(assertion).encode("utf-8"))
    ).decode("ascii")
    (private_dir / "current_key.json").write_text(json.dumps(private_payload), encoding="utf-8")
    (trusted_dir / f"{key_id}.json").write_text(json.dumps(public_payload), encoding="utf-8")
    (root / ".imperaos" / "enterprise" / "keys" / "manifest.json").write_text(
        json.dumps({"schema_version": "1", "current_key_id": key_id, "revoked_keys": []}),
        encoding="utf-8",
    )
    (identity_dir / "current_assertion.json").write_text(json.dumps(assertion), encoding="utf-8")
