from __future__ import annotations

from imperaos.computer_use.vision_runtime.models import ExecutionResult, VisionAction


class DryRunVisionExecutor:
    def execute(self, action: VisionAction) -> ExecutionResult:
        return ExecutionResult(
            status="skipped",
            message="Dry-run executor did not perform live OS input.",
            details={"action_id": action.action_id},
        )
