from __future__ import annotations

from imperaos.computer_use.models import RiskClass
from imperaos.computer_use.vision_runtime.models import (
    InputActionType,
    NormalizedBBox,
    SurfaceKind,
    VisionAction,
    VisionObservation,
    VisionVerificationStatus,
)
from imperaos.computer_use.vision_runtime.verifier import ConservativeVisionStepVerifier


def _observation(
    hash_char: str,
    *,
    visible_text_redacted: list[str] | None = None,
    sensitive_indicators: list[str] | None = None,
    raw_screenshot_path: str | None = None,
) -> VisionObservation:
    return VisionObservation(
        screenshot_hash=hash_char * 64,
        raw_screenshot_path=raw_screenshot_path,
        captured_at="2026-05-05T00:00:00+00:00",
        platform="macos",
        surface_kind=SurfaceKind.BROWSER,
        visible_text_redacted=visible_text_redacted or [],
        sensitive_indicators=sensitive_indicators or [],
        confidence=0.92,
    )


def _action(
    action_type: InputActionType,
    *,
    expected_effect: str = "The local fixture advances.",
) -> VisionAction:
    return VisionAction(
        action_id=f"act-{action_type.value}",
        action_type=action_type,
        target_bbox=NormalizedBBox(x=0.1, y=0.1, w=0.2, h=0.2),
        rationale="Exercise verifier behavior.",
        expected_effect=expected_effect,
        risk_class=RiskClass.LOW if action_type == InputActionType.WAIT else RiskClass.MEDIUM,
        requires_approval=False,
        confidence=0.9,
    )


def test_conservative_verifier_accepts_wait_without_hash_change() -> None:
    verifier = ConservativeVisionStepVerifier()

    result = verifier.verify(
        before=_observation("a"),
        action=_action(InputActionType.WAIT),
        after=_observation("a"),
    )

    assert result.verified is True
    assert result.confidence == 0.75
    assert result.status == VisionVerificationStatus.SKIPPED
    assert result.reason_code == "VISION_VERIFICATION_SKIPPED"


def test_conservative_verifier_rejects_click_without_hash_change() -> None:
    verifier = ConservativeVisionStepVerifier()

    result = verifier.verify(
        before=_observation("a"),
        action=_action(InputActionType.CLICK),
        after=_observation("a"),
    )

    assert result.verified is False
    assert result.confidence == 0.2
    assert result.status == VisionVerificationStatus.FAILED
    assert result.reason_code == "VISION_VERIFICATION_FAILED"


def test_click_hash_change_without_semantic_match_is_inconclusive() -> None:
    verifier = ConservativeVisionStepVerifier()

    result = verifier.verify(
        before=_observation("a"),
        action=_action(InputActionType.CLICK),
        after=_observation("b"),
    )

    assert result.verified is False
    assert result.confidence == 0.45
    assert result.status == VisionVerificationStatus.INCONCLUSIVE
    assert result.reason_code == "VISION_VERIFICATION_INCONCLUSIVE"


def test_semantic_verifier_satisfies_fixture_expected_text() -> None:
    verifier = ConservativeVisionStepVerifier()

    result = verifier.verify(
        before=_observation("a"),
        action=_action(InputActionType.CLICK, expected_effect="Submitted"),
        after=_observation("b", visible_text_redacted=["Submitted"]),
    )

    assert result.verified is True
    assert result.status == VisionVerificationStatus.SATISFIED
    assert result.evidence["expected_effect_observed"] is True


def test_semantic_verifier_marks_hash_change_without_expected_match_inconclusive() -> None:
    verifier = ConservativeVisionStepVerifier()

    result = verifier.verify(
        before=_observation("a"),
        action=_action(InputActionType.CLICK, expected_effect="Submitted"),
        after=_observation("b", visible_text_redacted=["Still editing"]),
    )

    assert result.verified is False
    assert result.status == VisionVerificationStatus.INCONCLUSIVE
    assert result.reason_code == "VISION_VERIFICATION_INCONCLUSIVE"


def test_semantic_verifier_fails_when_sensitive_surface_appears_after_action() -> None:
    verifier = ConservativeVisionStepVerifier()

    result = verifier.verify(
        before=_observation("a"),
        action=_action(InputActionType.CLICK),
        after=_observation("b", sensitive_indicators=["password field"]),
    )

    assert result.verified is False
    assert result.status == VisionVerificationStatus.FAILED
    assert result.reason_code == "COMPUTER_USE_SENSITIVE_SURFACE_DETECTED"


def test_semantic_verifier_result_excludes_raw_screenshot_paths() -> None:
    verifier = ConservativeVisionStepVerifier()

    result = verifier.verify(
        before=_observation("a", raw_screenshot_path="/tmp/raw-before.png"),
        action=_action(InputActionType.CLICK),
        after=_observation("b", raw_screenshot_path="/tmp/raw-after.png"),
    )

    payload = result.model_dump(mode="json")
    assert "raw_screenshot_path" not in str(payload)
    assert result.before_observation_hash == "a" * 64
    assert result.after_observation_hash == "b" * 64
    assert result.action_digest is not None
