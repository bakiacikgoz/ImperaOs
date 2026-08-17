from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from imperaos.computer_use.vision_runtime.runtime_gate import (
    ComputerUseOperationIntent,
    RuntimePreflightContext,
    evaluate_runtime_preflight,
)
from imperaos.runtime.config import ComputerUseRuntimeConfig

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = REPO_ROOT / "contracts" / "computer_use" / "fixtures"
NOW = datetime(2026, 5, 6, tzinfo=UTC)


def _fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


def _enabled_macos_config() -> ComputerUseRuntimeConfig:
    return ComputerUseRuntimeConfig(
        runtime_mode="vision_first",
        vision_enabled=True,
        vision_provider="ollama",
        vision_model="llava",
        macos_live_enabled=True,
        macos_capture_backend="screencapture",
        macos_input_backend="quartz",
        macos_require_step_approval=True,
    )


def _ready_macos_driver() -> dict[str, object]:
    return {
        "platform": "macos",
        "live_execution_enabled": True,
        "reason_code": None,
        "summary": "macOS fixture driver is ready.",
    }


def _context(
    config: ComputerUseRuntimeConfig,
    *,
    intent: ComputerUseOperationIntent = ComputerUseOperationIntent.NORMAL_RUNTIME_LIVE,
    platform: str = "macos",
    evidence_by_platform: dict[str, object] | None = None,
    evidence_paths: dict[str, str] | None = None,
    driver_readiness_by_platform: dict[str, object] | None = None,
    current_commit: str = "fixture-commit",
) -> RuntimePreflightContext:
    return RuntimePreflightContext(
        profile="balanced",
        platform=platform,
        operation_intent=intent,
        config=config,
        current_commit=current_commit,
        evidence_by_platform=evidence_by_platform,
        evidence_paths=evidence_paths,
        driver_readiness_by_platform=driver_readiness_by_platform,
    )


def test_missing_evidence_blocks_normal_runtime_live() -> None:
    decision = evaluate_runtime_preflight(
        context=_context(
            ComputerUseRuntimeConfig(),
            platform="windows",
        ),
        now=NOW,
    )

    assert decision.allowed is False
    assert decision.operation_intent == "normal_runtime_live"
    assert decision.reason_code == "WINDOWS_COMPUTER_USE_NOT_QUALIFIED"
    assert "COMPUTER_USE_EVIDENCE_MISSING" in decision.blockers
    assert decision.public_live_claim_allowed is False
    assert decision.to_payload()["captureAttempted"] is False
    assert decision.to_payload()["approvalConsumed"] is False
    assert decision.to_payload()["runtimePreflight"]["approvalConsumed"] is False


def test_stale_evidence_blocks_normal_runtime_live() -> None:
    decision = evaluate_runtime_preflight(
        context=_context(
            _enabled_macos_config(),
            evidence_by_platform={
                "macos": _fixture("macos_supervised_v2_evidence_fail_stale.json")
            },
            driver_readiness_by_platform={"macos": _ready_macos_driver()},
        ),
        now=NOW,
    )

    assert decision.allowed is False
    assert "COMPUTER_USE_EVIDENCE_STALE" in decision.blockers
    assert decision.evidence_status == "invalid"


def test_commit_mismatch_blocks_normal_runtime_live() -> None:
    decision = evaluate_runtime_preflight(
        context=_context(
            _enabled_macos_config(),
            evidence_by_platform={
                "macos": _fixture("macos_supervised_v2_evidence_fail_commit_mismatch.json")
            },
            driver_readiness_by_platform={"macos": _ready_macos_driver()},
        ),
        now=NOW,
    )

    assert decision.allowed is False
    assert "COMPUTER_USE_EVIDENCE_COMMIT_MISMATCH" in decision.blockers


def test_provider_and_backend_mismatch_block_normal_runtime_live() -> None:
    config = _enabled_macos_config().model_copy(
        update={
            "vision_provider": "mock",
            "vision_model": None,
            "macos_input_backend": "disabled",
        }
    )

    decision = evaluate_runtime_preflight(
        context=_context(
            config,
            evidence_by_platform={"macos": _fixture("macos_supervised_v2_evidence_pass.json")},
            driver_readiness_by_platform={"macos": _ready_macos_driver()},
        ),
        now=NOW,
    )

    assert decision.allowed is False
    assert "COMPUTER_USE_EVIDENCE_PROVIDER_MISMATCH" in decision.blockers
    assert "COMPUTER_USE_EVIDENCE_BACKEND_MISMATCH" in decision.blockers


def test_driver_readiness_failure_blocks_normal_runtime_live() -> None:
    decision = evaluate_runtime_preflight(
        context=_context(
            _enabled_macos_config(),
            evidence_by_platform={"macos": _fixture("macos_supervised_v2_evidence_pass.json")},
            driver_readiness_by_platform={
                "macos": {
                    "platform": "macos",
                    "live_execution_enabled": False,
                    "reason_code": "MACOS_CAPTURE_BACKEND_UNAVAILABLE",
                    "summary": "screencapture is unavailable.",
                }
            },
        ),
        now=NOW,
    )

    assert decision.allowed is False
    assert "MACOS_CAPTURE_BACKEND_UNAVAILABLE" in decision.blockers


def test_resolver_exception_blocks_fail_closed_without_leaking_exception() -> None:
    def _raise_resolution_error(**_kwargs: object) -> dict[str, object]:
        raise RuntimeError("boom C:/Users/duzey/private/rawScreenshotPath.png")

    decision = evaluate_runtime_preflight(
        context=_context(_enabled_macos_config()),
        resolver=_raise_resolution_error,
        now=NOW,
    )

    encoded = json.dumps(decision.to_payload(), sort_keys=True)
    assert decision.allowed is False
    assert decision.reason_code == "COMPUTER_USE_RUNTIME_RESOLUTION_FAILED"
    assert "COMPUTER_USE_RUNTIME_RESOLUTION_FAILED" in decision.blockers
    assert "boom" not in encoded
    assert "C:/Users" not in encoded
    assert "rawScreenshotPath" not in encoded


def test_public_live_intent_always_blocks_even_with_pass_evidence() -> None:
    decision = evaluate_runtime_preflight(
        context=_context(
            _enabled_macos_config(),
            intent=ComputerUseOperationIntent.PUBLIC_LIVE,
            evidence_by_platform={"macos": _fixture("macos_supervised_v2_evidence_pass.json")},
            driver_readiness_by_platform={"macos": _ready_macos_driver()},
        ),
        now=NOW,
    )

    assert decision.allowed is False
    assert decision.reason_code == "COMPUTER_USE_RUNTIME_PUBLIC_LIVE_DISABLED"
    assert decision.public_live_claim_allowed is False


@pytest.mark.parametrize(
    "intent",
    [
        ComputerUseOperationIntent.DETERMINISTIC_MOCK,
        ComputerUseOperationIntent.PROVIDER_DOCTOR,
        ComputerUseOperationIntent.PLATFORM_MATRIX,
    ],
)
def test_observational_intents_may_proceed_while_recording_resolver_state(
    intent: ComputerUseOperationIntent,
) -> None:
    decision = evaluate_runtime_preflight(
        context=_context(
            ComputerUseRuntimeConfig(),
            intent=intent,
            platform="windows",
        ),
        now=NOW,
    )

    assert decision.allowed is True
    assert decision.capability_status == "blocked"
    assert decision.evidence_status == "missing"
    assert decision.public_live_claim_allowed is False


def test_qualification_generation_allows_missing_evidence_when_safe_controls_are_explicit() -> None:
    decision = evaluate_runtime_preflight(
        context=_context(
            _enabled_macos_config(),
            intent=ComputerUseOperationIntent.QUALIFICATION_EVIDENCE_GENERATION,
        ),
        now=NOW,
    )

    assert decision.allowed is True
    assert decision.reason_code == "COMPUTER_USE_RUNTIME_QUALIFICATION_GENERATION_ALLOWED"
    assert decision.evidence_status == "missing"
    assert decision.public_live_claim_allowed is False


def test_qualification_generation_blocks_when_safe_controls_are_missing() -> None:
    unsafe_config = _enabled_macos_config().model_copy(
        update={
            "raw_screenshot_persistence": True,
            "raw_screenshot_retention": "explicit_opt_in",
            "raw_screenshot_max_count": 1,
        }
    )

    decision = evaluate_runtime_preflight(
        context=_context(
            unsafe_config,
            intent=ComputerUseOperationIntent.QUALIFICATION_EVIDENCE_GENERATION,
        ),
        now=NOW,
    )

    assert decision.allowed is False
    assert decision.reason_code == "COMPUTER_USE_RUNTIME_UNSAFE_QUALIFICATION_CONTROLS"
    assert "COMPUTER_USE_RAW_SCREENSHOT_INVARIANT_FAILED" in decision.blockers


def test_decision_payload_removes_evidence_paths() -> None:
    decision = evaluate_runtime_preflight(
        context=_context(
            _enabled_macos_config(),
            evidence_by_platform={"macos": _fixture("macos_supervised_v2_evidence_pass.json")},
            evidence_paths={"macos": "C:/Users/duzey/private/rawScreenshotPath.png"},
            driver_readiness_by_platform={"macos": _ready_macos_driver()},
        ),
        now=NOW,
    )

    payload = decision.to_payload()
    encoded = json.dumps(payload, sort_keys=True)
    assert decision.allowed is True
    assert payload["runtimePreflight"]["publicLiveClaimAllowed"] is False
    assert "C:/Users" not in encoded
    assert "rawScreenshotPath" not in encoded
    assert "path" not in payload["runtimePreflight"]["capability"]["evidence"]
