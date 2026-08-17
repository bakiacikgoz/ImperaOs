from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from jsonschema import validate

from imperaos.computer_use.vision_runtime.evidence import (
    validate_qualification_evidence,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = REPO_ROOT / "contracts" / "computer_use" / "fixtures"
SCHEMA_PATH = REPO_ROOT / "contracts" / "computer_use" / "qualification_evidence.schema.json"


def _fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


def _validation_context() -> dict[str, object]:
    return {
        "current_commit": "fixture-commit",
        "current_platform": "macos",
        "expected_provider": "ollama",
        "expected_model": "llava",
        "expected_capture_backend": "screencapture",
        "expected_input_backend": "quartz",
        "now": datetime(2026, 5, 6, tzinfo=UTC),
    }


def test_evidence_schema_validates_all_fixtures() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    for path in FIXTURE_ROOT.glob("macos_supervised_v2_evidence_*.json"):
        validate(instance=json.loads(path.read_text(encoding="utf-8")), schema=schema)


def test_valid_blocked_windows_fixture_is_accepted() -> None:
    result = validate_qualification_evidence(
        _fixture("macos_supervised_v2_evidence_blocked_windows.json"),
        current_platform="windows",
        current_commit="fixture-commit",
        now=datetime(2026, 5, 6, tzinfo=UTC),
    )

    assert result.valid is True
    assert result.status == "blocked"
    assert result.evidence is not None
    assert result.evidence.claim.public_live_claim_allowed is False
    assert result.reason_codes == ["MACOS_LIVE_QUALIFICATION_NOT_RUN_IN_THIS_ENV"]


def test_valid_pass_macos_fixture_is_accepted_without_public_live_claim() -> None:
    result = validate_qualification_evidence(
        _fixture("macos_supervised_v2_evidence_pass.json"),
        **_validation_context(),
    )

    assert result.valid is True
    assert result.status == "pass"
    assert result.evidence is not None
    assert result.evidence.claim.public_live_claim_allowed is False
    assert result.evidence.safety.raw_screenshot_count == 0


def test_raw_screenshot_evidence_is_rejected() -> None:
    result = validate_qualification_evidence(
        _fixture("macos_supervised_v2_evidence_fail_raw_screenshot.json"),
        **_validation_context(),
    )

    assert result.valid is False
    assert "RAW_SCREENSHOT_PERSISTENCE_DETECTED" in result.reason_codes


def test_stale_evidence_is_rejected() -> None:
    result = validate_qualification_evidence(
        _fixture("macos_supervised_v2_evidence_fail_stale.json"),
        **_validation_context(),
    )

    assert result.valid is False
    assert "QUALIFICATION_EVIDENCE_STALE" in result.reason_codes


def test_commit_mismatch_is_rejected_when_commit_binding_is_required() -> None:
    result = validate_qualification_evidence(
        _fixture("macos_supervised_v2_evidence_fail_commit_mismatch.json"),
        **_validation_context(),
    )

    assert result.valid is False
    assert "QUALIFICATION_EVIDENCE_COMMIT_MISMATCH" in result.reason_codes


def test_platform_mismatch_for_pass_evidence_is_rejected() -> None:
    result = validate_qualification_evidence(
        _fixture("macos_supervised_v2_evidence_pass.json"),
        **{**_validation_context(), "current_platform": "windows"},
    )

    assert result.valid is False
    assert "QUALIFICATION_EVIDENCE_PLATFORM_MISMATCH" in result.reason_codes


def test_provider_or_backend_mismatch_is_rejected() -> None:
    result = validate_qualification_evidence(
        _fixture("macos_supervised_v2_evidence_pass.json"),
        **{**_validation_context(), "expected_provider": "mock"},
    )

    assert result.valid is False
    assert "QUALIFICATION_EVIDENCE_PROVIDER_MISMATCH" in result.reason_codes


def test_unknown_top_level_field_is_rejected() -> None:
    payload = _fixture("macos_supervised_v2_evidence_pass.json")
    payload["unexpected"] = "not allowed"

    result = validate_qualification_evidence(payload, **_validation_context())

    assert result.valid is False
    assert "QUALIFICATION_EVIDENCE_SCHEMA_INVALID" in result.reason_codes
