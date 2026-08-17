from __future__ import annotations

import platform as platform_module

from imperaos.computer_use.actions import approval_snapshot_payload
from imperaos.computer_use.adapters.browser_adapter import BrowserAdapter
from imperaos.computer_use.guards import detect_hard_stop
from imperaos.computer_use.models import (
    ComputerUseMode,
    ComputerUseStopReason,
    PerceptionSnapshot,
    ProposedAction,
    SessionOutcome,
    SessionRequest,
    SessionStatus,
    TargetDescriptor,
)
from imperaos.computer_use.planner import plan_browser_task
from imperaos.computer_use.policy import BrowserAllowlistPolicy
from imperaos.computer_use.recorder import build_recorder_artifact
from imperaos.computer_use.world_model import build_execution_trace, build_world_model
from imperaos.governance.runtime import GovernanceRuntime


class ComputerUseSession:
    def __init__(
        self,
        *,
        policy: BrowserAllowlistPolicy,
        governance_runtime: GovernanceRuntime | None = None,
        browser_adapter: BrowserAdapter | None = None,
        platform_name: str | None = None,
    ) -> None:
        self._policy = policy
        self._governance_runtime = governance_runtime
        self._browser_adapter = browser_adapter
        self._platform_name = platform_name

    def run_browser_task(
        self,
        *,
        request: SessionRequest,
        target: TargetDescriptor,
    ) -> SessionOutcome:
        platform_name = (self._platform_name or platform_module.system()).strip().lower()
        if platform_name not in {"darwin", "macos"}:
            return self._stopped_outcome(
                request=request,
                stop_reason=ComputerUseStopReason.UNSUPPORTED_PLATFORM,
            )
        if self._browser_adapter is None:
            return self._stopped_outcome(
                request=request,
                stop_reason=ComputerUseStopReason.MISSING_ADAPTER,
            )

        try:
            perception = self._browser_adapter.inspect_target(target=target)
        except NotImplementedError:
            return self._stopped_outcome(
                request=request,
                stop_reason=ComputerUseStopReason.AUTONOMY_NOT_ENABLED,
            )

        actions = plan_browser_task(
            family=request.task_family,
            mode=request.mode,
            target=target,
        )
        return self.run(request=request, perception=perception, actions=actions)

    def run(
        self,
        *,
        request: SessionRequest,
        perception: PerceptionSnapshot,
        actions: list[ProposedAction],
    ) -> SessionOutcome:
        stop_reason = detect_hard_stop(snapshot=perception, policy=self._policy)
        if stop_reason is not None:
            return self._stopped_outcome(
                request=request,
                stop_reason=stop_reason,
                perception=perception,
                actions=actions,
                approval_ids=[],
            )

        approval_ids: list[str] = []
        policy_hash = self._policy.policy_hash()
        status = SessionStatus.PREVIEW_READY

        for action in actions:
            if request.mode == ComputerUseMode.DRY_RUN:
                action.execution_result = {"status": "preview_only"}
                continue

            if self._governance_runtime is None:
                return self._stopped_outcome(
                    request=request,
                    stop_reason=ComputerUseStopReason.GOVERNANCE_UNAVAILABLE,
                    perception=perception,
                    actions=actions,
                    approval_ids=approval_ids,
                )

            snapshot = approval_snapshot_payload(
                action=action,
                perception=perception,
                policy_hash=policy_hash,
            )
            decision, ticket = self._governance_runtime.request_device_action_approval(
                run_id=request.run_id,
                target_ref=action.target_descriptor.target_ref,
                action_payload=snapshot,
                explain="computer-use pilot requires step approval before execution",
            )
            action.execution_result = {
                "status": "approval_pending",
                "reason_code": decision.reason_code,
                "approval_id": ticket.approval_id if ticket else None,
            }
            if ticket is not None:
                approval_ids.append(ticket.approval_id)
            status = SessionStatus.AWAITING_APPROVAL

        return SessionOutcome(
            status=status,
            mode=request.mode,
            actions=actions,
            approval_ids=approval_ids,
            stop_reason=None,
            recorder_artifact=build_recorder_artifact(
                mode=request.mode,
                perception=perception,
                actions=actions,
                approval_ids=approval_ids,
                raw_evidence_allowed=(
                    request.raw_evidence_opt_in and self._policy.raw_evidence_allowed
                ),
            ),
            world_model=build_world_model(
                request=request,
                perception=perception,
                actions=actions,
                status=status,
                approval_ids=approval_ids,
                stop_reason=None,
            ),
            execution_trace=build_execution_trace(
                perception=perception,
                actions=actions,
                status=status,
                approval_ids=approval_ids,
                stop_reason=None,
            ),
        )

    def _stopped_outcome(
        self,
        *,
        request: SessionRequest,
        stop_reason: ComputerUseStopReason,
        perception: PerceptionSnapshot | None = None,
        actions: list[ProposedAction] | None = None,
        approval_ids: list[str] | None = None,
    ) -> SessionOutcome:
        resolved_actions = actions or []
        resolved_approval_ids = approval_ids or []
        recorder_artifact = (
            build_recorder_artifact(
                mode=request.mode,
                perception=perception,
                actions=resolved_actions,
                approval_ids=resolved_approval_ids,
                raw_evidence_allowed=(
                    request.raw_evidence_opt_in and self._policy.raw_evidence_allowed
                ),
            )
            if perception is not None
            else {
                "mode": request.mode.value,
                "traces": [],
                "stop_reason": stop_reason.value,
            }
        )
        return SessionOutcome(
            status=SessionStatus.STOPPED,
            mode=request.mode,
            actions=resolved_actions,
            approval_ids=resolved_approval_ids,
            stop_reason=stop_reason,
            recorder_artifact=recorder_artifact,
            world_model=build_world_model(
                request=request,
                perception=perception,
                actions=resolved_actions,
                status=SessionStatus.STOPPED,
                approval_ids=resolved_approval_ids,
                stop_reason=stop_reason,
            ),
            execution_trace=build_execution_trace(
                perception=perception,
                actions=resolved_actions,
                status=SessionStatus.STOPPED,
                approval_ids=resolved_approval_ids,
                stop_reason=stop_reason,
            ),
        )
