from __future__ import annotations

from imperaos.computer_use.vision_runtime.platforms import (
    ComputerUsePlatform,
    build_platform_capabilities,
)
from imperaos.computer_use.vision_runtime.qualification import platform_config_hash
from imperaos.runtime.config import ComputerUseRuntimeConfig


def test_default_config_reports_all_platforms_fail_closed() -> None:
    capabilities = build_platform_capabilities(ComputerUseRuntimeConfig())

    assert set(capabilities) == {"macos", "windows", "linux"}
    for platform, capability in capabilities.items():
        assert capability.platform == platform
        assert capability.stage == "not_qualified"
        assert capability.live_enabled is False
        assert capability.execution_modes == ["dry_run", "step_approval"]
        assert capability.replayable is True
        assert capability.fail_closed is True

    assert capabilities["macos"].reason_code == "MACOS_COMPUTER_USE_NOT_QUALIFIED"
    assert capabilities["windows"].reason_code == "WINDOWS_COMPUTER_USE_NOT_QUALIFIED"
    assert capabilities["linux"].reason_code == "LINUX_COMPUTER_USE_NOT_QUALIFIED"


def test_platform_capability_serializes_with_operator_contract_aliases() -> None:
    capability = build_platform_capabilities(ComputerUseRuntimeConfig())[
        ComputerUsePlatform.WINDOWS.value
    ]
    payload = capability.model_dump(mode="json", by_alias=True)

    assert payload["liveEnabled"] is False
    assert payload["captureBackend"] == "disabled"
    assert payload["inputBackend"] == "disabled"
    assert payload["reasonCode"] == "WINDOWS_COMPUTER_USE_NOT_QUALIFIED"
    assert payload["failClosed"] is True


def test_macos_qualified_report_without_live_flag_is_fixture_qualified() -> None:
    config = ComputerUseRuntimeConfig(
        vision_enabled=True,
        vision_provider="ollama",
        vision_model="llava",
        macos_capture_backend="screencapture",
        macos_input_backend="quartz",
        macos_live_enabled=False,
    )
    report = {
        "schemaVersion": "1.0",
        "platform": "macos",
        "status": "pass",
        "stage": "fixture_qualified_default_disabled",
        "commitSha": "abc123",
        "configHash": platform_config_hash(config, platform="macos"),
        "generatedAt": "2026-05-05T00:00:00+00:00",
        "expiresAt": "2099-05-05T00:00:00+00:00",
        "provider": {"name": "ollama", "model": "llava", "strictJson": True},
        "permissions": {"screenRecording": True, "accessibility": True},
        "backends": {"capture": "screencapture", "input": "quartz"},
        "safety": {
            "rawScreenshotPersistenceDefault": False,
            "rawScreenshotMaxCountDefault": 0,
            "terminalPolicy": "deny",
            "sensitiveSurfacePolicy": "stop",
            "approvalFreshnessEnforced": True,
            "replayIntegrityEnforced": True,
        },
        "tasks": [{"id": "fixture", "status": "pass"}],
        "blockers": [],
    }

    capability = build_platform_capabilities(
        config,
        qualification_reports={"macos": report},
        commit="abc123",
    )["macos"]

    assert capability.stage == "fixture_qualified_default_disabled"
    assert capability.live_enabled is False
    assert capability.execution_modes == ["dry_run", "step_approval", "supervised_fixture"]
    assert capability.fixture_qualified is True
    assert capability.production_qualified is False
    assert capability.reason_code == "MACOS_FIXTURE_QUALIFIED_DEFAULT_DISABLED"
