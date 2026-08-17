from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from imperaos.governance.approval_store import ApprovalStore


def test_only_one_execution_attempt_can_claim_an_approved_ticket(tmp_path: Path) -> None:
    store = ApprovalStore(tmp_path / "approvals.sqlite3")
    ticket = store.create_ticket(
        workspace_id="default",
        run_id="run-1",
        target_kind="task",
        target_ref="task-1",
        action_hash="a" * 64,
        policy_hash="b" * 64,
        request_hash="c" * 64,
        snapshot_hash="d" * 64,
        snapshot={"kind": "task", "workspaceId": "default"},
        ttl_seconds=300,
        idempotency_key="run-1:task-1",
    )
    store.decide(
        approval_id=ticket.approval_id,
        workspace_id="default",
        approve=True,
        actor="operator",
        reason=None,
    )

    def claim(attempt_id: str) -> str | None:
        return store.claim_execution(
            approval_id=ticket.approval_id,
            workspace_id="default",
            attempt_id=attempt_id,
            actor="operator",
        ).error_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(claim, ["attempt-a", "attempt-b"]))

    assert results.count(None) == 1
    assert results.count("APPROVAL_EXECUTION_CLAIM_CONFLICT") == 1
    claimed = store.get(ticket.approval_id, workspace_id="default")
    assert claimed is not None
    assert claimed.status.value == "executing"
    assert claimed.execution_attempt_id in {"attempt-a", "attempt-b"}
