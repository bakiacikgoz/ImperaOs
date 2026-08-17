from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from imperaos.governance.approval_executors.base import ApprovalExecutor
from imperaos.governance.approval_snapshots import (
    compute_approval_request_hash,
    parse_approval_snapshot,
)
from imperaos.governance.approval_store import ApprovalStore


@dataclass(frozen=True, slots=True)
class ApprovalExecutionResult:
    ok: bool
    approval_id: str
    attempt_id: str | None = None
    reason_code: str = "OK"
    result: dict | None = None


class ApprovalExecutionService:
    def __init__(self, store: ApprovalStore, executors: list[ApprovalExecutor]):
        self.store = store
        self.executors = {executor.kind: executor for executor in executors}

    def execute(
        self, *, approval_id: str, workspace_id: str, actor: str
    ) -> ApprovalExecutionResult:
        ticket = self.store.get(approval_id, workspace_id=workspace_id)
        if ticket is None:
            return ApprovalExecutionResult(False, approval_id, reason_code="APPROVAL_NOT_FOUND")
        try:
            snapshot = parse_approval_snapshot(ticket.snapshot)
        except ValueError:
            return ApprovalExecutionResult(
                False, approval_id, reason_code="APPROVAL_SNAPSHOT_SCHEMA_UNSUPPORTED"
            )
        if compute_approval_request_hash(snapshot) != ticket.request_hash:
            return ApprovalExecutionResult(
                False, approval_id, reason_code="APPROVAL_REQUEST_HASH_MISMATCH"
            )
        executor = self.executors.get(snapshot.kind)
        if executor is None:
            return ApprovalExecutionResult(
                False, approval_id, reason_code="APPROVAL_EXECUTOR_UNSUPPORTED"
            )
        preflight = executor.preflight(ticket, snapshot)
        if not preflight.allowed:
            return ApprovalExecutionResult(False, approval_id, reason_code=preflight.reason_code)
        attempt_id = str(uuid4())
        claim = self.store.claim_execution(
            approval_id=approval_id, workspace_id=workspace_id, attempt_id=attempt_id, actor=actor
        )
        if claim.error_code:
            return ApprovalExecutionResult(False, approval_id, attempt_id, claim.error_code)
        try:
            outcome = executor.execute(ticket, snapshot, attempt_id)
        except Exception as exc:
            self.store.finalize_execution_failure(
                approval_id=approval_id,
                workspace_id=workspace_id,
                attempt_id=attempt_id,
                error_code=type(exc).__name__,
            )
            return ApprovalExecutionResult(
                False, approval_id, attempt_id, "APPROVAL_EXECUTION_FAILED"
            )
        finalized = self.store.finalize_execution_success(
            approval_id=approval_id,
            workspace_id=workspace_id,
            attempt_id=attempt_id,
            result_hash=outcome.result_hash,
        )
        return ApprovalExecutionResult(
            finalized.error_code is None,
            approval_id,
            attempt_id,
            finalized.error_code or "OK",
            outcome.result,
        )
