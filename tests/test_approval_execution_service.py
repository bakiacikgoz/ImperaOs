from __future__ import annotations

from pathlib import Path

from imperaos.governance.approval_execution import ApprovalExecutionService
from imperaos.governance.approval_executors.base import ExecutionOutcome, PreflightOutcome
from imperaos.governance.approval_snapshots import compute_approval_request_hash
from imperaos.governance.approval_store import ApprovalStore


class RecordingExecutor:
    kind = "control_plane_action"

    def __init__(self, events: list[str], *, allowed: bool = True):
        self.events = events
        self.allowed = allowed

    def preflight(self, ticket, snapshot):
        self.events.append("preflight")
        return PreflightOutcome(self.allowed, "PERMISSION_DENIED" if not self.allowed else "OK")

    def execute(self, ticket, snapshot, attempt_id):
        assert ticket.status.value == "approved"
        self.events.append("execute")
        return ExecutionOutcome({"evidenceRef": "evidence/run-1.json"}, "e" * 64)


def _approved_store(tmp_path: Path) -> tuple[ApprovalStore, str]:
    store = ApprovalStore(tmp_path / "approvals.sqlite3")
    snapshot = {
        "schema_version": "approval.snapshot/v2", "kind": "control_plane_action",
        "run_id": "run-1", "agent_id": "agent-1", "action_id": "action-1",
        "proposal_ref": "proposals/run-1/action-1.json", "proposal_hash": "a" * 64,
        "policy_hash": "b" * 64, "input_hash": "c" * 64, "runtime_version": "0.4.1",
    }
    request_hash = compute_approval_request_hash(snapshot)
    ticket = store.create_ticket(workspace_id="default", run_id="run-1",
        target_kind="control_plane_action", target_ref="agent-1:action-1",
        action_hash="a" * 64, policy_hash="b" * 64, request_hash=request_hash,
        snapshot_hash=request_hash, snapshot=snapshot, ttl_seconds=300,
        idempotency_key="run-1:action-1")
    store.decide(approval_id=ticket.approval_id, workspace_id="default", approve=True,
        actor="operator", reason=None)
    return store, ticket.approval_id


def test_service_preflights_claims_executes_and_finalizes(tmp_path: Path) -> None:
    store, approval_id = _approved_store(tmp_path)
    events: list[str] = []
    result = ApprovalExecutionService(store, [RecordingExecutor(events)]).execute(
        approval_id=approval_id, workspace_id="default", actor="operator")
    assert result.ok is True
    assert events == ["preflight", "execute"]
    assert store.get(approval_id, workspace_id="default").status.value == "executed"


def test_preflight_denial_never_claims_or_executes(tmp_path: Path) -> None:
    store, approval_id = _approved_store(tmp_path)
    events: list[str] = []
    result = ApprovalExecutionService(store, [RecordingExecutor(events, allowed=False)]).execute(
        approval_id=approval_id, workspace_id="default", actor="operator")
    assert result.reason_code == "PERMISSION_DENIED"
    assert events == ["preflight"]
    assert store.get(approval_id, workspace_id="default").status.value == "approved"
