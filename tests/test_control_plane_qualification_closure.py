from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from typer.testing import CliRunner

from imperaos.cli import app
from imperaos.control_plane.claim_guard import ClaimGuard
from imperaos.control_plane.qualification_closure import (
    generate_enterprise_hat_a_closure,
    verify_enterprise_hat_a_closure,
    write_pilot_qualification_fixture,
)
from imperaos.enterprise.signing import canonical_payload_hash
from imperaos.runtime.config import RuntimeConfig

runner = CliRunner()


def test_enterprise_hat_a_closure_ready_with_signed_fixture(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    _write_signing_material(tmp_path)
    config = RuntimeConfig.from_profile("enterprise")
    report = write_pilot_qualification_fixture(
        output_root=tmp_path / "qualification",
        config=config,
        now=datetime.now(UTC),
    )

    closure = generate_enterprise_hat_a_closure(
        profile="enterprise",
        output_root=tmp_path / "artifacts" / "enterprise-hat-a",
        qualification_root=report.parent,
        config=config,
    )

    assert closure.claim_status == "ready"
    assert closure.signature_status == "valid"
    assert closure.baseline_status == "pass"
    assert closure.workload_status == "pass"

    verify = verify_enterprise_hat_a_closure(
        input_path=Path(closure.artifact_path or ""),
        config=config,
    )
    assert verify["status"] == "pass"

    matrix = ClaimGuard(config=config).evaluate(evidence_root=tmp_path / "artifacts")
    claims = {claim.claim_id: claim for claim in matrix.claims}
    assert claims["enterprise-self-hosted-agent-control-plane"].status == "allowed"


def test_enterprise_hat_a_missing_evidence_is_conditional(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    _write_signing_material(tmp_path)
    config = RuntimeConfig.from_profile("enterprise")

    closure = generate_enterprise_hat_a_closure(
        profile="enterprise",
        output_root=tmp_path / "artifacts" / "enterprise-hat-a",
        qualification_root=tmp_path / "missing",
        config=config,
    )

    assert closure.claim_status == "conditional"
    assert closure.signature_status == "missing"
    assert "QUALIFICATION_REPORT_MISSING" in closure.warnings


def test_enterprise_hat_a_tampered_report_blocks(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    _write_signing_material(tmp_path)
    config = RuntimeConfig.from_profile("enterprise")
    report = write_pilot_qualification_fixture(
        output_root=tmp_path / "qualification",
        config=config,
    )
    payload = json.loads(report.read_text(encoding="utf-8"))
    payload["data"]["qualification_status"] = "tampered"
    report.write_text(json.dumps(payload), encoding="utf-8")

    closure = generate_enterprise_hat_a_closure(
        profile="enterprise",
        output_root=tmp_path / "artifacts" / "enterprise-hat-a",
        qualification_root=report.parent,
        config=config,
    )

    assert closure.claim_status == "blocked"
    assert "QUALIFICATION_SIGNATURE_INVALID" in closure.blocking_reasons


def test_enterprise_hat_a_stale_report_blocks(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    _write_signing_material(tmp_path)
    config = RuntimeConfig.from_profile("enterprise")
    report = write_pilot_qualification_fixture(
        output_root=tmp_path / "qualification",
        config=config,
        now=datetime.now(UTC) - timedelta(days=30),
    )

    closure = generate_enterprise_hat_a_closure(
        profile="enterprise",
        output_root=tmp_path / "artifacts" / "enterprise-hat-a",
        qualification_root=report.parent,
        config=config,
    )

    assert closure.claim_status == "blocked"
    assert "QUALIFICATION_EVIDENCE_STALE" in closure.blocking_reasons


def test_dev_hmac_does_not_satisfy_enterprise_ready(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("IMPERAOS_AUDIT_SIGNING_KEY", "dev-only")
    base = RuntimeConfig.from_profile("lite")
    config = base.model_copy(update={"profile_name": "enterprise"})
    report = write_pilot_qualification_fixture(
        output_root=tmp_path / "qualification",
        config=config,
    )

    closure = generate_enterprise_hat_a_closure(
        profile="enterprise",
        output_root=tmp_path / "artifacts" / "enterprise-hat-a",
        qualification_root=report.parent,
        config=config,
    )

    assert closure.claim_status == "blocked"
    assert "COMPAT_HMAC_NOT_ENTERPRISE_READY" in closure.blocking_reasons


def test_control_plane_qualification_close_cli(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    _write_signing_material(tmp_path)
    config = RuntimeConfig.from_profile("enterprise")
    write_pilot_qualification_fixture(output_root=tmp_path / "qualification", config=config)

    result = runner.invoke(
        app,
        [
            "control-plane",
            "qualification",
            "close",
            "--profile",
            "enterprise",
            "--qualification-root",
            str(tmp_path / "qualification"),
            "--output-root",
            str(tmp_path / "artifacts" / "enterprise-hat-a"),
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["claimStatus"] == "ready"


def _write_signing_material(root: Path) -> None:
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
    (private_dir / "current_key.json").write_text(
        json.dumps(private_payload, indent=2),
        encoding="utf-8",
    )
    (trusted_dir / f"{key_id}.json").write_text(
        json.dumps(public_payload, indent=2),
        encoding="utf-8",
    )
    (root / ".imperaos" / "enterprise" / "keys" / "manifest.json").write_text(
        json.dumps({"schema_version": "1", "current_key_id": key_id, "revoked_keys": []}),
        encoding="utf-8",
    )
    (identity_dir / "current_assertion.json").write_text(
        json.dumps(assertion, indent=2),
        encoding="utf-8",
    )
