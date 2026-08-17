from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from imperaos.computer_use.vision_runtime.capability_resolver import (
    resolve_capability_decision_snapshot,
)
from imperaos.runtime.config import ComputerUseRuntimeConfig


class ComputerUseOperationIntent(StrEnum):
    DETERMINISTIC_MOCK = "deterministic_mock"
    PROVIDER_DOCTOR = "provider_doctor"
    PLATFORM_MATRIX = "platform_matrix"
    QUALIFICATION_EVIDENCE_GENERATION = "qualification_evidence_generation"
    SUPERVISED_FIXTURE_LIVE = "supervised_fixture_live"
    NORMAL_RUNTIME_LIVE = "normal_runtime_live"
    PUBLIC_LIVE = "public_live"


@dataclass(frozen=True)
class RuntimePreflightContext:
    profile: str
    platform: str
    operation_intent: ComputerUseOperationIntent
    config: ComputerUseRuntimeConfig
    current_commit: str | None = None
    evidence_by_platform: Mapping[str, object] | None = None
    evidence_paths: Mapping[str, str] | None = None
    driver_readiness_by_platform: Mapping[str, object] | None = None
    provider: str | None = None
    model: str | None = None
    capture_backend: str | None = None
    input_backend: str | None = None
    root_dir: Path | None = None


@dataclass(frozen=True)
class RuntimePreflightDecision:
    allowed: bool
    status: str
    reason_code: str
    blockers: tuple[str, ...]
    operation_intent: str
    capability: Mapping[str, Any]
    capability_status: str
    evidence_status: str
    public_live_claim_allowed: bool = False
    live_execution_attempted: bool = False
    capture_attempted: bool = False
    provider_attempted: bool = False
    executor_attempted: bool = False
    approval_created: bool = False
    approval_consumed: bool = False

    def to_payload(self) -> dict[str, object]:
        runtime_preflight = {
            "allowed": self.allowed,
            "status": self.status,
            "operationIntent": self.operation_intent,
            "reasonCode": self.reason_code,
            "blockers": list(self.blockers),
            "capabilityStatus": self.capability_status,
            "evidenceStatus": self.evidence_status,
            "publicLiveClaimAllowed": False,
            "liveExecutionAttempted": self.live_execution_attempted,
            "captureAttempted": self.capture_attempted,
            "providerAttempted": self.provider_attempted,
            "executorAttempted": self.executor_attempted,
            "approvalCreated": self.approval_created,
            "approvalConsumed": self.approval_consumed,
            "capability": dict(self.capability),
        }
        return {
            "status": self.status,
            "reasonCode": self.reason_code,
            "liveExecutionAttempted": self.live_execution_attempted,
            "captureAttempted": self.capture_attempted,
            "providerAttempted": self.provider_attempted,
            "executorAttempted": self.executor_attempted,
            "approvalCreated": self.approval_created,
            "approvalConsumed": self.approval_consumed,
            "runtimePreflight": runtime_preflight,
        }


ResolverSnapshotCallable = Callable[..., dict[str, object]]


OBSERVATIONAL_INTENTS = {
    ComputerUseOperationIntent.DETERMINISTIC_MOCK,
    ComputerUseOperationIntent.PROVIDER_DOCTOR,
    ComputerUseOperationIntent.PLATFORM_MATRIX,
}

GATED_LIVE_INTENTS = {
    ComputerUseOperationIntent.NORMAL_RUNTIME_LIVE,
    ComputerUseOperationIntent.SUPERVISED_FIXTURE_LIVE,
}

SENSITIVE_KEYS = {
    "absolutePath",
    "approvalSnapshotBody",
    "env",
    "path",
    "providerRawPrompt",
    "providerRawResponse",
    "rawScreenshotPath",
    "raw_screenshot_path",
    "screenshotFile",
}


def evaluate_runtime_preflight(
    *,
    context: RuntimePreflightContext,
    resolver: ResolverSnapshotCallable | None = None,
    now: datetime | None = None,
) -> RuntimePreflightDecision:
    snapshot_resolver = resolver or resolve_capability_decision_snapshot
    try:
        snapshot = snapshot_resolver(
            config=context.config,
            profile=context.profile,
            current_platform=context.platform,
            current_commit=context.current_commit,
            now=now,
            evidence_by_platform=context.evidence_by_platform,
            evidence_paths=context.evidence_paths,
            driver_readiness_by_platform=context.driver_readiness_by_platform,
        )
    except Exception:
        return _decision(
            allowed=False,
            status="blocked",
            reason_code="COMPUTER_USE_RUNTIME_RESOLUTION_FAILED",
            blockers=("COMPUTER_USE_RUNTIME_RESOLUTION_FAILED",),
            context=context,
            capability={"status": "blocked", "evidence": {"status": "missing"}},
        )

    selected_capability = _selected_platform_capability(snapshot, context.platform)
    capability = _sanitize_mapping(selected_capability)

    if context.operation_intent == ComputerUseOperationIntent.PUBLIC_LIVE:
        return _decision(
            allowed=False,
            status="blocked",
            reason_code="COMPUTER_USE_RUNTIME_PUBLIC_LIVE_DISABLED",
            blockers=("COMPUTER_USE_RUNTIME_PUBLIC_LIVE_DISABLED",),
            context=context,
            capability=capability,
        )

    if context.operation_intent in OBSERVATIONAL_INTENTS:
        return _decision(
            allowed=True,
            status="allowed",
            reason_code=_read_string(
                selected_capability,
                "reasonCode",
                "COMPUTER_USE_RUNTIME_PREFLIGHT_OBSERVED",
            ),
            blockers=(),
            context=context,
            capability=capability,
        )

    if context.operation_intent == ComputerUseOperationIntent.QUALIFICATION_EVIDENCE_GENERATION:
        control_blockers = _qualification_control_blockers(context)
        if control_blockers:
            return _decision(
                allowed=False,
                status="blocked",
                reason_code="COMPUTER_USE_RUNTIME_UNSAFE_QUALIFICATION_CONTROLS",
                blockers=tuple(control_blockers),
                context=context,
                capability=capability,
            )
        return _decision(
            allowed=True,
            status="allowed",
            reason_code="COMPUTER_USE_RUNTIME_QUALIFICATION_GENERATION_ALLOWED",
            blockers=(),
            context=context,
            capability=capability,
        )

    if context.operation_intent in GATED_LIVE_INTENTS:
        if selected_capability.get("supervisedLiveAllowed") is True:
            return _decision(
                allowed=True,
                status="allowed",
                reason_code=_read_string(
                    selected_capability,
                    "reasonCode",
                    "COMPUTER_USE_RUNTIME_PREFLIGHT_ALLOWED",
                ),
                blockers=(),
                context=context,
                capability=capability,
            )
        blockers = tuple(_blocker_codes(selected_capability)) or (
            _read_string(
                selected_capability,
                "reasonCode",
                "COMPUTER_USE_RUNTIME_CAPABILITY_NOT_QUALIFIED",
            ),
        )
        return _decision(
            allowed=False,
            status="blocked",
            reason_code=_read_string(
                selected_capability,
                "reasonCode",
                "COMPUTER_USE_RUNTIME_CAPABILITY_NOT_QUALIFIED",
            ),
            blockers=blockers,
            context=context,
            capability=capability,
        )

    return _decision(
        allowed=False,
        status="blocked",
        reason_code="COMPUTER_USE_RUNTIME_UNKNOWN_INTENT",
        blockers=("COMPUTER_USE_RUNTIME_UNKNOWN_INTENT",),
        context=context,
        capability=capability,
    )


def _decision(
    *,
    allowed: bool,
    status: str,
    reason_code: str,
    blockers: tuple[str, ...],
    context: RuntimePreflightContext,
    capability: Mapping[str, Any],
) -> RuntimePreflightDecision:
    return RuntimePreflightDecision(
        allowed=allowed,
        status=status,
        reason_code=reason_code,
        blockers=blockers,
        operation_intent=context.operation_intent.value,
        capability=capability,
        capability_status=_read_string(capability, "status", "blocked"),
        evidence_status=_evidence_status(capability),
        public_live_claim_allowed=False,
    )


def _selected_platform_capability(
    snapshot: Mapping[str, object],
    platform: str,
) -> dict[str, object]:
    platforms = snapshot.get("platforms")
    if not isinstance(platforms, Mapping) or not platforms:
        return {"status": "blocked", "evidence": {"status": "missing"}}
    platform_key = platform if platform in platforms else snapshot.get("currentPlatform")
    if not isinstance(platform_key, str) or platform_key not in platforms:
        platform_key = "windows" if "windows" in platforms else next(iter(platforms))
    selected = platforms.get(platform_key)
    return dict(selected) if isinstance(selected, Mapping) else {}


def _qualification_control_blockers(context: RuntimePreflightContext) -> list[str]:
    config = context.config
    blockers: list[str] = []
    if context.platform != "macos":
        blockers.append("COMPUTER_USE_RUNTIME_UNSUPPORTED_QUALIFICATION_PLATFORM")
    if not config.vision_enabled or config.vision_provider == "none":
        blockers.append("VISION_PROVIDER_UNAVAILABLE")
    if not config.macos_live_enabled:
        blockers.append("COMPUTER_USE_CONFIG_LIVE_DISABLED")
    if config.macos_capture_backend == "disabled":
        blockers.append("MACOS_CAPTURE_BACKEND_DISABLED")
    if config.macos_input_backend == "disabled":
        blockers.append("MACOS_INPUT_BACKEND_DISABLED")
    if not config.macos_require_step_approval:
        blockers.append("COMPUTER_USE_STEP_APPROVAL_REQUIRED")
    if (
        config.raw_screenshot_persistence
        or config.raw_screenshot_retention != "disabled"
        or config.raw_screenshot_max_count != 0
    ):
        blockers.append("COMPUTER_USE_RAW_SCREENSHOT_INVARIANT_FAILED")
    if config.terminal_control != "deny":
        blockers.append("COMPUTER_USE_TERMINAL_CONTROL_NOT_DENIED")
    if config.sensitive_surface_policy != "stop":
        blockers.append("COMPUTER_USE_SENSITIVE_SURFACE_STOP_REQUIRED")
    return _unique(blockers)


def _blocker_codes(capability: Mapping[str, object]) -> list[str]:
    blockers = capability.get("blockers")
    if not isinstance(blockers, list):
        return []
    codes: list[str] = []
    for blocker in blockers:
        if isinstance(blocker, Mapping):
            code = blocker.get("code")
            if isinstance(code, str):
                codes.append(code)
        elif isinstance(blocker, str):
            codes.append(blocker)
    return codes


def _evidence_status(capability: Mapping[str, Any]) -> str:
    evidence = capability.get("evidence")
    if isinstance(evidence, Mapping):
        return _read_string(evidence, "status", "missing")
    return "missing"


def _read_string(source: Mapping[str, object], key: str, fallback: str) -> str:
    value = source.get(key)
    return value if isinstance(value, str) and value else fallback


def _sanitize_mapping(value: Mapping[str, object]) -> dict[str, Any]:
    sanitized = _sanitize_value(value)
    return sanitized if isinstance(sanitized, dict) else {}


def _sanitize_value(value: object) -> object:
    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str) or key in SENSITIVE_KEYS:
                continue
            result[key] = _sanitize_value(item)
        return result
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, str) and _looks_sensitive_string(value):
        return "[redacted]"
    return value


def _looks_sensitive_string(value: str) -> bool:
    normalized = value.replace("\\", "/").lower()
    return (
        "c:/users/" in normalized
        or "/users/" in normalized
        or "rawscreenshotpath" in normalized
        or "raw_screenshot_path" in normalized
    )


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
