from __future__ import annotations

from imperaos.computer_use.models import WorldModel
from imperaos.computer_use.vision_runtime.models import (
    InputActionType,
    NormalizedBBox,
    StopDecision,
    VisionAction,
    VisionInterpretation,
)


def first_candidate_or_done(interpretation: VisionInterpretation) -> VisionAction | StopDecision:
    if interpretation.candidate_actions:
        return interpretation.candidate_actions[0]
    return StopDecision(reason="done", summary="No candidate actions remain.")


class CandidateActionPlanner:
    def __init__(
        self,
        *,
        allowed_action_types: set[InputActionType],
        min_action_confidence: float,
        max_candidates: int = 3,
    ) -> None:
        self.allowed_action_types = frozenset(allowed_action_types)
        self.min_action_confidence = min_action_confidence
        self.max_candidates = max_candidates

    def next_action(
        self,
        *,
        objective: str,
        interpretation: VisionInterpretation,
        world: WorldModel | None,
    ) -> VisionAction | StopDecision:
        _ = (objective, world)
        if not interpretation.candidate_actions:
            return StopDecision(reason="done", summary="No candidate actions remain.")

        rejected_reasons: list[str] = []
        for action in interpretation.candidate_actions[: self.max_candidates]:
            rejection = self._rejection_reason(action)
            if rejection is None:
                return action
            rejected_reasons.append(rejection)

        return StopDecision(
            reason=_summarize_rejection_reasons(rejected_reasons),
            summary="No safe candidate action passed planner hygiene checks.",
        )

    def _rejection_reason(self, action: VisionAction) -> str | None:
        if action.action_type not in self.allowed_action_types:
            return "candidate_action_not_allowed"
        if action.confidence < self.min_action_confidence:
            return "candidate_action_confidence_below_threshold"
        if not _has_valid_payload(action):
            return "no_safe_candidate_action"
        return None


def _summarize_rejection_reasons(rejected_reasons: list[str]) -> str:
    if rejected_reasons and all(
        reason == "candidate_action_confidence_below_threshold" for reason in rejected_reasons
    ):
        return "candidate_action_confidence_below_threshold"
    if rejected_reasons and all(
        reason == "candidate_action_not_allowed" for reason in rejected_reasons
    ):
        return "candidate_action_not_allowed"
    return "no_safe_candidate_action"


def _has_valid_payload(action: VisionAction) -> bool:
    if action.action_type in {
        InputActionType.MOVE_MOUSE,
        InputActionType.CLICK,
        InputActionType.DOUBLE_CLICK,
        InputActionType.RIGHT_CLICK,
    }:
        return action.target_bbox is not None and _bbox_within_bounds(action.target_bbox)
    if action.action_type == InputActionType.TYPE_TEXT:
        return bool(action.text and action.text.strip())
    if action.action_type == InputActionType.HOTKEY:
        return bool(action.hotkey) and not _is_denied_hotkey(action.hotkey)
    return True


def _bbox_within_bounds(bbox: NormalizedBBox) -> bool:
    return bbox.x + bbox.w <= 1.0 and bbox.y + bbox.h <= 1.0


def _is_denied_hotkey(hotkey: list[str]) -> bool:
    normalized = "+".join(part.strip().lower() for part in hotkey)
    return normalized in {"cmd+q", "cmd+w", "cmd+space"}
