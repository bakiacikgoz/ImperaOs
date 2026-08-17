from __future__ import annotations

import hashlib
import json

from imperaos.computer_use.vision_runtime.models import (
    InputActionType,
    VerificationResult,
    VisionAction,
    VisionObservation,
    VisionVerificationStatus,
)


class HashChangeVerifier:
    def verify(
        self,
        *,
        before: VisionObservation,
        action: VisionAction,
        after: VisionObservation,
    ) -> VerificationResult:
        changed = before.screenshot_hash != after.screenshot_hash
        return VerificationResult(
            verified=changed,
            confidence=0.9 if changed else 0.2,
            message="screen hash changed" if changed else "screen hash did not change",
            status=(
                VisionVerificationStatus.SATISFIED
                if changed
                else VisionVerificationStatus.FAILED
            ),
            reason_code=(
                "VISION_VERIFICATION_SATISFIED"
                if changed
                else "VISION_VERIFICATION_FAILED"
            ),
            evidence={"hash_changed": changed},
            before_observation_hash=before.screenshot_hash,
            after_observation_hash=after.screenshot_hash,
            action_digest=_action_digest(action),
        )


class ConservativeVisionStepVerifier:
    def verify(
        self,
        *,
        before: VisionObservation,
        action: VisionAction,
        after: VisionObservation,
    ) -> VerificationResult:
        if action.action_type in {InputActionType.WAIT, InputActionType.MOVE_MOUSE}:
            return VerificationResult(
                verified=True,
                confidence=0.75,
                message=f"{action.action_type.value} completed; screen change not required",
                status=VisionVerificationStatus.SKIPPED,
                reason_code="VISION_VERIFICATION_SKIPPED",
                evidence={"screen_change_required": False},
                before_observation_hash=before.screenshot_hash,
                after_observation_hash=after.screenshot_hash,
                action_digest=_action_digest(action),
            )
        if after.sensitive_indicators:
            return VerificationResult(
                verified=False,
                confidence=0.0,
                message="sensitive surface appeared after action",
                status=VisionVerificationStatus.FAILED,
                reason_code="COMPUTER_USE_SENSITIVE_SURFACE_DETECTED",
                evidence={
                    "sensitive_indicator_count": len(after.sensitive_indicators),
                },
                before_observation_hash=before.screenshot_hash,
                after_observation_hash=after.screenshot_hash,
                action_digest=_action_digest(action),
            )

        expected_effect_observed = _expected_effect_observed(action, after)
        if expected_effect_observed:
            return VerificationResult(
                verified=True,
                confidence=0.9,
                message="expected effect observed in redacted screen text",
                status=VisionVerificationStatus.SATISFIED,
                reason_code="VISION_VERIFICATION_SATISFIED",
                evidence={
                    "expected_effect_observed": True,
                    "visible_text_redacted_count": len(after.visible_text_redacted),
                },
                before_observation_hash=before.screenshot_hash,
                after_observation_hash=after.screenshot_hash,
                action_digest=_action_digest(action),
            )

        changed = before.screenshot_hash != after.screenshot_hash
        status = (
            VisionVerificationStatus.INCONCLUSIVE
            if changed
            else VisionVerificationStatus.FAILED
        )
        reason_code = (
            "VISION_VERIFICATION_INCONCLUSIVE" if changed else "VISION_VERIFICATION_FAILED"
        )
        return VerificationResult(
            verified=False,
            confidence=0.45 if changed else 0.2,
            message=(
                "screen hash changed but expected effect was not observed"
                if changed
                else "screen hash did not change"
            ),
            status=status,
            reason_code=reason_code,
            evidence={
                "hash_changed": changed,
                "expected_effect_observed": False,
                "visible_text_redacted_count": len(after.visible_text_redacted),
            },
            before_observation_hash=before.screenshot_hash,
            after_observation_hash=after.screenshot_hash,
            action_digest=_action_digest(action),
        )


def _expected_effect_observed(action: VisionAction, after: VisionObservation) -> bool:
    expected = action.expected_effect.strip().lower()
    if not expected:
        return False
    return any(expected in item.lower() for item in after.visible_text_redacted)


def _action_digest(action: VisionAction) -> str:
    payload = action.model_dump(mode="json", exclude_none=True)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
