from __future__ import annotations

import pytest

from imperaos.computer_use.vision_runtime.drivers import linux
from imperaos.computer_use.vision_runtime.errors import VisionRuntimeError
from imperaos.runtime.config import ComputerUseRuntimeConfig


def test_linux_gate_reports_wayland_not_qualified_without_evidence() -> None:
    capability = linux.readiness_report(
        ComputerUseRuntimeConfig(),
        environment={
            "XDG_SESSION_TYPE": "wayland",
            "WAYLAND_DISPLAY": "wayland-0",
            "DISPLAY": "",
        },
    )

    assert capability.platform == "linux"
    assert capability.stage == "not_qualified"
    assert capability.live_enabled is False
    assert capability.reason_code == "LINUX_COMPUTER_USE_NOT_QUALIFIED"
    assert "LINUX_WAYLAND_NOT_QUALIFIED" in capability.blockers
    assert "LINUX_INPUT_BACKEND_DISABLED" in capability.blockers


def test_linux_gate_reports_x11_not_qualified_without_evidence() -> None:
    capability = linux.readiness_report(
        ComputerUseRuntimeConfig(),
        environment={
            "XDG_SESSION_TYPE": "x11",
            "WAYLAND_DISPLAY": "",
            "DISPLAY": ":0",
        },
    )

    assert capability.platform == "linux"
    assert capability.live_enabled is False
    assert capability.reason_code == "LINUX_COMPUTER_USE_NOT_QUALIFIED"
    assert "LINUX_X11_NOT_QUALIFIED" in capability.blockers


def test_linux_input_executor_is_fail_closed() -> None:
    config = ComputerUseRuntimeConfig(
        vision_enabled=True,
        vision_provider="mock",
        linux_live_enabled=True,
        linux_capture_backend="mock",
        linux_input_backend="mock",
    )
    executor = linux.input_executor_factory(config)

    with pytest.raises(VisionRuntimeError) as exc_info:
        executor.execute(None)  # type: ignore[arg-type]

    assert exc_info.value.reason_code == "LINUX_COMPUTER_USE_NOT_QUALIFIED"
