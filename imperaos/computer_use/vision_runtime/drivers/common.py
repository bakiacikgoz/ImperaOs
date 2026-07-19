from __future__ import annotations

from typing import Any

from imperaos.computer_use.vision_runtime.errors import VisionRuntimeError


class FailClosedScreenCaptureProvider:
    def __init__(self, *, reason_code: str, message: str) -> None:
        self.reason_code = reason_code
        self.message = message

    def capture(self) -> None:
        raise VisionRuntimeError(self.reason_code, self.message)


class FailClosedInputExecutor:
    def __init__(self, *, reason_code: str, message: str) -> None:
        self.reason_code = reason_code
        self.message = message

    def execute(self, action: Any) -> None:
        del action
        raise VisionRuntimeError(self.reason_code, self.message)
