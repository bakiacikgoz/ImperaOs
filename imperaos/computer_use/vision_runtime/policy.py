from __future__ import annotations

import hashlib
import json

from imperaos.computer_use.models import ComputerUseMode, RiskClass
from imperaos.computer_use.vision_runtime.models import (
    InputActionType,
    SurfaceKind,
    VisionAction,
    VisionObservation,
    VisionPolicyDecision,
)
from imperaos.runtime.config import ComputerUseRuntimeConfig


class UniversalComputerUsePolicy:
    def __init__(self, config: ComputerUseRuntimeConfig) -> None:
        self.config = config
        self.policy_hash = self._hash_policy(config)

    def detect_surface_stop(
        self,
        observation: VisionObservation,
        *,
        objective: str,
    ) -> VisionPolicyDecision | None:
        del objective
        if observation.sensitive_indicators:
            return self._decision(
                allowed=False,
                denied=True,
                requires_approval=False,
                reason_code="COMPUTER_USE_SENSITIVE_SURFACE_DETECTED",
                risk_reasons=list(observation.sensitive_indicators),
            )
        active_app = (observation.active_app or "").casefold()
        blocked = {app.casefold() for app in self.config.blocked_apps}
        if active_app and active_app in blocked:
            return self._decision(
                allowed=False,
                denied=True,
                requires_approval=False,
                reason_code="COMPUTER_USE_BLOCKED_APP_DETECTED",
                risk_reasons=[observation.active_app or "blocked_app"],
            )
        if observation.confidence < self.config.min_verification_confidence:
            return self._decision(
                allowed=False,
                denied=True,
                requires_approval=False,
                reason_code="VISION_CONFIDENCE_BELOW_THRESHOLD",
                risk_reasons=["observation_confidence_below_threshold"],
            )
        return None

    def classify(
        self,
        action: VisionAction,
        observation: VisionObservation,
        *,
        mode: ComputerUseMode,
    ) -> VisionPolicyDecision:
        surface_stop = self.detect_surface_stop(observation, objective="")
        if surface_stop is not None:
            return surface_stop
        if observation.surface_kind == SurfaceKind.TERMINAL:
            if self.config.terminal_control == "deny":
                return self._decision(
                    allowed=False,
                    denied=True,
                    requires_approval=False,
                    reason_code="COMPUTER_USE_TERMINAL_CONTROL_DENIED",
                    risk_reasons=["terminal_surface"],
                )
            if self.config.terminal_control == "approval_required":
                return self._approval(["terminal_surface"])
        if action.confidence < self.config.min_action_confidence:
            return self._decision(
                allowed=False,
                denied=True,
                requires_approval=False,
                reason_code="VISION_CONFIDENCE_BELOW_THRESHOLD",
                risk_reasons=["action_confidence_below_threshold"],
            )
        if mode == ComputerUseMode.DRY_RUN:
            return self._decision(
                allowed=False,
                denied=False,
                requires_approval=False,
                reason_code="DRY_RUN_PREVIEW",
                risk_reasons=[],
            )
        if mode == ComputerUseMode.STEP_APPROVAL:
            return self._approval(["step_approval_mode"])
        if action.requires_approval or action.risk_class in {
            RiskClass.MEDIUM,
            RiskClass.HIGH,
            RiskClass.CRITICAL,
        }:
            return self._approval([f"risk_{action.risk_class.value}"])
        if action.action_type in {
            InputActionType.CLICK,
            InputActionType.DOUBLE_CLICK,
            InputActionType.RIGHT_CLICK,
            InputActionType.DRAG,
            InputActionType.TYPE_TEXT,
            InputActionType.PRESS_KEY,
            InputActionType.HOTKEY,
            InputActionType.SELECT_FILE,
            InputActionType.SWITCH_WINDOW,
            InputActionType.FOCUS_WINDOW_OR_APP,
        }:
            return self._approval([f"action_{action.action_type.value}"])
        return self._decision(
            allowed=True,
            denied=False,
            requires_approval=False,
            reason_code="POLICY_ALLOW",
            risk_reasons=[],
        )

    def _approval(self, risk_reasons: list[str]) -> VisionPolicyDecision:
        return self._decision(
            allowed=False,
            denied=False,
            requires_approval=True,
            reason_code="COMPUTER_USE_APPROVAL_REQUIRED",
            risk_reasons=risk_reasons,
        )

    def _decision(
        self,
        *,
        allowed: bool,
        denied: bool,
        requires_approval: bool,
        reason_code: str,
        risk_reasons: list[str],
    ) -> VisionPolicyDecision:
        return VisionPolicyDecision(
            allowed=allowed,
            denied=denied,
            requires_approval=requires_approval,
            reason_code=reason_code,
            risk_reasons=risk_reasons,
            policy_hash=self.policy_hash,
        )

    @staticmethod
    def _hash_policy(config: ComputerUseRuntimeConfig) -> str:
        payload = config.model_dump(mode="json")
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()
