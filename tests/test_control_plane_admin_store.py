from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from typer.testing import CliRunner

from imperaos.cli import app
from imperaos.control_plane.admin_store import (
    IdentityAssertion,
    apply_admin_change,
    propose_admin_change,
)
from imperaos.enterprise.signing import canonical_payload_hash, verify_signed_artifact
from imperaos.governance.approval_store import ApprovalStore
from imperaos.runtime.config import RuntimeConfig

runner = CliRunner()


def test_admin_apply_requires_approval_and_writes_signed_audit(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_signing_material(tmp_path)
    config = RuntimeConfig.from_profile("enterprise")
    actor = _actor()
    proposal = propose_admin_change(
        store_root=tmp_path / "control-plane",
        actor=actor,
        kind="user",
        operation="update",
        payload={"id": "pilot-operator", "status": "active"},
        dry_run=True,
        config=config,
    )

    blocked = apply_admin_change(
        store_root=tmp_path / "control-plane",
        proposal_id=proposal.proposal_id,
        approval_id=proposal.approval_id or "",
        actor=actor,
        config=config,
    )
    ApprovalStore(tmp_path / "control-plane" / "approvals.sqlite3").decide(
        approval_id=proposal.approval_id or "",
        workspace_id="default",
        approve=True,
        actor=actor.actor_id,
        reason="test",
    )
    applied = apply_admin_change(
        store_root=tmp_path / "control-plane",
        proposal_id=proposal.proposal_id,
        approval_id=proposal.approval_id or "",
        actor=actor,
        config=config,
    )

    assert blocked.status == "blocked"
    assert "APPROVAL_NOT_APPROVED" in blocked.blocking_reasons
    assert applied.status == "applied"
    audit_path = tmp_path / "control-plane" / (applied.audit_envelope_path or "")
    assert verify_signed_artifact(path=audit_path, config=config)["signature_verified"] is True


def test_admin_propose_denies_unauthorized_actor(tmp_path: Path) -> None:
    proposal = propose_admin_change(
        store_root=tmp_path / "control-plane",
        actor=IdentityAssertion(actor_id="viewer", roles=["viewer"], permissions=["reports.read"]),
        kind="role",
        operation="update",
        payload={"id": "operator", "permissions": ["runtime.run"]},
        dry_run=True,
    )

    assert proposal.status == "denied"
    assert "RBAC_PERMISSION_DENIED" in proposal.blocking_reasons


def test_admin_cli_propose(tmp_path: Path) -> None:
    input_path = tmp_path / "proposal.json"
    input_path.write_text(
        json.dumps({"id": "pilot-operator", "status": "active"}),
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "control-plane",
            "admin",
            "propose",
            "--kind",
            "user",
            "--operation",
            "update",
            "--input",
            str(input_path),
            "--root-dir",
            str(tmp_path / "control-plane"),
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout)["status"] == "approval_required"


def _actor() -> IdentityAssertion:
    return IdentityAssertion(
        actor_id="enterprise-admin",
        roles=["platform_admin", "security_admin"],
        permissions=["config.write", "policy.promote"],
    )


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
    (private_dir / "current_key.json").write_text(json.dumps(private_payload), encoding="utf-8")
    (trusted_dir / f"{key_id}.json").write_text(json.dumps(public_payload), encoding="utf-8")
    (root / ".imperaos" / "enterprise" / "keys" / "manifest.json").write_text(
        json.dumps({"schema_version": "1", "current_key_id": key_id, "revoked_keys": []}),
        encoding="utf-8",
    )
    (identity_dir / "current_assertion.json").write_text(json.dumps(assertion), encoding="utf-8")
