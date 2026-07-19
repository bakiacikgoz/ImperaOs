from __future__ import annotations

import hashlib
import hmac
from pathlib import Path

import pytest

from imperaos.governance.redaction import redact_audit_payload
from scripts import run_enterprise_workspace_pr_readiness_gate as readiness_gate
from scripts import run_product_complete_closure_gate as product_gate

ACTIVE_IDENTITY_FILES = (
    Path("imperaos/governance/redaction.py"),
    Path("scripts/prepare_enterprise_fixture.py"),
    Path("scripts/run_managed_kms_adapter_drill.py"),
    Path("scripts/run_memory_governance_gate.py"),
    Path("scripts/run_enterprise_workspace_pr_readiness_gate.py"),
    Path("scripts/run_product_complete_closure_gate.py"),
)

CANONICAL_IDENTITIES = (
    (
        ACTIVE_IDENTITY_FILES[0],
        'os.getenv("IMPERAOS_AUDIT_SECRET", "imperaos-dev-secret")',
    ),
    (ACTIVE_IDENTITY_FILES[1], 'f"imperaos-enterprise-fixture:{args.key_id}"'),
    (
        ACTIVE_IDENTITY_FILES[2],
        'tempfile.TemporaryDirectory(prefix="imperaos-managed-kms-")',
    ),
    (ACTIVE_IDENTITY_FILES[3], 'owner="imperaos"'),
    (ACTIVE_IDENTITY_FILES[4], "https://github.com/bakiacikgoz/ImperaOS"),
    (ACTIVE_IDENTITY_FILES[5], "Product-complete closure gate for ImperaOS."),
)


def _former_brand_tokens() -> tuple[str, str]:
    return ("bin" + "liquid", "ae" + "gis" + "os")


def _assert_no_former_brand(text: str) -> None:
    folded = text.casefold()
    assert not any(token in folded for token in _former_brand_tokens())


@pytest.mark.parametrize("path", ACTIVE_IDENTITY_FILES, ids=lambda path: path.name)
def test_active_security_and_evidence_file_has_no_former_brand(path: Path) -> None:
    _assert_no_former_brand(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("path", "expected_identity"),
    CANONICAL_IDENTITIES,
    ids=lambda value: value.name if isinstance(value, Path) else value,
)
def test_active_security_and_evidence_file_has_canonical_identity(
    path: Path,
    expected_identity: str,
) -> None:
    assert expected_identity in path.read_text(encoding="utf-8")


def test_audit_redaction_uses_canonical_development_fallback(monkeypatch) -> None:
    monkeypatch.delenv("IMPERAOS_AUDIT_SECRET", raising=False)

    payload = redact_audit_payload({"api_key": "secret-value"})

    expected = hmac.new(
        b"imperaos-dev-secret",
        b"secret-value",
        hashlib.sha256,
    ).hexdigest()
    assert payload["api_key"]["hash"] == expected


def test_audit_redaction_environment_override_still_wins(monkeypatch) -> None:
    explicit_key = "test-explicit-audit-key"
    monkeypatch.setenv("IMPERAOS_AUDIT_SECRET", explicit_key)

    payload = redact_audit_payload({"api_key": "secret-value"})

    expected = hmac.new(
        explicit_key.encode("utf-8"),
        b"secret-value",
        hashlib.sha256,
    ).hexdigest()
    fallback = hmac.new(
        b"imperaos-dev-secret",
        b"secret-value",
        hashlib.sha256,
    ).hexdigest()
    assert payload["api_key"]["hash"] == expected
    assert payload["api_key"]["hash"] != fallback


def test_readiness_commands_emit_canonical_manual_pr_url(tmp_path: Path) -> None:
    branch = "codex/security-evidence-identity"

    text = readiness_gate.build_remote_commands(
        branch=branch,
        base_branch="main",
        pr_body_path=tmp_path / "pr_body_final.md",
        output_path=tmp_path / "remote_commands.md",
    )

    assert f"https://github.com/bakiacikgoz/ImperaOS/pull/new/{branch}" in text
    _assert_no_former_brand(text)
    for forbidden in readiness_gate.REMOTE_COMMAND_FORBIDDEN:
        assert forbidden not in text


def test_product_complete_pr_body_emits_canonical_product_identity() -> None:
    body = product_gate.render_pr_body(
        {
            "status": "pass",
            "headSha": "a" * 40,
            "noShipBlockers": [],
        }
    )

    assert "Product-complete closure gate for ImperaOS." in body
    _assert_no_former_brand(body)
