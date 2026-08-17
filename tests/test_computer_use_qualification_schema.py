from __future__ import annotations

from datetime import UTC, datetime, timedelta

from imperaos import __version__
from imperaos.computer_use.vision_runtime.qualification import (
    platform_config_hash,
    validate_platform_qualification_report,
)
from imperaos.runtime.config import ComputerUseRuntimeConfig


def _valid_report(
    *,
    platform: str = "windows",
    commit: str = "abc123",
    config: ComputerUseRuntimeConfig | None = None,
) -> dict[str, object]:
    runtime_config = config or ComputerUseRuntimeConfig(
        vision_enabled=True,
        vision_provider="mock",
        windows_live_enabled=True,
        windows_capture_backend="mock",
        windows_input_backend="mock",
    )
    return {
        "schemaVersion": "computer-use-platform-qualification/v1",
        "status": "pass",
        "platform": platform,
        "sessionType": platform,
        "commit": commit,
        "configHash": platform_config_hash(runtime_config, platform=platform),
        "runtimeVersion": __version__,
        "provider": {"name": "mock", "model": None, "strictJson": True},
        "permissions": {"screenCapture": "granted", "accessibilityOrInput": "granted"},
        "backends": {"capture": "mock", "input": "mock"},
        "environment": {
            "osVersion": "test",
            "architecture": "x86_64",
            "displayScaling": "unknown",
            "multiDisplay": "unknown",
        },
        "taskSuite": {"name": "safe-local-fixtures", "total": 1, "passed": 1, "failed": 0},
        "safety": {
            "sensitiveSurfaceBlocked": True,
            "terminalDeniedByDefault": True,
            "rawScreenshotsPersisted": 0,
            "approvalFreshnessEnforced": True,
            "replayIntegrityVerified": True,
        },
        "evidence": [],
        "blockers": [],
    }


def test_platform_qualification_report_passes_when_platform_commit_and_config_match() -> None:
    config = ComputerUseRuntimeConfig(
        vision_enabled=True,
        vision_provider="mock",
        windows_live_enabled=True,
        windows_capture_backend="mock",
        windows_input_backend="mock",
    )
    result = validate_platform_qualification_report(
        _valid_report(config=config),
        platform="windows",
        config=config,
        commit="abc123",
    )

    assert result.allowed is True
    assert result.status == "pass"
    assert result.blockers == []


def test_platform_mismatch_fails_closed() -> None:
    result = validate_platform_qualification_report(
        _valid_report(platform="macos"),
        platform="windows",
        config=ComputerUseRuntimeConfig(),
        commit="abc123",
    )

    assert result.allowed is False
    assert "VISION_PLATFORM_QUALIFICATION_PLATFORM_MISMATCH" in result.blockers


def test_stale_commit_or_config_mismatch_fails_closed() -> None:
    report = _valid_report(commit="old")
    result = validate_platform_qualification_report(
        report,
        platform="windows",
        config=ComputerUseRuntimeConfig(),
        commit="new",
    )

    assert result.allowed is False
    assert "VISION_PLATFORM_QUALIFICATION_STALE" in result.blockers
    assert "VISION_PLATFORM_QUALIFICATION_CONFIG_MISMATCH" in result.blockers


def _valid_macos_report(
    *,
    commit: str = "abc123",
    config: ComputerUseRuntimeConfig | None = None,
    expires_at: datetime | None = None,
) -> tuple[ComputerUseRuntimeConfig, dict[str, object]]:
    runtime_config = config or ComputerUseRuntimeConfig(
        vision_enabled=True,
        vision_provider="ollama",
        vision_model="llava",
        macos_capture_backend="screencapture",
        macos_input_backend="quartz",
    )
    now = datetime.now(UTC)
    return runtime_config, {
        "schemaVersion": "1.0",
        "platform": "macos",
        "status": "pass",
        "scope": "supervised_local_fixtures",
        "suite": "live-fixture-smoke",
        "mode": "supervised",
        "stage": "fixture_qualified_default_disabled",
        "qualificationStatus": "passed",
        "qualificationPassed": True,
        "fixtureQualified": True,
        "productionQualified": False,
        "liveEnabled": False,
        "liveEnabledDefault": False,
        "replayIntegrityStatus": "passed",
        "replayIntegrityVerified": True,
        "auditHashChainVerified": True,
        "reasonCode": None,
        "commit": commit,
        "commitSha": commit,
        "configHash": platform_config_hash(runtime_config, platform="macos"),
        "createdAt": now.isoformat(),
        "generatedAt": now.isoformat(),
        "expiresAt": (expires_at or (now + timedelta(hours=1))).isoformat(),
        "host": {"os": "macos", "version": "test", "arch": "arm64"},
        "machine": {
            "osVersion": "test",
            "arch": "arm64",
            "displayCount": 1,
            "scaleFactors": [2.0],
        },
        "provider": {
            "name": "ollama",
            "model": "llava",
            "strictJson": True,
            "strictJsonValidated": True,
            "ready": True,
        },
        "optIn": {"present": True, "source": "env", "required": True},
        "readiness": {"readyForLiveFixture": True},
        "permissions": {
            "screenRecording": "granted",
            "accessibility": "granted",
            "inputMonitoring": "not_required",
        },
        "capture": {
            "backend": "screencapture",
            "ready": True,
            "reasonCode": None,
            "rawPersistedCount": 0,
        },
        "input": {"backend": "quartz", "ready": True, "reasonCode": None},
        "backends": {"capture": "screencapture", "input": "quartz"},
        "safety": {
            "visionEnabledDefault": False,
            "rawScreenshotPersistence": False,
            "rawScreenshotPersistenceDefault": False,
            "rawScreenshotRetention": "disabled",
            "rawScreenshotMaxCountDefault": 0,
            "rawScreenshotPersistedCount": 0,
            "terminalPolicy": "deny",
            "sensitiveSurfacePolicy": "stop",
            "approvalFreshnessEnforced": True,
            "replayIntegrityVerified": True,
            "replayIntegrityEnforced": True,
        },
        "tasks": [
            {
                "id": "local_textedit_type_verify",
                "status": "pass",
                "steps": 1,
                "forbiddenActions": 0,
                "approvalStops": 0,
            }
        ],
        "fixtures": [
            {
                "id": "local_browser_form",
                "status": "pass",
                "stepsAttempted": 1,
                "stepsSucceeded": 1,
                "reasonCode": None,
            },
            {
                "id": "textedit_safe_typing",
                "status": "pass",
                "stepsAttempted": 1,
                "stepsSucceeded": 1,
                "reasonCode": None,
            },
            {
                "id": "finder_fixture_file",
                "status": "pass",
                "stepsAttempted": 1,
                "stepsSucceeded": 1,
                "reasonCode": None,
            },
            {
                "id": "sensitive_surface_stop",
                "status": "blocked_expected",
                "stepsAttempted": 0,
                "stepsSucceeded": 0,
                "inputExecuted": False,
                "reasonCode": "SENSITIVE_SURFACE_STOP",
            },
            {
                "id": "terminal_deny",
                "status": "blocked_expected",
                "stepsAttempted": 0,
                "stepsSucceeded": 0,
                "terminalExecuted": False,
                "reasonCode": "TERMINAL_POLICY_DENY",
            },
        ],
        "artifacts": {
            "replayPath": "artifacts/replay.jsonl",
            "auditPath": "artifacts/audit.json",
            "eventLogPath": "artifacts/events.jsonl",
            "rawScreenshotCount": 0,
            "screenshotHashesOnly": True,
        },
        "limitations": ["supervised local fixtures only"],
        "blockers": [],
    }


def test_macos_phase4a_report_passes_when_fresh_commit_and_config_match() -> None:
    config, report = _valid_macos_report()

    result = validate_platform_qualification_report(
        report,
        platform="macos",
        config=config,
        commit="abc123",
    )

    assert result.allowed is True
    assert result.blockers == []


def test_macos_phase4a_report_fails_closed_when_stale_or_config_mismatched() -> None:
    config, report = _valid_macos_report(
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )

    result = validate_platform_qualification_report(
        report,
        platform="macos",
        config=config.model_copy(update={"macos_step_delay_ms": 200}),
        commit="new",
    )

    assert result.allowed is False
    assert "MACOS_QUALIFICATION_REPORT_STALE" in result.blockers
    assert "MACOS_QUALIFICATION_COMMIT_MISMATCH" in result.blockers
    assert "MACOS_QUALIFICATION_CONFIG_MISMATCH" in result.blockers
