from __future__ import annotations

from imperaos.computer_use.models import ComputerUseStopReason, PerceptionSnapshot
from imperaos.computer_use.policy import BrowserAllowlistPolicy


def detect_hard_stop(
    *,
    snapshot: PerceptionSnapshot,
    policy: BrowserAllowlistPolicy,
    expected_url: str | None = None,
) -> ComputerUseStopReason | None:
    if not policy.allows_url(snapshot.current_url) and (
        not expected_url or not policy.allows_url(expected_url)
    ):
        return ComputerUseStopReason.POLICY_DENIED
    if expected_url and policy.detects_sensitive_surface(
        expected_url, snapshot.selector_context.selector
    ):
        return ComputerUseStopReason.SENSITIVE_SURFACE_DETECTED
    if policy.detects_sensitive_surface(snapshot.current_url, snapshot.selector_context.selector):
        return ComputerUseStopReason.SENSITIVE_SURFACE_DETECTED
    if snapshot.sensitive_surface:
        return ComputerUseStopReason.SENSITIVE_SURFACE_DETECTED
    if snapshot.source.value == "ocr":
        return ComputerUseStopReason.UNKNOWN_VISUAL
    if snapshot.selector_ambiguous:
        return ComputerUseStopReason.SELECTOR_AMBIGUOUS
    if snapshot.unexpected_modal:
        return ComputerUseStopReason.UNEXPECTED_MODAL
    if not snapshot.focused:
        return ComputerUseStopReason.FOCUS_DRIFT
    if snapshot.confidence < policy.confidence_threshold:
        return ComputerUseStopReason.CONFIDENCE_BELOW_THRESHOLD
    return None
