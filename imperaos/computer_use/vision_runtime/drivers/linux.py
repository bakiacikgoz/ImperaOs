from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from imperaos.computer_use.vision_runtime.drivers.base import PlatformDriverReadiness
from imperaos.computer_use.vision_runtime.drivers.common import (
    FailClosedInputExecutor,
    FailClosedScreenCaptureProvider,
)
from imperaos.computer_use.vision_runtime.platforms import (
    PlatformCapability,
    build_platform_capability,
)
from imperaos.runtime.config import ComputerUseRuntimeConfig


def readiness() -> PlatformDriverReadiness:
    return PlatformDriverReadiness(
        platform="linux",
        live_execution_enabled=False,
        reason_code="LINUX_COMPUTER_USE_NOT_QUALIFIED",
        summary="Linux live computer-use is scaffolded but not qualified.",
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
        platform="linux",
        environment=environment,
        qualification_report=qualification_report,
        commit=commit,
    )


def screen_capture_provider_factory(
    config: ComputerUseRuntimeConfig,
) -> FailClosedScreenCaptureProvider:
    del config
    return FailClosedScreenCaptureProvider(
        reason_code="LINUX_COMPUTER_USE_NOT_QUALIFIED",
        message="Linux capture is scaffolded but not qualified for live computer-use.",
    )


def input_executor_factory(config: ComputerUseRuntimeConfig) -> FailClosedInputExecutor:
    del config
    return FailClosedInputExecutor(
        reason_code="LINUX_COMPUTER_USE_NOT_QUALIFIED",
        message="Linux input is scaffolded but not qualified for live computer-use.",
    )
