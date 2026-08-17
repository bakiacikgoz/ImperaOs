from __future__ import annotations

from pathlib import Path

from imperaos.control_plane.storage import ControlPlaneStore, canonical_json_hash
from imperaos.governance.approval_execution import ApprovalExecutionService
from imperaos.governance.approval_executors.control_plane import ControlPlaneApprovalExecutor
from imperaos.governance.approval_snapshots import compute_approval_request_hash
from imperaos.governance.approval_store import ApprovalStore
from imperaos.runtime.config import RuntimeConfig


def test_control_plane_executor_validates_proposal_and_emits_evidence(tmp_path: Path) -> None:
    root = tmp_path / "control-plane"
    cp_store = ControlPlaneStore(root)
    proposal = {
        "run_id": "run-1",
        "agent_id": "agent-1",
        "action_id": "action-1",
        "input_hash": "c" * 64,
    }
    proposal_ref = "proposals/run-1/action-1.json"
    cp_store.write_json_atomic(proposal_ref, proposal)
    snapshot = {
        "schema_version": "approval.snapshot/v2",
        "kind": "control_plane_action",
        "run_id": "run-1",
        "agent_id": "agent-1",
        "action_id": "action-1",
        "proposal_ref": proposal_ref,
        "proposal_hash": canonical_json_hash(proposal),
        "policy_hash": "b" * 64,
        "input_hash": "c" * 64,
        "runtime_version": "0.4.1",
    }
    digest = compute_approval_request_hash(snapshot)
    approvals = ApprovalStore(tmp_path / "approvals.sqlite3")
    ticket = approvals.create_ticket(
        workspace_id="default",
        run_id="run-1",
        target_kind="control_plane_action",
        target_ref="agent-1:action-1",
        action_hash=canonical_json_hash(proposal),
        policy_hash="b" * 64,
        request_hash=digest,
        snapshot_hash=digest,
        snapshot=snapshot,
        ttl_seconds=300,
        idempotency_key="run-1:action-1",
    )
    approvals.decide(
        approval_id=ticket.approval_id,
        workspace_id="default",
        approve=True,
        actor="operator",
        reason=None,
    )
    config = RuntimeConfig.from_profile("balanced")
    result = ApprovalExecutionService(
        approvals, [ControlPlaneApprovalExecutor(config=config, root_dir=root)]
    ).execute(approval_id=ticket.approval_id, workspace_id="default", actor="operator")
    assert result.ok is True
    assert cp_store.path(result.result["evidenceRef"]).exists()
