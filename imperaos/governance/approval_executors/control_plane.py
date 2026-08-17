from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from imperaos.control_plane.storage import ControlPlaneStore, canonical_json_hash
from imperaos.enterprise.identity import IdentityResolutionError, require_permission
from imperaos.governance.approval_executors.base import ExecutionOutcome, PreflightOutcome
from imperaos.governance.approval_snapshots import ApprovalSnapshot, ControlPlaneActionSnapshot
from imperaos.governance.models import ApprovalTicket
from imperaos.runtime.config import RuntimeConfig


class ControlPlaneApprovalExecutor:
    kind = "control_plane_action"

    def __init__(self, *, config: RuntimeConfig, root_dir: str | Path):
        self.config = config
        self.store = ControlPlaneStore(root_dir)

    def _proposal(self, snapshot: ControlPlaneActionSnapshot) -> dict | None:
        payload = self.store.read_json(snapshot.proposal_ref, default=None)
        return payload if isinstance(payload, dict) else None

    def preflight(self, ticket: ApprovalTicket, snapshot: ApprovalSnapshot) -> PreflightOutcome:
        if not isinstance(snapshot, ControlPlaneActionSnapshot):
            return PreflightOutcome(False, "APPROVAL_SNAPSHOT_KIND_MISMATCH")
        proposal = self._proposal(snapshot)
        if proposal is None or canonical_json_hash(proposal) != snapshot.proposal_hash:
            return PreflightOutcome(False, "CONTROL_PLANE_PROPOSAL_HASH_MISMATCH")
        if (proposal.get("run_id"), proposal.get("agent_id"), proposal.get("action_id")) != (
            snapshot.run_id,
            snapshot.agent_id,
            snapshot.action_id,
        ):
            return PreflightOutcome(False, "CONTROL_PLANE_PROPOSAL_BINDING_MISMATCH")
        if ticket.policy_hash != snapshot.policy_hash:
            return PreflightOutcome(False, "CONTROL_PLANE_POLICY_HASH_MISMATCH")
        try:
            require_permission(self.config, permission="runtime.run")
        except IdentityResolutionError as exc:
            return PreflightOutcome(False, exc.error_code)
        return PreflightOutcome(True)

    def execute(
        self, ticket: ApprovalTicket, snapshot: ApprovalSnapshot, attempt_id: str
    ) -> ExecutionOutcome:
        assert isinstance(snapshot, ControlPlaneActionSnapshot)
        evidence = {
            "schemaVersion": "control-plane.execution-evidence/v1",
            "approvalId": ticket.approval_id,
            "executionAttemptId": attempt_id,
            "runId": snapshot.run_id,
            "agentId": snapshot.agent_id,
            "actionId": snapshot.action_id,
            "proposalHash": snapshot.proposal_hash,
            "policyHash": snapshot.policy_hash,
            "outcome": "executed",
            "generatedAtUtc": datetime.now(UTC).isoformat(),
        }
        result_hash = canonical_json_hash(evidence)
        evidence_ref = f"evidence/executions/{attempt_id}.json"
        self.store.write_json_atomic(evidence_ref, {**evidence, "resultHash": result_hash})
        return ExecutionOutcome(
            {"evidenceRef": evidence_ref, "resultHash": result_hash}, result_hash
        )
