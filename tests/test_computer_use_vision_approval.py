from __future__ import annotations

from datetime import UTC, datetime, timedelta

from imperaos.computer_use.models import RiskClass
from imperaos.computer_use.vision_runtime.approval import (
    hash_json,
    validate_approval_snapshot,
    validate_vision_approval_resume,
)
from imperaos.computer_use.vision_runtime.models import (
    InputActionType,
    NormalizedBBox,
    SurfaceKind,
    VisionAction,
    VisionObservation,
)
from imperaos.computer_use.vision_runtime.runtime import build_approval_snapshot
from imperaos.governance.approval_store import ApprovalStore
from imperaos.governance.models import ApprovalStatus
from imperaos.runtime.config import ComputerUseRuntimeConfig


def _observation() -> VisionObservation:
    return VisionObservation(
        screenshot_hash="f" * 64,
        captured_at="2026-05-05T00:00:00+00:00",
        platform="macos",
        active_app="Safari",
        active_window_title="Fixture",
        surface_kind=SurfaceKind.BROWSER,
        confidence=0.92,
    )


def _action() -> VisionAction:
    return VisionAction(
        action_id="act-approval",
        action_type=InputActionType.CLICK,
        target_bbox=NormalizedBBox(x=0.1, y=0.2, w=0.2, h=0.1),
        rationale="Click safe fixture button.",
        expected_effect="Fixture state changes.",
        risk_class=RiskClass.MEDIUM,
        requires_approval=True,
        confidence=0.91,
    )


def test_approval_snapshot_contains_hashes_and_surface_identity() -> None:
    snapshot = build_approval_snapshot(
        job_id="job-1",
        step_index=1,
        objective="Click safe fixture",
        observation=_observation(),
        action=_action(),
        policy_hash="policy",
        risk_reasons=["step_approval_mode"],
        max_age_ms=10000,
        created_at="2026-05-05T00:00:00+00:00",
    )

    assert snapshot["objective_hash"]
    assert snapshot["approval_kind"] == "computer_use_step"
    assert snapshot["objective_digest"] == snapshot["objective_hash"]
    assert snapshot["step_id"] == "step_001"
    assert snapshot["action_hash"]
    assert snapshot["action_digest"] == snapshot["action_hash"]
    assert snapshot["target_element_id"] is None
    assert snapshot["planner_version"] == "candidate_action_planner/v1"
    assert snapshot["provider_name"] is None
    assert snapshot["provider_model"] is None
    assert snapshot["observation_digest"] == snapshot["before_screenshot_hash"]
    assert snapshot["active_app"] == "Safari"
    assert snapshot["raw_screenshot_path"] is None


def test_stale_approval_snapshot_blocks_execution() -> None:
    snapshot = build_approval_snapshot(
        job_id="job-1",
        step_index=1,
        objective="Click safe fixture",
        observation=_observation(),
        action=_action(),
        policy_hash="policy",
        risk_reasons=["step_approval_mode"],
        max_age_ms=1000,
        created_at=(datetime.now(UTC) - timedelta(seconds=5)).isoformat(),
    )

    result = validate_approval_snapshot(
        snapshot=snapshot,
        current_observation=_observation(),
        action=_action(),
        policy_hash="policy",
        config=ComputerUseRuntimeConfig(),
        now=datetime.now(UTC),
    )

    assert result.allowed is False
    assert result.reason_code == "COMPUTER_USE_STALE_APPROVAL_SNAPSHOT"


def test_vision_approval_resume_requires_executed_unconsumed_ticket(tmp_path) -> None:
    snapshot = build_approval_snapshot(
        job_id="job-1",
        step_index=1,
        objective="Click safe fixture",
        observation=_observation(),
        action=_action(),
        policy_hash="policy",
        risk_reasons=["step_approval_mode"],
        max_age_ms=10000,
    )
    store = ApprovalStore(tmp_path / "approvals.sqlite3")
    ticket = store.create_ticket(
        workspace_id="default",
        run_id="job-1",
        target_kind="device_action",
        target_ref="act-approval",
        action_hash=snapshot["action_hash"],
        policy_hash=snapshot["policy_hash"],
        request_hash=snapshot["objective_hash"],
        snapshot_hash=hash_json(snapshot),
        snapshot=snapshot,
        ttl_seconds=60,
        idempotency_key="vision:job-1:act-approval",
    )

    approved = store.decide(
        approval_id=ticket.approval_id,
        workspace_id="default",
        approve=True,
        actor="operator",
        reason="approved",
    )
    assert approved.ticket is not None
    assert approved.ticket.status == ApprovalStatus.APPROVED

    approved_only = validate_vision_approval_resume(
        ticket=approved.ticket,
        current_observation=_observation(),
        action=_action(),
        policy_hash="policy",
        config=ComputerUseRuntimeConfig(),
    )
    assert approved_only.allowed is False
    assert approved_only.reason_code == "APPROVAL_NOT_EXECUTED"

    executed = store.mark_executed(
        approval_id=ticket.approval_id,
        workspace_id=ticket.workspace_id,
        executed_by="operator",
    )
    assert executed.ticket is not None
    ready = validate_vision_approval_resume(
        ticket=executed.ticket,
        current_observation=_observation(),
        action=_action(),
        policy_hash="policy",
        config=ComputerUseRuntimeConfig(),
    )
    assert ready.allowed is True

    consumed = store.mark_consumed(
        approval_id=ticket.approval_id,
        workspace_id=ticket.workspace_id,
        consumed_by_job_id="job-resume",
    )
    assert consumed.ticket is not None
    replay = validate_vision_approval_resume(
        ticket=consumed.ticket,
        current_observation=_observation(),
        action=_action(),
        policy_hash="policy",
        config=ComputerUseRuntimeConfig(),
    )
    assert replay.allowed is False
    assert replay.reason_code == "REPLAY_BLOCKED"
