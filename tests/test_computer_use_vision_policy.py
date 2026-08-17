from __future__ import annotations

from imperaos.computer_use.models import ComputerUseMode, RiskClass
from imperaos.computer_use.vision_runtime.models import (
    InputActionType,
    NormalizedBBox,
    SurfaceKind,
    VisionAction,
    VisionObservation,
)
from imperaos.computer_use.vision_runtime.policy import UniversalComputerUsePolicy
from imperaos.runtime.config import ComputerUseRuntimeConfig


def _observation(
    *,
    surface_kind: SurfaceKind = SurfaceKind.BROWSER,
    confidence: float = 0.92,
    active_app: str = "Safari",
    sensitive_indicators: list[str] | None = None,
) -> VisionObservation:
    return VisionObservation(
        screenshot_hash="b" * 64,
        captured_at="2026-05-05T00:00:00+00:00",
        platform="macos",
        active_app=active_app,
        surface_kind=surface_kind,
        sensitive_indicators=sensitive_indicators or [],
        confidence=confidence,
    )


def _action(
    *,
    action_type: InputActionType = InputActionType.CLICK,
    risk_class: RiskClass = RiskClass.MEDIUM,
    confidence: float = 0.9,
) -> VisionAction:
    return VisionAction(
        action_id="act-1",
        action_type=action_type,
        target_bbox=NormalizedBBox(x=0.2, y=0.2, w=0.1, h=0.1),
        rationale="Interact with visible control.",
        expected_effect="The next safe state appears.",
        risk_class=risk_class,
        requires_approval=False,
        confidence=confidence,
    )


def test_sensitive_surface_stops_fail_closed() -> None:
    policy = UniversalComputerUsePolicy(ComputerUseRuntimeConfig())

    decision = policy.detect_surface_stop(
        _observation(sensitive_indicators=["password field"]),
        objective="Sign in",
    )

    assert decision is not None
    assert decision.allowed is False
    assert decision.denied is True
    assert decision.reason_code == "COMPUTER_USE_SENSITIVE_SURFACE_DETECTED"


def test_terminal_surface_is_denied_by_default() -> None:
    policy = UniversalComputerUsePolicy(ComputerUseRuntimeConfig())

    decision = policy.classify(
        _action(action_type=InputActionType.TYPE_TEXT, risk_class=RiskClass.HIGH),
        _observation(surface_kind=SurfaceKind.TERMINAL, active_app="Terminal"),
        mode=ComputerUseMode.EXECUTE,
    )

    assert decision.denied is True
    assert decision.reason_code == "COMPUTER_USE_TERMINAL_CONTROL_DENIED"


def test_low_confidence_action_is_denied() -> None:
    policy = UniversalComputerUsePolicy(ComputerUseRuntimeConfig(min_action_confidence=0.82))

    decision = policy.classify(
        _action(confidence=0.5),
        _observation(),
        mode=ComputerUseMode.EXECUTE,
    )

    assert decision.denied is True
    assert decision.reason_code == "VISION_CONFIDENCE_BELOW_THRESHOLD"


def test_step_approval_mode_requires_approval_for_clicks() -> None:
    policy = UniversalComputerUsePolicy(ComputerUseRuntimeConfig())

    decision = policy.classify(
        _action(),
        _observation(),
        mode=ComputerUseMode.STEP_APPROVAL,
    )

    assert decision.allowed is False
    assert decision.requires_approval is True
    assert decision.reason_code == "COMPUTER_USE_APPROVAL_REQUIRED"


def test_read_only_wait_can_run_without_approval_in_execute_mode() -> None:
    policy = UniversalComputerUsePolicy(ComputerUseRuntimeConfig())

    decision = policy.classify(
        _action(action_type=InputActionType.WAIT, risk_class=RiskClass.LOW),
        _observation(),
        mode=ComputerUseMode.EXECUTE,
    )

    assert decision.allowed is True
    assert decision.requires_approval is False
    assert decision.denied is False
