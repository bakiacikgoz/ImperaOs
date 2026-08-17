from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from imperaos.computer_use.models import RiskClass
from imperaos.computer_use.vision_runtime.drivers.macos import (
    DisplayBounds,
    MacOSInputExecutor,
    MacOSScreenCaptureProvider,
    MacOSVisionReadiness,
    normalized_bbox_center_to_pixel,
)
from imperaos.computer_use.vision_runtime.errors import VisionRuntimeError
from imperaos.computer_use.vision_runtime.models import (
    InputActionType,
    NormalizedBBox,
    VisionAction,
)
from imperaos.runtime.config import ComputerUseRuntimeConfig
from imperaos.runtime.platform import PlatformInfo

ACK = "I understand ImperaOS will control my macOS desktop only for local supervised fixtures."


def _live_env(**updates: str) -> dict[str, str]:
    values = {
        "IMPERAOS_COMPUTER_USE_LIVE_MACOS": "1",
        "IMPERAOS_COMPUTER_USE_ACK": ACK,
        "IMPERAOS_COMPUTER_USE_SUPERVISED_FIXTURE_ONLY": "1",
        "IMPERAOS_COMPUTER_USE_REQUIRE_STEP_APPROVAL": "1",
        "IMPERAOS_COMPUTER_USE_MACOS_SCREEN_RECORDING": "granted",
        "IMPERAOS_COMPUTER_USE_MACOS_ACCESSIBILITY": "granted",
    }
    values.update(updates)
    return values


def _action(action_type: InputActionType = InputActionType.CLICK) -> VisionAction:
    return VisionAction(
        action_id="act-1",
        action_type=action_type,
        target_bbox=NormalizedBBox(x=0.25, y=0.25, w=0.5, h=0.5),
        text="safe",
        hotkey=["cmd", "q"] if action_type == InputActionType.HOTKEY else [],
        rationale="Exercise macOS driver policy.",
        expected_effect="A safe fixture changes state.",
        risk_class=RiskClass.LOW,
        requires_approval=False,
        confidence=0.95,
    )


def test_macos_readiness_blocks_non_macos_live_request() -> None:
    report = MacOSVisionReadiness(
        ComputerUseRuntimeConfig(
            runtime_mode="vision_first",
            vision_enabled=True,
            vision_provider="ollama",
            vision_model="llava",
            macos_live_enabled=True,
        )
    ).evaluate(
        platform_info=PlatformInfo(system="Windows", label="windows", machine="x64", release="11")
    )

    assert report["live_execution_allowed"] is False
    assert report["checks"][0]["reason_code"] == "WINDOWS_COMPUTER_USE_NOT_QUALIFIED"


def test_screencapture_hashes_bytes_and_deletes_temp_by_default(tmp_path: Path) -> None:
    captured_paths: list[Path] = []

    def fake_runner(args, capture_output, text, check):  # noqa: ANN001
        del capture_output, text, check
        capture_path = Path(args[-1])
        captured_paths.append(capture_path)
        capture_path.write_bytes(b"\x89PNG\r\n\x1a\nfixture")
        return SimpleNamespace(returncode=0, stderr="")

    provider = MacOSScreenCaptureProvider(
        config=ComputerUseRuntimeConfig(
            macos_live_enabled=True,
            macos_capture_backend="screencapture",
        ),
        job_dir=tmp_path / "job",
        raw_screenshot_opt_in=False,
        environment=_live_env(),
        runner=fake_runner,
        now=lambda: "2026-05-05T00:00:00+00:00",
    )

    observation = provider.capture()

    assert len(observation.screenshot_hash) == 64
    assert observation.raw_screenshot_path is None
    assert captured_paths and not captured_paths[0].exists()


def test_capture_backend_unavailable_fails_closed(tmp_path: Path) -> None:
    def missing_runner(args, capture_output, text, check):  # noqa: ANN001
        del args, capture_output, text, check
        raise FileNotFoundError("screencapture")

    provider = MacOSScreenCaptureProvider(
        config=ComputerUseRuntimeConfig(
            macos_live_enabled=True,
            macos_capture_backend="screencapture",
        ),
        job_dir=tmp_path / "job",
        environment=_live_env(),
        runner=missing_runner,
    )

    try:
        provider.capture()
    except VisionRuntimeError as exc:
        assert exc.reason_code == "MACOS_CAPTURE_BACKEND_UNAVAILABLE"
    else:  # pragma: no cover
        raise AssertionError("expected fail-closed capture error")


def test_capture_backend_requires_live_opt_in(tmp_path: Path) -> None:
    provider = MacOSScreenCaptureProvider(
        config=ComputerUseRuntimeConfig(
            macos_live_enabled=True,
            macos_capture_backend="screencapture",
        ),
        job_dir=tmp_path / "job",
        environment={},
    )

    try:
        provider.capture()
    except VisionRuntimeError as exc:
        assert exc.reason_code == "MACOS_LIVE_OPT_IN_MISSING"
    else:  # pragma: no cover
        raise AssertionError("expected live opt-in capture error")


def test_capture_backend_blocks_missing_screen_recording(tmp_path: Path) -> None:
    provider = MacOSScreenCaptureProvider(
        config=ComputerUseRuntimeConfig(
            macos_live_enabled=True,
            macos_capture_backend="screencapture",
        ),
        job_dir=tmp_path / "job",
        environment=_live_env(IMPERAOS_COMPUTER_USE_MACOS_SCREEN_RECORDING="missing"),
    )

    try:
        provider.capture()
    except VisionRuntimeError as exc:
        assert exc.reason_code == "MACOS_SCREEN_RECORDING_PERMISSION_MISSING"
    else:  # pragma: no cover
        raise AssertionError("expected screen recording permission error")


def test_capture_backend_disabled_fails_closed(tmp_path: Path) -> None:
    provider = MacOSScreenCaptureProvider(
        config=ComputerUseRuntimeConfig(),
        job_dir=tmp_path / "job",
    )

    try:
        provider.capture()
    except VisionRuntimeError as exc:
        assert exc.reason_code == "MACOS_CAPTURE_BACKEND_DISABLED"
    else:  # pragma: no cover
        raise AssertionError("expected disabled capture backend error")


def test_normalized_bbox_to_pixel_clamps_to_display_bounds() -> None:
    point = normalized_bbox_center_to_pixel(
        NormalizedBBox(x=0.95, y=0.95, w=0.2, h=0.2),
        DisplayBounds(width=100, height=50),
    )

    assert point == (99, 49)


def test_macos_input_executor_requires_quartz_backend() -> None:
    executor = MacOSInputExecutor(
        config=ComputerUseRuntimeConfig(
            macos_live_enabled=True,
            macos_input_backend="quartz",
        ),
        environment=_live_env(),
        quartz_backend=None,
    )

    result = executor.execute(_action())

    assert result.status == "failed"
    assert result.details["reason_code"] == "MACOS_INPUT_BACKEND_UNAVAILABLE"


def test_macos_input_executor_blocks_out_of_bounds_target() -> None:
    executor = MacOSInputExecutor(
        config=ComputerUseRuntimeConfig(
            macos_live_enabled=True,
            macos_input_backend="quartz",
        ),
        environment=_live_env(),
        quartz_backend=SimpleNamespace(move_mouse=lambda *_: None, click=lambda *_: None),
    )
    action = _action().model_copy(
        update={"target_bbox": NormalizedBBox(x=0.95, y=0.95, w=0.1, h=0.1)}
    )

    result = executor.execute(action)

    assert result.status == "blocked"
    assert result.details["reason_code"] == "MACOS_INPUT_TARGET_OUT_OF_BOUNDS"


def test_macos_input_executor_blocks_risky_hotkey_even_with_backend() -> None:
    executor = MacOSInputExecutor(
        config=ComputerUseRuntimeConfig(
            macos_live_enabled=True,
            macos_input_backend="quartz",
        ),
        environment=_live_env(),
        quartz_backend=SimpleNamespace(move_mouse=lambda *_: None, click=lambda *_: None),
    )

    result = executor.execute(_action(InputActionType.HOTKEY))

    assert result.status == "blocked"
    assert result.details["reason_code"] == "COMPUTER_USE_APPROVAL_REQUIRED"


def test_macos_input_executor_requires_live_opt_in() -> None:
    executor = MacOSInputExecutor(
        config=ComputerUseRuntimeConfig(
            macos_live_enabled=True,
            macos_input_backend="quartz",
        ),
        environment={},
        quartz_backend=SimpleNamespace(move_mouse=lambda *_: None, click=lambda *_: None),
    )

    result = executor.execute(_action())

    assert result.status == "blocked"
    assert result.details["reason_code"] == "MACOS_LIVE_OPT_IN_MISSING"


def test_macos_input_executor_blocks_missing_accessibility() -> None:
    executor = MacOSInputExecutor(
        config=ComputerUseRuntimeConfig(
            macos_live_enabled=True,
            macos_input_backend="quartz",
        ),
        environment=_live_env(IMPERAOS_COMPUTER_USE_MACOS_ACCESSIBILITY="missing"),
        quartz_backend=SimpleNamespace(move_mouse=lambda *_: None, click=lambda *_: None),
    )

    result = executor.execute(_action())

    assert result.status == "blocked"
    assert result.details["reason_code"] == "MACOS_ACCESSIBILITY_PERMISSION_MISSING"
