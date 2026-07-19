from __future__ import annotations

from datetime import UTC, datetime, timedelta

from imperaos.governance.runtime import GovernanceRuntime
from imperaos.runtime.config import RuntimeConfig


def _runtime(tmp_path) -> GovernanceRuntime:
    cfg = RuntimeConfig.from_profile("default")
    cfg = cfg.model_copy(
        update={
            "governance": cfg.governance.model_copy(
                update={
                    "approval_store_path": str(tmp_path / "approvals.sqlite3"),
                    "audit_dir": str(tmp_path / "audit"),
                }
            )
        }
    )
    return GovernanceRuntime(config=cfg)


def test_approval_lifecycle_and_replay_block(tmp_path) -> None:
    runtime = _runtime(tmp_path)
    decision, ticket = runtime.evaluate_task(
        run_id="run-1",
        task_type="code",
        user_input="fix this code",
    )

    assert decision.action.value == "require_approval"
    assert ticket is not None

    approved = runtime.decide_approval(
        approval_id=ticket.approval_id,
        approve=True,
        actor="tester",
        reason="approved",
    )
    assert approved.error_code is None
    assert approved.ticket is not None
    assert approved.ticket.status.value == "approved"

    conflict = runtime.decide_approval(
        approval_id=ticket.approval_id,
        approve=False,
        actor="tester",
        reason="late reject",
    )
    assert conflict.error_code == "APPROVAL_CONFLICT"

    executed = runtime.execute_approval(approval_id=ticket.approval_id)
    assert executed.error_code is None
    assert executed.ticket is not None
    assert executed.ticket.status.value == "executed"

    consumed = runtime.consume_approval(
        approval_id=ticket.approval_id,
        consumed_by_job_id="job-resume-1",
    )
    assert consumed.error_code is None
    assert consumed.ticket is not None
    assert consumed.ticket.status.value == "consumed"
    assert consumed.ticket.consumed_by_job_id == "job-resume-1"

    replay = runtime.execute_approval(approval_id=ticket.approval_id)
    assert replay.error_code == "APPROVAL_CONFLICT"


def test_expired_ticket_cannot_be_decided(tmp_path) -> None:
    runtime = _runtime(tmp_path)
    _decision, ticket = runtime.evaluate_task(
        run_id="run-2",
        task_type="code",
        user_input="fix this code",
    )
    assert ticket is not None

    with runtime.approval_store._conn() as conn:  # noqa: SLF001
        conn.execute(
            "UPDATE approvals SET expires_at = ? WHERE approval_id = ?",
            ((datetime.now(UTC) - timedelta(seconds=5)).isoformat(), ticket.approval_id),
        )
    runtime.approval_store.expire_pending()

    expired = runtime.get_approval(ticket.approval_id, workspace_id=ticket.workspace_id)
    assert expired is not None
    assert expired.status.value == "expired"

    result = runtime.decide_approval(
        approval_id=ticket.approval_id,
        approve=True,
        actor="tester",
        reason="too late",
    )
    assert result.error_code == "APPROVAL_CONFLICT"
