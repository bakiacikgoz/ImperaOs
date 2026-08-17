from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from imperaos.computer_use.vision_runtime.drivers.base import PlatformDriverReadiness
from imperaos.computer_use.vision_runtime.errors import VisionRuntimeError
from imperaos.computer_use.vision_runtime.models import (
    ExecutionResult,
    InputActionType,
    NormalizedBBox,
    VisionAction,
    VisionObservation,
)
from imperaos.computer_use.vision_runtime.platforms import (
    PlatformCapability,
    build_platform_capability,
)
from imperaos.computer_use.vision_runtime.qualification import (
    macos_opt_in_state,
    validate_platform_qualification_report,
)
from imperaos.runtime.config import ComputerUseRuntimeConfig
from imperaos.runtime.platform import PlatformInfo, current_platform


@dataclass(frozen=True, slots=True)
class DisplayBounds:
    width: int
    height: int
    origin_x: int = 0
    origin_y: int = 0


def readiness(*, vision_enabled: bool) -> PlatformDriverReadiness:
    return PlatformDriverReadiness(
        platform="macos",
        live_execution_enabled=vision_enabled,
        reason_code=None if vision_enabled else "VISION_RUNTIME_NOT_CONFIGURED",
        summary=(
            "macOS vision-first runtime is configured for supervised execution."
            if vision_enabled
            else "macOS vision-first runtime is scaffolded but no vision provider is configured."
        ),
    )


def readiness_report(
    config: ComputerUseRuntimeConfig,
    *,
    environment: Mapping[str, str] | None = None,
    qualification_report: Mapping[str, Any] | None = None,
    commit: str | None = None,
) -> PlatformCapability:
    return build_platform_capability(
        config,
        platform="macos",
        environment=environment,
        qualification_report=qualification_report,
        commit=commit,
    )


class MacOSVisionReadiness:
    def __init__(self, config: ComputerUseRuntimeConfig) -> None:
        self.config = config

    def evaluate(
        self,
        *,
        platform_info: PlatformInfo | None = None,
        environment: Mapping[str, str] | None = None,
        qualification_report: Mapping[str, Any] | None = None,
        commit: str | None = None,
        which: Callable[[str], str | None] = shutil.which,
        input_backend_available: bool | None = None,
    ) -> dict[str, Any]:
        platform = platform_info or current_platform()
        env = dict(environment or {})
        opt_in = macos_opt_in_state(env)
        checks: list[dict[str, Any]] = []
        if platform.label != "macos":
            reason = (
                "WINDOWS_COMPUTER_USE_NOT_QUALIFIED"
                if platform.label == "windows"
                else "LINUX_COMPUTER_USE_NOT_QUALIFIED"
            )
            checks.append(
                _check(
                    "platform",
                    False,
                    reason,
                    "Vision live execution remains gated to supervised macOS qualification.",
                    "Use live vision computer-use only with valid macOS qualification evidence.",
                )
            )
            return self._report(
                platform.label,
                checks,
                stage="not_qualified",
                live_enabled=False,
                reason_code=reason,
                permissions=_permissions_payload(
                    screen_recording="unknown",
                    accessibility="unknown",
                    input_monitoring="not_required",
                ),
                provider=_provider_payload(
                    configured=False,
                    name=self.config.vision_provider,
                    model=self.config.vision_model or "",
                    strict_json=False,
                    ready=False,
                    reason_code="VISION_PROVIDER_UNAVAILABLE",
                ),
                capture={"backend": "disabled", "ready": False},
                input_state={"backend": "disabled", "ready": False},
                opt_in=opt_in,
                qualification=_qualification_payload(
                    required=True,
                    present=False,
                    valid=False,
                    fresh=False,
                    status="missing",
                    report_path=self.config.macos_qualification_report,
                    reason_code="MACOS_QUALIFICATION_REPORT_MISSING",
                ),
            )

        screen_recording = _env_permission_status(
            env,
            "IMPERAOS_COMPUTER_USE_MACOS_SCREEN_RECORDING",
            "IMPERAOS_TEST_MACOS_SCREEN_RECORDING",
        )
        accessibility = _env_permission_status(
            env,
            "IMPERAOS_COMPUTER_USE_MACOS_ACCESSIBILITY",
            "IMPERAOS_TEST_MACOS_ACCESSIBILITY",
        )
        provider = _evaluate_provider(self.config, which=which)
        capture = _evaluate_capture(
            self.config,
            which=which,
            screen_recording=screen_recording,
        )
        input_state = _evaluate_input(
            self.config,
            accessibility=accessibility,
            input_backend_available=input_backend_available,
        )
        qualification = _evaluate_qualification(
            self.config,
            qualification_report=qualification_report,
            commit=commit,
        )

        checks.append(
            _check(
                "macos_live_opt_in",
                bool(opt_in["present"]),
                None if opt_in["present"] else "MACOS_LIVE_OPT_IN_MISSING",
                "Explicit macOS live fixture opt-in is present."
                if opt_in["present"]
                else "Explicit macOS live fixture opt-in is missing.",
                "Set the documented one-run macOS live fixture opt-in environment values.",
            )
        )
        checks.append(
            _check(
                "macos_live_ack",
                bool(opt_in["acknowledged"]),
                None if opt_in["acknowledged"] else "MACOS_LIVE_ACK_MISSING",
                "The operator acknowledgment is present."
                if opt_in["acknowledged"]
                else "The operator acknowledgment is missing.",
                "Set IMPERAOS_COMPUTER_USE_ACK for this supervised local fixture run.",
            )
        )
        checks.append(
            _check(
                "supervised_fixture_only",
                bool(opt_in["supervisedFixtureOnly"]),
                None
                if opt_in["supervisedFixtureOnly"]
                else "MACOS_SUPERVISED_FIXTURE_ONLY_REQUIRED",
                "The run is scoped to supervised local fixtures."
                if opt_in["supervisedFixtureOnly"]
                else "The run is not scoped to supervised local fixtures.",
                "Set IMPERAOS_COMPUTER_USE_SUPERVISED_FIXTURE_ONLY=1.",
            )
        )
        checks.append(
            _check(
                "step_approval_required",
                bool(opt_in["stepApprovalRequired"]),
                None if opt_in["stepApprovalRequired"] else "MACOS_STEP_APPROVAL_REQUIRED",
                "Step approval is required for the run."
                if opt_in["stepApprovalRequired"]
                else "Step approval is not explicitly required for the run.",
                "Set IMPERAOS_COMPUTER_USE_REQUIRE_STEP_APPROVAL=1.",
            )
        )
        checks.append(
            _check(
                "vision_enabled",
                self.config.vision_enabled,
                None if self.config.vision_enabled else "VISION_RUNTIME_DISABLED",
                "Vision runtime feature flag is enabled."
                if self.config.vision_enabled
                else "Vision runtime feature flag is disabled.",
                "Set computer_use.vision_enabled=true only on a supervised pilot host.",
            )
        )
        checks.append(
            _check(
                "macos_live_enabled",
                self.config.macos_live_enabled,
                None if self.config.macos_live_enabled else "MACOS_LIVE_FLAG_DISABLED",
                "macOS live execution flag is enabled."
                if self.config.macos_live_enabled
                else "macOS live execution flag is disabled.",
                "Set computer_use.macos_live_enabled=true after local qualification.",
            )
        )
        checks.append(
            _check(
                "vision_provider",
                bool(provider["ready"]),
                None if provider["ready"] else str(provider["reasonCode"]),
                "Vision provider is configured and ready."
                if provider["ready"]
                else "Vision provider is not ready.",
                "Configure computer_use.vision_provider and computer_use.vision_model.",
            )
        )
        checks.append(
            _check(
                "screen_capture",
                bool(capture["ready"]),
                None if capture["ready"] else str(capture["reasonCode"]),
                "macOS capture backend is ready."
                if capture["ready"]
                else "macOS capture backend is unavailable or disabled.",
                "Verify macOS Screen Recording permission and system capture tooling manually.",
            )
        )
        checks.append(
            _check(
                "accessibility_input",
                bool(input_state["ready"]),
                None if input_state["ready"] else str(input_state["reasonCode"]),
                "Quartz input backend is configured."
                if input_state["ready"]
                else "Quartz input backend is unavailable or disabled.",
                (
                    "Install optional macOS computer-use dependencies and grant "
                    "Accessibility manually."
                ),
            )
        )
        checks.append(
            _check(
                "raw_screenshot_policy",
                self.config.raw_screenshot_persistence is False
                and self.config.raw_screenshot_retention == "disabled"
                and self.config.raw_screenshot_max_count == 0,
                None
                if self.config.raw_screenshot_persistence is False
                and self.config.raw_screenshot_retention == "disabled"
                and self.config.raw_screenshot_max_count == 0
                else "RAW_SCREENSHOT_PERSISTENCE_DENIED",
                "Raw screenshot persistence is disabled by default.",
                (
                    "Keep raw_screenshot_retention=disabled unless using explicit "
                    "local debug evidence."
                ),
            )
        )
        if self.config.platform_qualification_required:
            checks.append(
                _check(
                    "qualification",
                    bool(qualification["fresh"]),
                    None if qualification["fresh"] else str(qualification["reasonCode"]),
                    "Fresh macOS qualification evidence is present."
                    if qualification["fresh"]
                    else "Live execution requires fresh local qualification evidence.",
                    "Run deterministic qualification, then opt-in live macOS qualification.",
                )
            )
        stage, live_enabled, reason_code = _derive_stage(
            config=self.config,
            provider=provider,
            capture=capture,
            input_state=input_state,
            qualification=qualification,
            screen_recording=screen_recording,
            accessibility=accessibility,
            opt_in=opt_in,
        )
        return self._report(
            platform.label,
            checks,
            stage=stage,
            live_enabled=live_enabled,
            reason_code=reason_code,
            permissions=_permissions_payload(
                screen_recording=screen_recording,
                accessibility=accessibility,
                input_monitoring="not_required",
            ),
            provider=provider,
            capture=capture,
            input_state=input_state,
            opt_in=opt_in,
            qualification=qualification,
        )

    @staticmethod
    def _report(
        platform: str,
        checks: list[dict[str, Any]],
        *,
        stage: str,
        live_enabled: bool,
        reason_code: str | None,
        permissions: dict[str, Any],
        provider: dict[str, Any],
        capture: dict[str, Any],
        input_state: dict[str, Any],
        opt_in: dict[str, Any],
        qualification: dict[str, Any],
    ) -> dict[str, Any]:
        blockers = _blockers_from_checks(checks)
        return {
            "runtime": "computer_use_vision",
            "platform": platform,
            "stage": stage,
            "liveEnabled": live_enabled,
            "reasonCode": reason_code,
            "permissions": permissions,
            "permissionSubjects": _permission_subjects(),
            "manualInstructions": _permission_manual_instructions(),
            "provider": provider,
            "capture": capture,
            "input": input_state,
            "optIn": opt_in,
            "qualification": qualification,
            "safety": {
                "privacyMode": True,
                "rawScreenshotPersistence": False,
                "rawScreenshotMaxCount": 0,
                "terminalPolicy": "deny",
                "sensitiveSurfacePolicy": "stop",
                "stepApprovalRequired": True,
                "supervisedFixtureOnly": True,
                "approvalFreshnessEnforced": True,
                "replayIntegrityEnforced": True,
            },
            "live_execution_allowed": live_enabled,
            "nextActions": _next_actions(blockers),
            "checks": checks,
        }


def _env_permission_status(
    environment: Mapping[str, str],
    *keys: str,
) -> str:
    for key in keys:
        value = environment.get(key)
        if value is None:
            continue
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "granted"}:
            return "granted"
        if normalized in {"0", "false", "no", "missing", "denied"}:
            return "missing"
        if normalized == "unknown":
            return "unknown"
    return "unknown"


def _provider_payload(
    *,
    configured: bool,
    name: str,
    model: str,
    strict_json: bool,
    ready: bool,
    reason_code: str | None,
) -> dict[str, Any]:
    return {
        "configured": configured,
        "kind": name,
        "name": name,
        "model": model,
        "strictJson": strict_json,
        "ready": ready,
        "reasonCode": reason_code,
    }


def _evaluate_provider(
    config: ComputerUseRuntimeConfig,
    *,
    which: Callable[[str], str | None],
) -> dict[str, Any]:
    configured = config.vision_enabled and config.vision_provider != "none"
    if not configured:
        return _provider_payload(
            configured=False,
            name=config.vision_provider,
            model=config.vision_model or "",
            strict_json=False,
            ready=False,
            reason_code="VISION_PROVIDER_UNAVAILABLE",
        )
    if not config.vision_model:
        return _provider_payload(
            configured=True,
            name=config.vision_provider,
            model="",
            strict_json=False,
            ready=False,
            reason_code="VISION_PROVIDER_MODEL_NOT_CONFIGURED",
        )
    if config.vision_provider != "ollama":
        return _provider_payload(
            configured=True,
            name=config.vision_provider,
            model=config.vision_model or "",
            strict_json=True,
            ready=False,
            reason_code="MACOS_PROVIDER_NOT_READY",
        )
    ready = bool(which("ollama"))
    return _provider_payload(
        configured=True,
        name="ollama",
        model=config.vision_model or "",
        strict_json=True,
        ready=ready,
        reason_code=None if ready else "VISION_PROVIDER_UNAVAILABLE",
    )


def _evaluate_capture(
    config: ComputerUseRuntimeConfig,
    *,
    which: Callable[[str], str | None],
    screen_recording: str,
) -> dict[str, Any]:
    backend = config.macos_capture_backend
    if backend == "disabled":
        return {
            "backend": backend,
            "ready": False,
            "reasonCode": "MACOS_CAPTURE_BACKEND_DISABLED",
        }
    tooling_ready = backend != "screencapture" or bool(which("screencapture"))
    if not tooling_ready:
        return {
            "backend": backend,
            "ready": False,
            "reasonCode": "MACOS_CAPTURE_BACKEND_UNAVAILABLE",
        }
    if screen_recording != "granted":
        return {
            "backend": backend,
            "ready": False,
            "reasonCode": "MACOS_SCREEN_RECORDING_PERMISSION_MISSING",
        }
    return {"backend": backend, "ready": True, "reasonCode": None}


def _evaluate_input(
    config: ComputerUseRuntimeConfig,
    *,
    accessibility: str,
    input_backend_available: bool | None,
) -> dict[str, Any]:
    backend = config.macos_input_backend
    if backend == "disabled":
        return {
            "backend": backend,
            "ready": False,
            "reasonCode": "MACOS_INPUT_BACKEND_DISABLED",
        }
    if accessibility != "granted":
        return {
            "backend": backend,
            "ready": False,
            "reasonCode": "MACOS_ACCESSIBILITY_PERMISSION_MISSING",
        }
    ready = input_backend_available if input_backend_available is not None else backend == "quartz"
    return {
        "backend": backend,
        "ready": bool(ready),
        "reasonCode": None if ready else "MACOS_INPUT_BACKEND_UNAVAILABLE",
    }


def _evaluate_qualification(
    config: ComputerUseRuntimeConfig,
    *,
    qualification_report: Mapping[str, Any] | None,
    commit: str | None,
) -> dict[str, Any]:
    if not config.platform_qualification_required:
        return _qualification_payload(
            required=False,
            present=False,
            valid=True,
            fresh=True,
            status="not_required",
            report_path=config.macos_qualification_report,
            reason_code=None,
        )
    if qualification_report is None:
        return _qualification_payload(
            required=True,
            present=False,
            valid=False,
            fresh=False,
            status="missing",
            report_path=config.macos_qualification_report,
            reason_code="MACOS_QUALIFICATION_REPORT_MISSING",
        )
    validation = validate_platform_qualification_report(
        qualification_report,
        platform="macos",
        config=config,
        commit=commit,
    )
    reason_code = validation.blockers[0] if validation.blockers else None
    return _qualification_payload(
        required=True,
        present=True,
        valid=validation.status != "invalid",
        fresh=validation.allowed,
        status=validation.status,
        report_path=config.macos_qualification_report,
        reason_code=reason_code,
    )


def _qualification_payload(
    *,
    required: bool,
    present: bool,
    valid: bool,
    fresh: bool,
    status: str,
    report_path: str,
    reason_code: str | None = None,
) -> dict[str, Any]:
    return {
        "required": required,
        "present": present,
        "valid": valid,
        "fresh": fresh,
        "status": status,
        "reportPath": report_path,
        "reasonCode": reason_code,
    }


def _permissions_payload(
    *,
    screen_recording: str,
    accessibility: str,
    input_monitoring: str,
) -> dict[str, Any]:
    return {
        "screenRecording": _permission_detail(
            status=screen_recording,
            required=True,
            reason_code="MACOS_SCREEN_RECORDING_PERMISSION_MISSING",
        ),
        "accessibility": _permission_detail(
            status=accessibility,
            required=True,
            reason_code="MACOS_ACCESSIBILITY_PERMISSION_MISSING",
        ),
        "inputMonitoring": _permission_detail(
            status=input_monitoring,
            required=False,
            reason_code=None,
        ),
        "permissionSubject": _permission_subject(),
    }


def _permission_detail(
    *,
    status: str,
    required: bool,
    reason_code: str | None,
) -> dict[str, Any]:
    return {
        "status": status,
        "required": required,
        "manualGrantRequired": required and status != "granted",
        "autoGrantAttempted": False,
        "reasonCode": None if status in {"granted", "not_required"} else reason_code,
    }


def _permission_subject() -> dict[str, str]:
    executable = Path(sys.executable)
    return {
        "process": executable.name or "python",
        "binary": str(executable),
        "note": (
            "Grant the app or terminal process that launches ImperaOS; this command "
            "does not grant permissions."
        ),
    }


def _permission_subjects() -> list[str]:
    return [
        "Terminal.app or the terminal app running uv/python",
        "Visual Studio Code if launching the runtime from VS Code",
        "ImperaOS operator shell if bundled",
    ]


def _permission_manual_instructions() -> list[str]:
    return [
        (
            "Open System Settings -> Privacy & Security -> Screen Recording and "
            "grant access to the process that runs ImperaOS."
        ),
        (
            "Open System Settings -> Privacy & Security -> Accessibility and "
            "grant access to the process that sends input events."
        ),
        "Quit and reopen the terminal/app after changing permissions.",
    ]


def _derive_stage(
    *,
    config: ComputerUseRuntimeConfig,
    provider: Mapping[str, Any],
    capture: Mapping[str, Any],
    input_state: Mapping[str, Any],
    qualification: Mapping[str, Any],
    screen_recording: str,
    accessibility: str,
    opt_in: Mapping[str, Any],
) -> tuple[str, bool, str | None]:
    if (
        config.raw_screenshot_persistence
        or config.raw_screenshot_retention != "disabled"
        or config.raw_screenshot_max_count != 0
    ):
        return "blocked", False, "RAW_SCREENSHOT_PERSISTENCE_DENIED"
    if config.terminal_control != "deny":
        return "blocked", False, "TERMINAL_CONTROL_DENIED"
    if config.sensitive_surface_policy != "stop":
        return "blocked", False, "SENSITIVE_SURFACE_BLOCKED"
    if not opt_in.get("present"):
        return "blocked", False, "MACOS_LIVE_OPT_IN_MISSING"
    if not opt_in.get("acknowledged"):
        return "blocked", False, "MACOS_LIVE_ACK_MISSING"
    if not opt_in.get("supervisedFixtureOnly"):
        return "blocked", False, "MACOS_SUPERVISED_FIXTURE_ONLY_REQUIRED"
    if not opt_in.get("stepApprovalRequired"):
        return "blocked", False, "MACOS_STEP_APPROVAL_REQUIRED"
    if not config.macos_live_enabled:
        stage = (
            "fixture_qualified_default_disabled"
            if qualification.get("fresh")
            else "not_configured"
        )
        return stage, False, "MACOS_LIVE_FLAG_DISABLED"
    if not config.vision_enabled:
        return "not_configured", False, "VISION_RUNTIME_DISABLED"
    if not capture.get("ready"):
        return "blocked", False, str(capture.get("reasonCode"))
    if not input_state.get("ready"):
        return "blocked", False, str(input_state.get("reasonCode"))
    if screen_recording != "granted":
        return "blocked", False, "MACOS_SCREEN_RECORDING_PERMISSION_MISSING"
    if accessibility != "granted":
        return "blocked", False, "MACOS_ACCESSIBILITY_PERMISSION_MISSING"
    if not provider.get("ready"):
        return "permission_ready", False, str(provider.get("reasonCode"))
    if qualification.get("required") and not qualification.get("fresh"):
        return "provider_ready", False, str(qualification.get("reasonCode"))
    if not config.macos_live_enabled:
        return "fixture_qualified_default_disabled", False, "MACOS_LIVE_FLAG_DISABLED"
    return "qualified_limited", True, None


def _blockers_from_checks(checks: list[dict[str, Any]]) -> list[str]:
    blockers: list[str] = []
    for check in checks:
        if check.get("ok") is True:
            continue
        reason = check.get("reason_code")
        if isinstance(reason, str) and reason not in blockers:
            blockers.append(reason)
    return blockers


def _next_actions(blockers: list[str]) -> list[dict[str, Any]]:
    descriptions = {
        "MACOS_LIVE_OPT_IN_MISSING": (
            "Set the documented macOS live fixture opt-in values for one supervised run."
        ),
        "MACOS_LIVE_ACK_MISSING": (
            "Set IMPERAOS_COMPUTER_USE_ACK to the documented acknowledgment string."
        ),
        "MACOS_SUPERVISED_FIXTURE_ONLY_REQUIRED": (
            "Set IMPERAOS_COMPUTER_USE_SUPERVISED_FIXTURE_ONLY=1."
        ),
        "MACOS_STEP_APPROVAL_REQUIRED": "Set IMPERAOS_COMPUTER_USE_REQUIRE_STEP_APPROVAL=1.",
        "VISION_RUNTIME_DISABLED": "Enable computer_use.vision_enabled for the run.",
        "VISION_PROVIDER_UNAVAILABLE": "Configure a local Ollama vision model.",
        "VISION_PROVIDER_MODEL_NOT_CONFIGURED": "Set computer_use.vision_model for the run.",
        "VISION_PROVIDER_MODEL_NOT_FOUND": "Install the configured local model manually.",
        "VISION_PROVIDER_NOT_VISION_CAPABLE": "Select a local model that accepts image input.",
        "MACOS_LIVE_FLAG_DISABLED": "Set computer_use.macos_live_enabled=true for the run.",
        "MACOS_CAPTURE_BACKEND_DISABLED": "Select an explicit macOS capture backend.",
        "MACOS_INPUT_BACKEND_DISABLED": "Select the quartz macOS input backend.",
        "MACOS_SCREEN_RECORDING_PERMISSION_MISSING": (
            "Grant Screen Recording manually in macOS System Settings."
        ),
        "MACOS_ACCESSIBILITY_PERMISSION_MISSING": (
            "Grant Accessibility manually in macOS System Settings."
        ),
    }
    return [
        {
            "id": blocker.lower(),
            "manual": True,
            "description": descriptions.get(blocker, blocker),
        }
        for blocker in blockers
    ]


class MacOSScreenCaptureProvider:
    def __init__(
        self,
        *,
        config: ComputerUseRuntimeConfig,
        job_dir: Path,
        raw_screenshot_opt_in: bool = False,
        environment: Mapping[str, str] | None = None,
        runner: Callable[..., Any] = subprocess.run,
        now: Callable[[], str] | None = None,
    ) -> None:
        self.config = config
        self.job_dir = Path(job_dir)
        self.raw_screenshot_opt_in = raw_screenshot_opt_in
        self.environment = dict(environment or os.environ)
        self.runner = runner
        self.now = now or (lambda: datetime.now(UTC).isoformat())
        self._persisted_count = 0

    def capture(self) -> VisionObservation:
        if self.config.macos_capture_backend != "screencapture":
            reason = (
                "MACOS_CAPTURE_BACKEND_DISABLED"
                if self.config.macos_capture_backend == "disabled"
                else "MACOS_CAPTURE_BACKEND_UNAVAILABLE"
            )
            raise VisionRuntimeError(
                reason,
                "Only the screencapture backend is currently implemented.",
            )
        opt_in = macos_opt_in_state(self.environment)
        if not self.config.macos_live_enabled:
            raise VisionRuntimeError(
                "MACOS_LIVE_FLAG_DISABLED",
                "macOS capture requires one-run live enablement.",
            )
        if not opt_in["present"]:
            raise VisionRuntimeError(
                "MACOS_LIVE_OPT_IN_MISSING",
                "macOS capture requires exact one-run opt-in.",
            )
        screen_recording = _env_permission_status(
            self.environment,
            "IMPERAOS_COMPUTER_USE_MACOS_SCREEN_RECORDING",
            "IMPERAOS_TEST_MACOS_SCREEN_RECORDING",
        )
        if screen_recording == "missing":
            raise VisionRuntimeError(
                "MACOS_SCREEN_RECORDING_PERMISSION_MISSING",
                "Screen Recording permission is missing.",
            )
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            capture_path = Path(tmp.name)
        try:
            try:
                proc = self.runner(
                    ["screencapture", "-x", "-t", "png", str(capture_path)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
            except FileNotFoundError as exc:
                raise VisionRuntimeError(
                    "MACOS_CAPTURE_BACKEND_UNAVAILABLE",
                    "macOS screencapture command is unavailable.",
                ) from exc
            if proc.returncode != 0:
                stderr = str(getattr(proc, "stderr", ""))
                reason = (
                    "MACOS_SCREEN_RECORDING_PERMISSION_MISSING"
                    if "permission" in stderr.lower() or "not authorized" in stderr.lower()
                    else "MACOS_CAPTURE_BACKEND_UNAVAILABLE"
                )
                raise VisionRuntimeError(reason, stderr or "screencapture failed")
            data = capture_path.read_bytes()
            screenshot_hash = hashlib.sha256(data).hexdigest()
            dimensions = _png_dimensions(data)
            persisted_path = self._maybe_persist(data)
            return VisionObservation(
                screenshot_hash=screenshot_hash,
                raw_screenshot_path=str(persisted_path) if persisted_path else None,
                captured_at=self.now(),
                platform="macos",
                image_width=dimensions[0] if dimensions else None,
                image_height=dimensions[1] if dimensions else None,
                confidence=1.0,
            )
        finally:
            capture_path.unlink(missing_ok=True)

    def _maybe_persist(self, data: bytes) -> Path | None:
        allowed = (
            self.raw_screenshot_opt_in
            and self.config.raw_screenshot_persistence
            and self.config.raw_screenshot_retention == "explicit_opt_in"
            and self.config.raw_screenshot_max_count > self._persisted_count
        )
        if not allowed:
            return None
        screenshots_dir = self.job_dir / "screenshots"
        screenshots_dir.mkdir(parents=True, exist_ok=True)
        path = screenshots_dir / f"screen-{self._persisted_count + 1:04d}.png"
        path.write_bytes(data)
        self._persisted_count += 1
        return path


class MacOSInputExecutor:
    def __init__(
        self,
        *,
        config: ComputerUseRuntimeConfig,
        display_bounds: DisplayBounds | None = None,
        environment: Mapping[str, str] | None = None,
        quartz_backend: Any | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.config = config
        self.display_bounds = display_bounds or DisplayBounds(width=1440, height=900)
        self.environment = dict(environment or os.environ)
        self.quartz_backend = quartz_backend
        self.sleeper = sleeper

    def execute(self, action: VisionAction) -> ExecutionResult:
        started = time.perf_counter()
        if self.config.macos_input_backend == "disabled":
            return self._failed(action, "MACOS_INPUT_BACKEND_DISABLED", started)
        if not self.config.macos_live_enabled:
            return self._blocked(action, "MACOS_LIVE_FLAG_DISABLED", started)
        opt_in = macos_opt_in_state(self.environment)
        if not opt_in["present"]:
            return self._blocked(action, "MACOS_LIVE_OPT_IN_MISSING", started)
        if not opt_in["supervisedFixtureOnly"]:
            return self._blocked(action, "MACOS_SUPERVISED_FIXTURE_ONLY_REQUIRED", started)
        if not opt_in["stepApprovalRequired"]:
            return self._blocked(action, "MACOS_STEP_APPROVAL_REQUIRED", started)
        accessibility = _env_permission_status(
            self.environment,
            "IMPERAOS_COMPUTER_USE_MACOS_ACCESSIBILITY",
            "IMPERAOS_TEST_MACOS_ACCESSIBILITY",
        )
        if accessibility == "missing":
            return self._blocked(
                action,
                "MACOS_ACCESSIBILITY_PERMISSION_MISSING",
                started,
            )
        if action.action_type.value not in self.config.action_set:
            return self._blocked(action, "COMPUTER_USE_APPROVAL_REQUIRED", started)
        if action.action_type in {
            InputActionType.TYPE_TEXT,
            InputActionType.PRESS_KEY,
            InputActionType.HOTKEY,
            InputActionType.FOCUS_WINDOW_OR_APP,
        }:
            return self._blocked(action, "COMPUTER_USE_APPROVAL_REQUIRED", started)
        if action.action_type == InputActionType.WAIT:
            wait_ms = min(action.wait_ms or 250, self.config.max_action_duration_ms)
            self.sleeper(wait_ms / 1000)
            return self._executed(action, started, {"wait_ms": wait_ms})
        if self.config.macos_input_backend != "quartz" or self.quartz_backend is None:
            return self._failed(action, "MACOS_INPUT_BACKEND_UNAVAILABLE", started)
        if action.target_bbox is None and action.action_type in {
            InputActionType.MOVE_MOUSE,
            InputActionType.CLICK,
            InputActionType.DOUBLE_CLICK,
            InputActionType.RIGHT_CLICK,
        }:
            return self._blocked(action, "VISION_CONFIDENCE_BELOW_THRESHOLD", started)
        if action.target_bbox is not None and not _bbox_within_unit_bounds(action.target_bbox):
            return self._blocked(action, "MACOS_INPUT_TARGET_OUT_OF_BOUNDS", started)
        if action.action_type == InputActionType.HOTKEY and _hotkey_denied(action.hotkey):
            return self._blocked(action, "COMPUTER_USE_APPROVAL_REQUIRED", started)

        point = (
            normalized_bbox_center_to_pixel(action.target_bbox, self.display_bounds)
            if action.target_bbox is not None
            else (self.display_bounds.origin_x, self.display_bounds.origin_y)
        )
        if action.action_type == InputActionType.MOVE_MOUSE:
            self.quartz_backend.move_mouse(*point)
        elif action.action_type == InputActionType.CLICK:
            self.quartz_backend.click(*point, clicks=1)
        elif action.action_type == InputActionType.DOUBLE_CLICK:
            self.quartz_backend.click(*point, clicks=2)
        elif action.action_type == InputActionType.RIGHT_CLICK:
            self.quartz_backend.click(*point, clicks=1, button="right")
        elif action.action_type == InputActionType.SCROLL:
            delta = max(min(action.scroll_delta or 0, 1200), -1200)
            if hasattr(self.quartz_backend, "scroll"):
                self.quartz_backend.scroll(delta)
        return self._executed(action, started, {"point": point})

    def _executed(
        self,
        action: VisionAction,
        started: float,
        details: dict[str, Any],
    ) -> ExecutionResult:
        return ExecutionResult(
            status="executed",
            message="macOS input action executed.",
            details={
                "action_id": action.action_id,
                "duration_ms": _duration_ms(started),
                "redacted": True,
                **details,
            },
        )

    def _failed(self, action: VisionAction, reason_code: str, started: float) -> ExecutionResult:
        return ExecutionResult(
            status="failed",
            message=reason_code,
            details={
                "action_id": action.action_id,
                "reason_code": reason_code,
                "duration_ms": _duration_ms(started),
                "redacted": True,
            },
        )

    def _blocked(self, action: VisionAction, reason_code: str, started: float) -> ExecutionResult:
        return ExecutionResult(
            status="blocked",
            message=reason_code,
            details={
                "action_id": action.action_id,
                "reason_code": reason_code,
                "duration_ms": _duration_ms(started),
                "redacted": True,
            },
        )


def normalized_bbox_center_to_pixel(
    bbox: NormalizedBBox,
    bounds: DisplayBounds,
) -> tuple[int, int]:
    raw_x = bounds.origin_x + round((bbox.x + bbox.w / 2) * bounds.width)
    raw_y = bounds.origin_y + round((bbox.y + bbox.h / 2) * bounds.height)
    return (
        max(bounds.origin_x, min(bounds.origin_x + bounds.width - 1, raw_x)),
        max(bounds.origin_y, min(bounds.origin_y + bounds.height - 1, raw_y)),
    )


def _bbox_within_unit_bounds(bbox: NormalizedBBox) -> bool:
    return bbox.x + bbox.w <= 1.0 and bbox.y + bbox.h <= 1.0


def _check(
    key: str,
    ok: bool,
    reason_code: str | None,
    summary: str,
    remediation: str,
) -> dict[str, Any]:
    return {
        "key": key,
        "ok": ok,
        "reason_code": None if ok else reason_code,
        "summary": summary,
        "remediation": remediation,
    }


def _duration_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _png_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")


def _hotkey_denied(keys: list[str]) -> bool:
    normalized = {key.strip().lower() for key in keys}
    denied = [
        {"cmd", "q"},
        {"cmd", "delete"},
        {"cmd", "shift", "delete"},
    ]
    return any(combo.issubset(normalized) for combo in denied)
