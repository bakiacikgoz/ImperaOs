from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from imperaos.control_plane.models import OperationDescriptor, OperationWorkflowResult
from imperaos.control_plane.rbac_admin import check_permission
from imperaos.control_plane.snapshot import build_control_plane_snapshot
from imperaos.runtime.config import RuntimeConfig
from imperaos.runtime.paths import CONTROL_PLANE_STATE_ROOT


def dry_run_operation(
    *,
    config: RuntimeConfig,
    operation_id: str,
    actor_id: str,
    root_dir: str | Path = CONTROL_PLANE_STATE_ROOT,
    evidence_root: str | Path = "artifacts",
    dry_run: bool = True,
) -> OperationWorkflowResult:
    operation = _operation_by_id(
        config=config,
        operation_id=operation_id,
        root_dir=root_dir,
        evidence_root=evidence_root,
    )
    if operation is None:
        return _result(
            operation_id=operation_id,
            actor_id=actor_id,
            dry_run=dry_run,
            permission="unknown",
            risk_level="high",
            status="blocked",
            reason_code="OPERATION_UNKNOWN",
            next_actions=["operation.select"],
        )

    if operation.risk_level == "destructive":
        return _result(
            operation_id=operation.operation_id,
            actor_id=actor_id,
            dry_run=dry_run,
            permission=operation.permission,
            risk_level=operation.risk_level,
            status="blocked",
            reason_code="DESTRUCTIVE_OPERATION_DISABLED",
            next_actions=["open.change-control"],
        )
    permission = check_permission(
        config=config,
        actor_id=actor_id,
        permission=operation.permission,
        dry_run=True,
    )
    if permission.status == "denied":
        return _result(
            operation_id=operation.operation_id,
            actor_id=actor_id,
            dry_run=dry_run,
            permission=operation.permission,
            risk_level=operation.risk_level,
            status="blocked",
            reason_code="RBAC_PERMISSION_DENIED",
            next_actions=["rbac.review", "operator.identity"],
        )
    if not dry_run:
        return _result(
            operation_id=operation.operation_id,
            actor_id=actor_id,
            dry_run=dry_run,
            permission=operation.permission,
            risk_level=operation.risk_level,
            status="blocked",
            reason_code="EXECUTE_NOT_SUPPORTED_IN_RC",
            next_actions=["retry.dry-run"],
        )
    if not operation.enabled:
        return _result(
            operation_id=operation.operation_id,
            actor_id=actor_id,
            dry_run=dry_run,
            permission=operation.permission,
            risk_level=operation.risk_level,
            status="blocked",
            reason_code=operation.disabled_reason or "OPERATION_DISABLED",
            next_actions=["resolve.prerequisite"],
        )
    if not operation.supports_dry_run and operation.risk_level != "read_only":
        return _result(
            operation_id=operation.operation_id,
            actor_id=actor_id,
            dry_run=dry_run,
            permission=operation.permission,
            risk_level=operation.risk_level,
            status="requires_approval",
            reason_code="APPROVAL_REQUIRED",
            next_actions=["approval.request"],
        )
    return _result(
        operation_id=operation.operation_id,
        actor_id=actor_id,
        dry_run=dry_run,
        permission=operation.permission,
        risk_level=operation.risk_level,
        status="passed",
        reason_code="DRY_RUN_PASSED",
        next_actions=["inspect.result"],
    )


def _operation_by_id(
    *,
    config: RuntimeConfig,
    operation_id: str,
    root_dir: str | Path,
    evidence_root: str | Path,
) -> OperationDescriptor | None:
    snapshot = build_control_plane_snapshot(
        root_dir=root_dir,
        profile=config.profile_name,
        evidence_root=evidence_root,
        runtime_mode="cli",
        bridge_mode="cli",
        used_fixture=False,
    )
    for operation in snapshot.operations:
        if operation.operation_id == operation_id:
            return operation
    return None


def _result(
    *,
    operation_id: str,
    actor_id: str,
    dry_run: bool,
    permission: str,
    risk_level: str,
    status: str,
    reason_code: str,
    next_actions: list[str],
) -> OperationWorkflowResult:
    return OperationWorkflowResult(
        operation_id=operation_id,
        actor_id=actor_id,
        dry_run=dry_run,
        permission=permission,
        risk_level=risk_level,
        status=status,
        reason_code=reason_code,
        next_actions=next_actions,
        generated_at_utc=datetime.now(UTC),
    )
