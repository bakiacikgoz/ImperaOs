from __future__ import annotations

from collections.abc import Iterable

from imperaos.computer_use.models import WorldModel
from imperaos.computer_use.vision_runtime.models import (
    StopDecision,
    VerificationResult,
    VisionAction,
    VisionInterpretation,
    VisionObservation,
)


class DeterministicScreenCapture:
    def __init__(self, observations: Iterable[VisionObservation]) -> None:
        self._observations = list(observations)
        self._index = 0

    def capture(self) -> VisionObservation:
        if not self._observations:
            raise RuntimeError("no deterministic observations configured")
        if self._index >= len(self._observations):
            return self._observations[-1]
        observation = self._observations[self._index]
        self._index += 1
        return observation


class DeterministicActionPlanner:
    def __init__(self, actions: Iterable[VisionAction | StopDecision]) -> None:
        self._actions = list(actions)
        self._index = 0

    def next_action(
        self,
        *,
        objective: str,
        interpretation: VisionInterpretation,
        world: WorldModel | None,
    ) -> VisionAction | StopDecision:
        del objective, interpretation, world
        if self._index >= len(self._actions):
            return StopDecision(reason="done", summary="No more deterministic actions.")
        action = self._actions[self._index]
        self._index += 1
        return action


class MockVisionInterpreter:
    def interpret(
        self,
        *,
        objective: str,
        observation: VisionObservation,
        world,
    ) -> VisionInterpretation:
        del world
        return VisionInterpretation(
            observation_hash=observation.screenshot_hash,
            summary=f"Mock interpretation for: {objective}",
            candidate_actions=[],
            surface_kind=observation.surface_kind,
            active_app_guess=observation.active_app,
            active_window_title_guess=observation.active_window_title,
            visible_text_redacted=observation.visible_text_redacted,
            ui_elements=observation.ui_elements,
            sensitive_indicators=observation.sensitive_indicators,
            confidence=observation.confidence,
        )


class DeterministicStepVerifier:
    def __init__(self, results: Iterable[VerificationResult]) -> None:
        self._results = list(results)
        self._index = 0

    def verify(
        self,
        *,
        before: VisionObservation,
        action: VisionAction,
        after: VisionObservation,
    ) -> VerificationResult:
        del before, action, after
        if self._index >= len(self._results):
            return VerificationResult(verified=True, confidence=1.0, message="default pass")
        result = self._results[self._index]
        self._index += 1
        return result
