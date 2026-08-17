from __future__ import annotations

from imperaos.governance.approval_executors.base import PreflightOutcome


class DeviceActionApprovalExecutor:
    """Generic approval execution must never bypass the vision qualification runtime."""

    kind = "device_action"

    def preflight(self, ticket, snapshot) -> PreflightOutcome:
        return PreflightOutcome(False, "COMPUTER_USE_NOT_QUALIFIED")

    def execute(self, ticket, snapshot, attempt_id):  # pragma: no cover - blocked by preflight
        raise RuntimeError("device execution requires the qualified vision resume path")
