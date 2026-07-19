from __future__ import annotations

from imperaos.computer_use.models import RiskClass
from imperaos.computer_use.vision_runtime.models import (
    InputActionType,
    NormalizedBBox,
    StopDecision,
    SurfaceKind,
    VisionAction,
    VisionInterpretation,
)
from imperaos.computer_use.vision_runtime.planner import CandidateActionPlanner

_DEFAULT_BBOX = object()


def _action(
    *,
    action_id: str = "act-1",
    action_type: InputActionType = InputActionType.CLICK,
    confidence: float = 0.9,
    target_bbox: NormalizedBBox | None | object = _DEFAULT_BBOX,
    text: str | None = None,
    risk_class: RiskClass = RiskClass.MEDIUM,
    requires_approval: bool = True,
) -> VisionAction:
    resolved_bbox = (
        NormalizedBBox(x=0.2, y=0.2, w=0.1, h=0.1)
        if target_bbox is _DEFAULT_BBOX
        else target_bbox
    )
    return VisionAction(
        action_id=action_id,
        action_type=action_type,
        target_bbox=resolved_bbox,
        text=text,
        rationale="Interact with the visible fixture control.",
        expected_effect="The local fixture advances.",
        risk_class=risk_class,
        requires_approval=requires_approval,
        confidence=confidence,
    )


def _interpretation(actions: list[VisionAction]) -> VisionInterpretation:
    return VisionInterpretation(
        observation_hash="e" * 64,
        summary="A safe fixture is visible.",
        candidate_actions=actions,
        surface_kind=SurfaceKind.BROWSER,
        confidence=0.93,
    )


def _planner(
    *,
    allowed_action_types: set[InputActionType] | None = None,
    min_action_confidence: float = 0.82,
) -> CandidateActionPlanner:
    return CandidateActionPlanner(
        allowed_action_types=allowed_action_types
        or {
            InputActionType.MOVE_MOUSE,
            InputActionType.CLICK,
            InputActionType.DOUBLE_CLICK,
            InputActionType.RIGHT_CLICK,
            InputActionType.SCROLL,
            InputActionType.WAIT,
        },
        min_action_confidence=min_action_confidence,
    )


def test_no_candidates_returns_done_stop_decision() -> None:
    decision = _planner().next_action(
        objective="Submit fixture",
        interpretation=_interpretation([]),
        world=None,
    )

    assert isinstance(decision, StopDecision)
    assert decision.reason == "done"


def test_low_confidence_candidate_returns_confidence_stop_decision() -> None:
    decision = _planner().next_action(
        objective="Submit fixture",
        interpretation=_interpretation([_action(confidence=0.4)]),
        world=None,
    )

    assert isinstance(decision, StopDecision)
    assert decision.reason == "candidate_action_confidence_below_threshold"


def test_unsupported_action_returns_not_allowed_stop_decision() -> None:
    decision = _planner().next_action(
        objective="Submit fixture",
        interpretation=_interpretation([_action(action_type=InputActionType.DRAG)]),
        world=None,
    )

    assert isinstance(decision, StopDecision)
    assert decision.reason == "candidate_action_not_allowed"


def test_click_without_bbox_returns_no_safe_candidate() -> None:
    decision = _planner().next_action(
        objective="Submit fixture",
        interpretation=_interpretation([_action(target_bbox=None)]),
        world=None,
    )

    assert isinstance(decision, StopDecision)
    assert decision.reason == "no_safe_candidate_action"


def test_bbox_out_of_bounds_returns_no_safe_candidate() -> None:
    decision = _planner().next_action(
        objective="Submit fixture",
        interpretation=_interpretation(
            [_action(target_bbox=NormalizedBBox(x=0.95, y=0.2, w=0.1, h=0.1))]
        ),
        world=None,
    )

    assert isinstance(decision, StopDecision)
    assert decision.reason == "no_safe_candidate_action"


def test_first_invalid_second_valid_selects_second_candidate() -> None:
    decision = _planner().next_action(
        objective="Submit fixture",
        interpretation=_interpretation(
            [
                _action(action_id="invalid", target_bbox=None),
                _action(action_id="valid"),
            ]
        ),
        world=None,
    )

    assert isinstance(decision, VisionAction)
    assert decision.action_id == "valid"


def test_type_text_requires_text_and_preserves_approval_metadata() -> None:
    decision = _planner(
        allowed_action_types={InputActionType.TYPE_TEXT},
    ).next_action(
        objective="Fill fixture",
        interpretation=_interpretation(
            [
                _action(
                    action_type=InputActionType.TYPE_TEXT,
                    text="safe fixture text",
                    risk_class=RiskClass.HIGH,
                    requires_approval=True,
                    target_bbox=None,
                )
            ]
        ),
        world=None,
    )

    assert isinstance(decision, VisionAction)
    assert decision.action_type == InputActionType.TYPE_TEXT
    assert decision.requires_approval is True
    assert decision.text == "safe fixture text"


def test_candidate_ordering_preserves_first_valid_action() -> None:
    decision = _planner().next_action(
        objective="Submit fixture",
        interpretation=_interpretation(
            [
                _action(action_id="first", confidence=0.84),
                _action(action_id="second", confidence=0.99),
            ]
        ),
        world=None,
    )

    assert isinstance(decision, VisionAction)
    assert decision.action_id == "first"
