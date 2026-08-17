from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from imperaos.computer_use.vision_runtime.models import VisionAction, VisionObservation
from imperaos.governance.models import ApprovalStatus, ApprovalTicket, ExecutionStatus
from imperaos.runtime.config import ComputerUseRuntimeConfig


class ApprovalSnapshotValidation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    allowed: bool
    reason_code: str | None = None
    checks: dict[str, bool] = Field(default_factory=dict)


def validate_approval_snapshot(
    *,
    snapshot: dict[str, Any],
    current_observation: VisionObservation,
    action: VisionAction,
    policy_hash: str,
    config: ComputerUseRuntimeConfig,
    now: datetime | None = None,
) -> ApprovalSnapshotValidation:
    checked_at = now or datetime.now(UTC)
    action_hash = hash_json(action.model_dump(mode="json", exclude_none=True))
    max_age_ms = int(snapshot.get("max_age_ms") or config.approval_snapshot_max_age_ms)
    created_at_raw = str(snapshot.get("created_at") or "")
    try:
        created_at = datetime.fromisoformat(created_at_raw)
    except ValueError:
        return _blocked({"created_at_parse": False})
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)

    age_ms = (checked_at - created_at).total_seconds() * 1000
    checks = {
        "not_stale": age_ms <= max_age_ms,
        "action_hash": snapshot.get("action_hash") == action_hash,
        "policy_hash": snapshot.get("policy_hash") == policy_hash,
        "before_screenshot_hash": (
            snapshot.get("before_screenshot_hash") == current_observation.screenshot_hash
        ),
        "active_app": snapshot.get("active_app") == current_observation.active_app,
        "active_window_title": (
            snapshot.get("active_window_title") == current_observation.active_window_title
        ),
        "surface_kind": snapshot.get("surface_kind") == current_observation.surface_kind.value,
        "surface_safe": not current_observation.sensitive_indicators,
    }
    if all(checks.values()):
        return ApprovalSnapshotValidation(allowed=True, checks=checks)
    return _blocked(checks)


def validate_vision_approval_resume(
    *,
    ticket: ApprovalTicket,
    current_observation: VisionObservation,
    action: VisionAction,
    policy_hash: str,
    config: ComputerUseRuntimeConfig,
    now: datetime | None = None,
) -> ApprovalSnapshotValidation:
    lifecycle_checks = {
        "status_executed": ticket.status == ApprovalStatus.EXECUTED,
        "execution_status_executed": ticket.execution_status == ExecutionStatus.EXECUTED,
        "not_consumed": ticket.consumed_at is None and ticket.consumed_by_job_id is None,
    }
    if ticket.status == ApprovalStatus.CONSUMED or not lifecycle_checks["not_consumed"]:
        return _blocked(lifecycle_checks, reason_code="REPLAY_BLOCKED")
    if not (
        lifecycle_checks["status_executed"]
        and lifecycle_checks["execution_status_executed"]
    ):
        return _blocked(lifecycle_checks, reason_code="APPROVAL_NOT_EXECUTED")

    snapshot_validation = validate_approval_snapshot(
        snapshot=ticket.snapshot,
        current_observation=current_observation,
        action=action,
        policy_hash=policy_hash,
        config=config,
        now=now,
    )
    checks = {**lifecycle_checks, **snapshot_validation.checks}
    if snapshot_validation.allowed:
        return ApprovalSnapshotValidation(allowed=True, checks=checks)
    return ApprovalSnapshotValidation(
        allowed=False,
        reason_code=snapshot_validation.reason_code,
        checks=checks,
    )


def hash_json(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _blocked(
    checks: dict[str, bool],
    *,
    reason_code: str = "COMPUTER_USE_STALE_APPROVAL_SNAPSHOT",
) -> ApprovalSnapshotValidation:
    return ApprovalSnapshotValidation(
        allowed=False,
        reason_code=reason_code,
        checks=checks,
    )
