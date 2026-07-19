from __future__ import annotations

import pytest

from imperaos.computer_use.vision_runtime.drivers import windows
from imperaos.computer_use.vision_runtime.errors import VisionRuntimeError
from imperaos.runtime.config import ComputerUseRuntimeConfig


def test_windows_gate_reports_not_qualified_without_evidence() -> None:
    capability = windows.readiness_report(ComputerUseRuntimeConfig())

    assert capability.platform == "windows"
    assert capability.stage == "not_qualified"
    assert capability.live_enabled is False
    assert capability.capture_backend == "disabled"
    assert capability.input_backend == "disabled"
    assert capability.reason_code == "WINDOWS_COMPUTER_USE_NOT_QUALIFIED"
    assert "WINDOWS_CAPTURE_BACKEND_DISABLED" in capability.blockers
    assert "WINDOWS_INPUT_BACKEND_DISABLED" in capability.blockers


def test_windows_input_executor_is_fail_closed_even_when_mock_backend_is_configured() -> None:
    config = ComputerUseRuntimeConfig(
        vision_enabled=True,
        vision_provider="mock",
        windows_live_enabled=True,
        windows_capture_backend="mock",
        windows_input_backend="mock",
    )
    executor = windows.input_executor_factory(config)

    with pytest.raises(VisionRuntimeError) as exc_info:
        executor.execute(None)  # type: ignore[arg-type]

    assert exc_info.value.reason_code == "WINDOWS_COMPUTER_USE_NOT_QUALIFIED"
