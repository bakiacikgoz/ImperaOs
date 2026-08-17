from __future__ import annotations

from typing import Protocol

from imperaos.computer_use.models import WorldModel
from imperaos.computer_use.vision_runtime.models import (
    ExecutionResult,
    StopDecision,
    VerificationResult,
    VisionAction,
    VisionInterpretation,
    VisionObservation,
    VisionStepResult,
)


class ScreenCapturePort(Protocol):
    def capture(self) -> VisionObservation: ...


class VisionInterpreterPort(Protocol):
    def interpret(
        self,
        *,
        objective: str,
        observation: VisionObservation,
        world: WorldModel | None,
    ) -> VisionInterpretation: ...


class ActionPlannerPort(Protocol):
    def next_action(
        self,
        *,
        objective: str,
        interpretation: VisionInterpretation,
        world: WorldModel | None,
    ) -> VisionAction | StopDecision: ...


class InputExecutorPort(Protocol):
    def execute(self, action: VisionAction) -> ExecutionResult: ...


class StepVerifierPort(Protocol):
    def verify(
        self,
        *,
        before: VisionObservation,
        action: VisionAction,
        after: VisionObservation,
    ) -> VerificationResult: ...


class VisionAuditSink(Protocol):
    def record_step(self, step: VisionStepResult) -> None: ...
    def finalize(self, status: str) -> dict[str, object]: ...
