from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from typer.testing import CliRunner

from imperaos.cli import app
from imperaos.control_plane.evidence_corpus import (
    build_evidence_verification_corpus,
    verify_evidence_corpus,
)
from imperaos.control_plane.evidence_index import build_evidence_index
from imperaos.enterprise.signing import canonical_payload_hash
from imperaos.runtime.config import RuntimeConfig

runner = CliRunner()


def test_evidence_corpus_verifies_valid_and_negative_cases(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_signing_material(tmp_path)
    config = RuntimeConfig.from_profile("enterprise")
    corpus = build_evidence_verification_corpus(
        output_root=tmp_path / "corpus",
        config=config,
    )

    report = verify_evidence_corpus(corpus_root=Path(corpus.corpus_root), config=config)

    assert report["status"] == "pass"
    cases = {item["caseId"]: item for item in report["cases"]}
    assert cases["valid_signed_pack"]["actualStatus"] == "pass"
    assert cases["tampered_manifest"]["actualStatus"] == "fail"
    assert "EVIDENCE_HASH_MISMATCH" in cases["tampered_manifest"]["blockingReasons"]
    assert "RAW_SCREENSHOT_PERSISTED" in cases["raw_screenshot_violation"]["blockingReasons"]


def test_evidence_index_passes_valid_corpus_and_empty_root_is_conditional(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_signing_material(tmp_path)
    config = RuntimeConfig.from_profile("enterprise")
    build_evidence_verification_corpus(output_root=tmp_path / "corpus", config=config)

    index = build_evidence_index(
        config=config,
        evidence_root=tmp_path / "corpus" / "valid",
        root_dir=tmp_path / "state",
    )
    empty = build_evidence_index(
        config=config,
        evidence_root=tmp_path / "empty",
        root_dir=tmp_path / "empty-state",
    )

    assert index.status == "pass"
    assert index.entries[0].signature_status == "valid"
    assert empty.status == "conditional"
    assert "EVIDENCE_INDEX_EMPTY" in empty.warnings


def test_evidence_corpus_cli(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    _write_signing_material(tmp_path)

    build = runner.invoke(
        app,
        [
            "control-plane",
            "evidence",
            "corpus-build",
            "--profile",
            "enterprise",
            "--output-root",
            str(tmp_path / "corpus"),
            "--json",
        ],
    )
    verify = runner.invoke(
        app,
        [
            "control-plane",
            "evidence",
            "corpus-verify",
            "--profile",
            "enterprise",
            "--corpus-root",
            str(tmp_path / "corpus"),
            "--json",
        ],
    )

    assert build.exit_code == 0
    assert verify.exit_code == 0
    assert json.loads(verify.stdout)["status"] == "pass"


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
