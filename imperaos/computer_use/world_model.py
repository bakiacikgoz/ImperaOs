from __future__ import annotations

from imperaos.computer_use.models import (
    ChangedResource,
    ComputerUseStopReason,
    ExecutionStage,
    ExecutionTurn,
    PerceptionSnapshot,
    ProposedAction,
    SessionRequest,
    SessionStatus,
    WindowState,
    WorldModel,
)

_DRIFT_REASONS = {
    ComputerUseStopReason.UNKNOWN_VISUAL,
    ComputerUseStopReason.SELECTOR_AMBIGUOUS,
    ComputerUseStopReason.UNEXPECTED_MODAL,
    ComputerUseStopReason.FOCUS_DRIFT,
}

_INTERVENTION_REASONS = {
    ComputerUseStopReason.SENSITIVE_SURFACE_DETECTED,
    ComputerUseStopReason.POLICY_DENIED,
    ComputerUseStopReason.GOVERNANCE_UNAVAILABLE,
}


def stage_for_outcome(
    *,
    status: SessionStatus,
    approval_ids: list[str],
    stop_reason: ComputerUseStopReason | None,
) -> ExecutionStage:
    if stop_reason is not None:
        return ExecutionStage.STOPPED
    if approval_ids:
        return ExecutionStage.REQUIRE_APPROVAL
    if status == SessionStatus.PREVIEW_READY:
        return ExecutionStage.CHECKPOINT
    return ExecutionStage.PLAN


def build_world_model(
    *,
    request: SessionRequest,
    perception: PerceptionSnapshot | None,
    actions: list[ProposedAction],
    status: SessionStatus,
    approval_ids: list[str],
    stop_reason: ComputerUseStopReason | None,
) -> WorldModel:
    active_window = (
        WindowState(
            window_identity=perception.window_or_tab_identity,
            app_identity=perception.app_identity,
            focused=perception.focused,
        )
        if perception is not None
        else None
    )
    changed_resources = [
        ChangedResource(
            target_ref=action.target_descriptor.target_ref,
            action_id=action.action_id,
            expected_effect=action.expected_effect,
            status=str(action.execution_result.get("status") or "planned"),
        )
        for action in actions
    ]
    notes: list[str] = []
    if approval_ids:
        notes.append("approval_pending")
    if stop_reason is not None:
        notes.append(stop_reason.value)

    last_completed_action = next(
        (
            action.action_id
            for action in reversed(actions)
            if str(action.execution_result.get("status") or "") in {"preview_only", "executed"}
        ),
        None,
    )
    current_stage = stage_for_outcome(
        status=status,
        approval_ids=approval_ids,
        stop_reason=stop_reason,
    )
    return WorldModel(
        active_run_id=request.run_id,
        objective=request.prompt,
        stage=current_stage,
        last_known_status=status.value,
        active_window=active_window,
        open_windows=[active_window] if active_window is not None else [],
        observed_targets=[action.target_descriptor for action in actions],
        changed_resources=changed_resources,
        pending_approval_ids=approval_ids,
        last_completed_action=last_completed_action,
        drift_detected=stop_reason in _DRIFT_REASONS,
        user_intervention_required=bool(approval_ids) or stop_reason in _INTERVENTION_REASONS,
        notes=notes,
    )


def build_execution_trace(
    *,
    perception: PerceptionSnapshot | None,
    actions: list[ProposedAction],
    status: SessionStatus,
    approval_ids: list[str],
    stop_reason: ComputerUseStopReason | None,
) -> list[ExecutionTurn]:
    trace: list[ExecutionTurn] = [
        ExecutionTurn(
            stage=ExecutionStage.PLAN,
            summary="Goal interpreted and action plan staged.",
        )
    ]
    if perception is not None:
        trace.append(
            ExecutionTurn(
                stage=ExecutionStage.OBSERVE,
                perception=perception,
                summary="Observed the current surface and grounded the target.",
            )
        )
        trace.append(
            ExecutionTurn(
                stage=ExecutionStage.INTERPRET_STATE,
                perception=perception,
                summary="Interpreted the observed state against the expected target.",
            )
        )
    if actions:
        action = actions[0]
        trace.extend(
            [
                ExecutionTurn(
                    stage=ExecutionStage.COMPARE_STATE,
                    action=action,
                    summary="Compared observed state against the expected effect.",
                ),
                ExecutionTurn(
                    stage=ExecutionStage.DECIDE_ACTION,
                    action=action,
                    summary="Selected the next bounded action.",
                ),
                ExecutionTurn(
                    stage=ExecutionStage.CLASSIFY_RISK,
                    action=action,
                    summary=f"Classified action risk as {action.risk_class.value}.",
                ),
            ]
        )
        action_status = str(action.execution_result.get("status") or "")
        if approval_ids:
            trace.append(
                ExecutionTurn(
                    stage=ExecutionStage.REQUIRE_APPROVAL,
                    action=action,
                    summary="Execution is waiting for operator approval.",
                )
            )
        elif action_status:
            trace.append(
                ExecutionTurn(
                    stage=ExecutionStage.EXECUTE,
                    action=action,
                    summary=f"Action entered {action_status} state.",
                )
            )
            trace.append(
                ExecutionTurn(
                    stage=ExecutionStage.VERIFY,
                    action=action,
                    summary="Captured the result for verification and checkpointing.",
                )
            )

    trace.append(
        ExecutionTurn(
            stage=ExecutionStage.CHECKPOINT,
            summary="Checkpointed the current world state for replay and resume.",
        )
    )
    if stop_reason is not None:
        trace.append(
            ExecutionTurn(
                stage=ExecutionStage.STOPPED,
                summary=f"Stopped because {stop_reason.value}.",
            )
        )
    elif status == SessionStatus.PREVIEW_READY:
        trace.append(
            ExecutionTurn(
                stage=ExecutionStage.COMPLETED,
                summary="Preview completed without external execution.",
            )
        )
    return trace
