from __future__ import annotations

import pytest
from pydantic import ValidationError

from imperaos.computer_use.models import RiskClass
from imperaos.computer_use.vision_runtime.models import (
    InputActionType,
    NormalizedBBox,
    SurfaceKind,
    UiElement,
    VisionAction,
    VisionObservation,
    VisionRunArtifact,
)
from imperaos.runtime.config import ComputerUseRuntimeConfig, RuntimeConfig, resolve_runtime_config


def test_computer_use_runtime_config_defaults_are_safe() -> None:
    config = ComputerUseRuntimeConfig()

    assert config.enabled is True
    assert config.runtime_mode == "legacy_pilot"
    assert config.vision_enabled is False
    assert config.vision_provider == "none"
    assert config.vision_model is None
    assert config.macos_live_enabled is False
    assert config.macos_input_backend == "disabled"
    assert config.default_mode == "step_approval"
    assert config.raw_screenshot_retention == "disabled"
    assert config.raw_screenshot_max_count == 0
    assert config.terminal_control == "deny"
    assert config.platform_qualification_required is True


def test_runtime_config_loads_computer_use_profile_block_and_env_override() -> None:
    resolved, source_map = resolve_runtime_config(
        profile="balanced",
        root_dir=None,
        env={
            "IMPERAOS_COMPUTER_USE_RUNTIME_MODE": "vision_first",
            "IMPERAOS_COMPUTER_USE_VISION_ENABLED": "true",
            "IMPERAOS_COMPUTER_USE_VISION_PROVIDER": "mock",
            "IMPERAOS_COMPUTER_USE_MACOS_LIVE_ENABLED": "true",
            "IMPERAOS_COMPUTER_USE_MAX_STEPS": "12",
        },
    )

    assert isinstance(resolved, RuntimeConfig)
    assert resolved.computer_use.runtime_mode == "vision_first"
    assert resolved.computer_use.vision_enabled is True
    assert resolved.computer_use.vision_provider == "mock"
    assert resolved.computer_use.macos_live_enabled is True
    assert resolved.computer_use.max_steps == 12
    assert source_map["computer_use.runtime_mode"] == "env"
    assert source_map["computer_use.vision_enabled"] == "env"


def test_vision_models_are_strict_and_hash_only_by_default() -> None:
    bbox = NormalizedBBox(x=0.1, y=0.2, w=0.3, h=0.4)
    observation = VisionObservation(
        screenshot_hash="a" * 64,
        captured_at="2026-05-05T00:00:00+00:00",
        platform="macos",
        active_app="Safari",
        surface_kind=SurfaceKind.BROWSER,
        ui_elements=[
            UiElement(
                element_id="button-1",
                label="Continue",
                role="button",
                bbox=bbox,
                confidence=0.93,
            )
        ],
        confidence=0.91,
    )

    assert observation.raw_screenshot_path is None
    assert observation.ui_elements[0].bbox.x == 0.1

    with pytest.raises(ValidationError):
        VisionObservation(
            screenshot_hash="a" * 64,
            captured_at="2026-05-05T00:00:00+00:00",
            platform="macos",
            confidence=0.91,
            unexpected="not allowed",
        )


def test_vision_action_and_run_artifact_contracts() -> None:
    action = VisionAction(
        action_id="act-1",
        action_type=InputActionType.CLICK,
        target_bbox=NormalizedBBox(x=0.1, y=0.2, w=0.3, h=0.1),
        rationale="Open the export menu.",
        expected_effect="Menu opens.",
        risk_class=RiskClass.MEDIUM,
        requires_approval=True,
        confidence=0.88,
    )
    artifact = VisionRunArtifact(
        job_id="job-1",
        status="awaiting_approval",
        objective="Open export menu",
        steps=[],
        redaction_report={"raw_screenshot_persisted_count": 0},
        integrity={"hash_chain_verified": True},
    )

    assert action.action_type == InputActionType.CLICK
    assert action.requires_approval is True
    assert artifact.artifact_version == "computer_use_vision/v1"
    assert artifact.redaction_report["raw_screenshot_persisted_count"] == 0
