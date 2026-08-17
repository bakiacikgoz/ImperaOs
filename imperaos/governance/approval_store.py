from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from imperaos.governance.models import ApprovalStatus, ApprovalTicket, ExecutionStatus


@dataclass(slots=True)
class ApprovalDecisionResult:
    ticket: ApprovalTicket | None
    error_code: str | None = None


class ApprovalStore:
    SCHEMA_VERSION = "3.0"
    LEGACY_UNBOUND_WORKSPACE = "__legacy_unbound__"

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS approvals (
                    approval_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL DEFAULT '__legacy_unbound__',
                    version INTEGER NOT NULL,
                    run_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    target_kind TEXT NOT NULL DEFAULT '',
                    target_ref TEXT NOT NULL DEFAULT '',
                    action_hash TEXT NOT NULL DEFAULT '',
                    policy_hash TEXT NOT NULL DEFAULT '',
                    request_hash TEXT NOT NULL,
                    snapshot_hash TEXT NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    actor TEXT,
                    decision_reason TEXT,
                    execution_status TEXT NOT NULL,
                    executed_at TEXT,
                    execution_error_code TEXT,
                    executed_by TEXT,
                    execution_contract_hash TEXT,
                    execution_attempt_id TEXT,
                    execution_claimed_at TEXT,
                    execution_result_hash TEXT,
                    resume_token_ref TEXT,
                    resume_claimed_job_id TEXT,
                    resume_claimed_at TEXT,
                    consumed_by_job_id TEXT,
                    consumed_at TEXT,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    decided_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS approval_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            existing_cols = {
                str(row["name"]) for row in conn.execute("PRAGMA table_info(approvals)").fetchall()
            }
            migrations = {
                "target_kind": (
                    "ALTER TABLE approvals ADD COLUMN target_kind TEXT NOT NULL DEFAULT ''"
                ),
                "target_ref": (
                    "ALTER TABLE approvals ADD COLUMN target_ref TEXT NOT NULL DEFAULT ''"
                ),
                "action_hash": (
                    "ALTER TABLE approvals ADD COLUMN action_hash TEXT NOT NULL DEFAULT ''"
                ),
                "policy_hash": (
                    "ALTER TABLE approvals ADD COLUMN policy_hash TEXT NOT NULL DEFAULT ''"
                ),
                "execution_contract_hash": (
                    "ALTER TABLE approvals ADD COLUMN execution_contract_hash TEXT"
                ),
                "resume_token_ref": "ALTER TABLE approvals ADD COLUMN resume_token_ref TEXT",
                "resume_claimed_job_id": (
                    "ALTER TABLE approvals ADD COLUMN resume_claimed_job_id TEXT"
                ),
                "resume_claimed_at": "ALTER TABLE approvals ADD COLUMN resume_claimed_at TEXT",
                "consumed_by_job_id": "ALTER TABLE approvals ADD COLUMN consumed_by_job_id TEXT",
                "consumed_at": "ALTER TABLE approvals ADD COLUMN consumed_at TEXT",
                "workspace_id": (
                    "ALTER TABLE approvals ADD COLUMN workspace_id "
                    "TEXT NOT NULL DEFAULT '__legacy_unbound__'"
                ),
                "executed_by": "ALTER TABLE approvals ADD COLUMN executed_by TEXT",
                "execution_attempt_id": (
                    "ALTER TABLE approvals ADD COLUMN execution_attempt_id TEXT"
                ),
                "execution_claimed_at": (
                    "ALTER TABLE approvals ADD COLUMN execution_claimed_at TEXT"
                ),
                "execution_result_hash": (
                    "ALTER TABLE approvals ADD COLUMN execution_result_hash TEXT"
                ),
            }
            for column, statement in migrations.items():
                if column not in existing_cols:
                    conn.execute(statement)
            self._backfill_workspace_bindings(conn)
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_approvals_workspace_status_created
                ON approvals(workspace_id, status, created_at)
                """
            )
            conn.execute(
                """
                INSERT INTO approval_metadata(key, value)
                VALUES ('schema_version', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (self.SCHEMA_VERSION,),
            )

    def _backfill_workspace_bindings(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute(
            """
            SELECT approval_id, target_kind, target_ref, snapshot_json
            FROM approvals WHERE workspace_id = ?
            """,
            (self.LEGACY_UNBOUND_WORKSPACE,),
        ).fetchall()
        for row in rows:
            try:
                snapshot = json.loads(str(row["snapshot_json"]))
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            candidates = {
                str(snapshot[key]).strip()
                for key in ("workspaceId", "workspace_id")
                if isinstance(snapshot, dict)
                and isinstance(snapshot.get(key), str)
                and str(snapshot[key]).strip()
            }
            target_kind = str(row["target_kind"])
            if target_kind.startswith("artifact"):
                target_ref = str(row["target_ref"])
                prefix, separator, remainder = target_ref.partition(":")
                if separator and prefix.strip() and remainder.strip():
                    candidates.add(prefix.strip())
            if len(candidates) != 1:
                continue
            conn.execute(
                "UPDATE approvals SET workspace_id = ? WHERE approval_id = ?",
                (next(iter(candidates)), str(row["approval_id"])),
            )

    @classmethod
    def _canonical_workspace_binding(
        cls,
        *,
        workspace_id: str | None,
        target_kind: str,
        target_ref: str,
        snapshot: dict[str, Any],
    ) -> str:
        candidates = {
            value.strip()
            for value in (workspace_id, snapshot.get("workspaceId"), snapshot.get("workspace_id"))
            if isinstance(value, str) and value.strip()
        }
        if target_kind.startswith("artifact"):
            prefix, separator, remainder = target_ref.partition(":")
            if not separator or not prefix.strip() or not remainder.strip():
                raise ValueError("artifact approval workspace binding is malformed")
            candidates.add(prefix.strip())
        if not candidates:
            raise ValueError("approval workspace binding is required")
        if len(candidates) != 1:
            raise ValueError("approval workspace binding is inconsistent")
        bound = next(iter(candidates))
        if bound == cls.LEGACY_UNBOUND_WORKSPACE:
            raise ValueError("approval workspace binding is reserved")
        return bound

    def create_ticket(
        self,
        *,
        workspace_id: str | None = None,
        run_id: str,
        target_kind: str,
        target_ref: str,
        action_hash: str,
        policy_hash: str,
        request_hash: str,
        snapshot_hash: str,
        snapshot: dict[str, Any],
        ttl_seconds: int,
        idempotency_key: str,
    ) -> ApprovalTicket:
        now = datetime.now(UTC)
        bound_workspace = self._canonical_workspace_binding(
            workspace_id=workspace_id,
            target_kind=target_kind,
            target_ref=target_ref,
            snapshot=snapshot,
        )
        ticket = ApprovalTicket(
            version=0,
            approval_id=str(uuid4()),
            workspace_id=bound_workspace,
            run_id=run_id,
            status=ApprovalStatus.PENDING,
            target_kind=target_kind,
            target_ref=target_ref,
            action_hash=action_hash,
            policy_hash=policy_hash,
            request_hash=request_hash,
            snapshot_hash=snapshot_hash,
            snapshot=snapshot,
            expires_at=now + timedelta(seconds=ttl_seconds),
            execution_status=ExecutionStatus.NOT_EXECUTED,
            idempotency_key=idempotency_key,
            created_at=now,
        )
        with self._conn() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO approvals (
                        approval_id, workspace_id, version, run_id, status,
                        target_kind, target_ref, action_hash,
                        policy_hash, request_hash, snapshot_hash,
                        snapshot_json, expires_at, actor, decision_reason, execution_status,
                        executed_at, execution_error_code, executed_by, execution_contract_hash,
                        resume_token_ref, resume_claimed_job_id, resume_claimed_at,
                        consumed_by_job_id, consumed_at,
                        idempotency_key, created_at, decided_at
                    )
                    VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                    """,
                    (
                        ticket.approval_id,
                        ticket.workspace_id,
                        ticket.version,
                        ticket.run_id,
                        ticket.status.value,
                        ticket.target_kind,
                        ticket.target_ref,
                        ticket.action_hash,
                        ticket.policy_hash,
                        ticket.request_hash,
                        ticket.snapshot_hash,
                        json.dumps(ticket.snapshot, ensure_ascii=False, sort_keys=True),
                        ticket.expires_at.isoformat(),
                        ticket.actor,
                        ticket.decision_reason,
                        ticket.execution_status.value,
                        ticket.executed_at.isoformat() if ticket.executed_at else None,
                        ticket.execution_error_code,
                        ticket.executed_by,
                        ticket.execution_contract_hash,
                        ticket.resume_token_ref,
                        ticket.resume_claimed_job_id,
                        ticket.resume_claimed_at.isoformat() if ticket.resume_claimed_at else None,
                        ticket.consumed_by_job_id,
                        ticket.consumed_at.isoformat() if ticket.consumed_at else None,
                        ticket.idempotency_key,
                        ticket.created_at.isoformat(),
                        ticket.decided_at.isoformat() if ticket.decided_at else None,
                    ),
                )
            except sqlite3.IntegrityError:
                existing = self._get_by_idempotency_key(conn, idempotency_key, bound_workspace)
                if existing is not None:
                    return existing
                raise
        return ticket

    def _get_by_idempotency_key(
        self,
        conn: sqlite3.Connection,
        idempotency_key: str,
        workspace_id: str | None = None,
    ) -> ApprovalTicket | None:
        if workspace_id is None:
            row = conn.execute(
                "SELECT * FROM approvals WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM approvals WHERE idempotency_key = ? AND workspace_id = ?",
                (idempotency_key, workspace_id),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_ticket(row)

    def list_pending(self, *, workspace_id: str | None = None) -> list[ApprovalTicket]:
        self.expire_pending()
        if workspace_id is None or not workspace_id.strip():
            return []
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM approvals
                WHERE status = ? AND workspace_id = ?
                ORDER BY created_at ASC
                """,
                (ApprovalStatus.PENDING.value, workspace_id),
            ).fetchall()
        return [self._row_to_ticket(row) for row in rows]

    def get(self, approval_id: str, *, workspace_id: str | None = None) -> ApprovalTicket | None:
        if workspace_id is None or not workspace_id.strip():
            return None
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM approvals WHERE approval_id = ? AND workspace_id = ?",
                (approval_id, workspace_id),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_ticket(row)

    def get_by_idempotency_key(
        self, idempotency_key: str, *, workspace_id: str | None = None
    ) -> ApprovalTicket | None:
        if workspace_id is None or not workspace_id.strip():
            return None
        with self._conn() as conn:
            return self._get_by_idempotency_key(conn, idempotency_key, workspace_id)

    def claim_approved_action(
        self,
        *,
        approval_id: str,
        workspace_id: str,
        claim_id: str,
        target_kind: str,
        target_ref: str,
        action_hash: str,
        executor_principal_id: str,
    ) -> ApprovalDecisionResult:
        self.expire_pending()
        now = datetime.now(UTC)
        with self._conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM approvals WHERE approval_id = ? AND workspace_id = ?",
                (approval_id, workspace_id),
            ).fetchone()
            if row is None:
                return ApprovalDecisionResult(ticket=None, error_code="APPROVAL_NOT_FOUND")
            ticket = self._row_to_ticket(row)
            if (
                ticket.target_kind != target_kind
                or ticket.target_ref != target_ref
                or ticket.action_hash != action_hash
            ):
                return ApprovalDecisionResult(ticket=ticket, error_code="STALE_APPROVAL_SNAPSHOT")
            if ticket.snapshot.get("executorPrincipalId") != executor_principal_id:
                return ApprovalDecisionResult(
                    ticket=ticket,
                    error_code="APPROVAL_PRINCIPAL_MISMATCH",
                )
            if ticket.status is ApprovalStatus.CONSUMED:
                error = None if ticket.consumed_by_job_id == claim_id else "REPLAY_BLOCKED"
                return ApprovalDecisionResult(ticket=ticket, error_code=error)
            if ticket.status is ApprovalStatus.EXECUTED:
                error = None if ticket.resume_claimed_job_id == claim_id else "REPLAY_BLOCKED"
                return ApprovalDecisionResult(ticket=ticket, error_code=error)
            if ticket.status is not ApprovalStatus.APPROVED:
                return ApprovalDecisionResult(ticket=ticket, error_code="APPROVAL_CONFLICT")
            updated = conn.execute(
                """
                UPDATE approvals
                SET status = ?, execution_status = ?, executed_at = ?,
                    executed_by = ?, resume_claimed_job_id = ?, resume_claimed_at = ?,
                    version = version + 1
                WHERE approval_id = ? AND workspace_id = ? AND version = ? AND status = ?
                """,
                (
                    ApprovalStatus.EXECUTED.value,
                    ExecutionStatus.EXECUTED.value,
                    now.isoformat(),
                    executor_principal_id,
                    claim_id,
                    now.isoformat(),
                    approval_id,
                    workspace_id,
                    ticket.version,
                    ApprovalStatus.APPROVED.value,
                ),
            ).rowcount
            if updated != 1:
                return ApprovalDecisionResult(ticket=ticket, error_code="APPROVAL_CONFLICT")
        return ApprovalDecisionResult(
            ticket=self.get(approval_id, workspace_id=workspace_id), error_code=None
        )

    def complete_claimed_action(
        self,
        *,
        approval_id: str,
        workspace_id: str,
        claim_id: str,
    ) -> ApprovalDecisionResult:
        now = datetime.now(UTC)
        with self._conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM approvals WHERE approval_id = ? AND workspace_id = ?",
                (approval_id, workspace_id),
            ).fetchone()
            if row is None:
                return ApprovalDecisionResult(ticket=None, error_code="APPROVAL_NOT_FOUND")
            ticket = self._row_to_ticket(row)
            if ticket.status is ApprovalStatus.CONSUMED:
                error = None if ticket.consumed_by_job_id == claim_id else "REPLAY_BLOCKED"
                return ApprovalDecisionResult(ticket=ticket, error_code=error)
            if (
                ticket.status is not ApprovalStatus.EXECUTED
                or ticket.resume_claimed_job_id != claim_id
            ):
                return ApprovalDecisionResult(ticket=ticket, error_code="APPROVAL_CONFLICT")
            updated = conn.execute(
                """
                UPDATE approvals
                SET status = ?, consumed_by_job_id = ?, consumed_at = ?, version = version + 1
                WHERE approval_id = ? AND workspace_id = ? AND version = ? AND status = ?
                  AND resume_claimed_job_id = ?
                """,
                (
                    ApprovalStatus.CONSUMED.value,
                    claim_id,
                    now.isoformat(),
                    approval_id,
                    workspace_id,
                    ticket.version,
                    ApprovalStatus.EXECUTED.value,
                    claim_id,
                ),
            ).rowcount
            if updated != 1:
                return ApprovalDecisionResult(ticket=ticket, error_code="APPROVAL_CONFLICT")
        return ApprovalDecisionResult(
            ticket=self.get(approval_id, workspace_id=workspace_id), error_code=None
        )

    def schema_version(self) -> str:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT value FROM approval_metadata WHERE key = 'schema_version'"
            ).fetchone()
        if row is None:
            return self.SCHEMA_VERSION
        return str(row["value"])

    def claim_execution(
        self, *, approval_id: str, workspace_id: str, attempt_id: str, actor: str
    ) -> ApprovalDecisionResult:
        self.expire_pending()
        now = datetime.now(UTC)
        with self._conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM approvals WHERE approval_id = ? AND workspace_id = ?",
                (approval_id, workspace_id),
            ).fetchone()
            if row is None:
                return ApprovalDecisionResult(ticket=None, error_code="APPROVAL_NOT_FOUND")
            ticket = self._row_to_ticket(row)
            if ticket.status is not ApprovalStatus.APPROVED:
                return ApprovalDecisionResult(
                    ticket=ticket, error_code="APPROVAL_EXECUTION_CLAIM_CONFLICT"
                )
            updated = conn.execute(
                """UPDATE approvals
                SET status = ?, execution_status = ?, execution_attempt_id = ?,
                    execution_claimed_at = ?, executed_by = ?, version = version + 1
                WHERE approval_id = ? AND workspace_id = ? AND version = ? AND status = ?""",
                (
                    ApprovalStatus.EXECUTING.value,
                    ExecutionStatus.EXECUTING.value,
                    attempt_id,
                    now.isoformat(),
                    actor,
                    approval_id,
                    workspace_id,
                    ticket.version,
                    ApprovalStatus.APPROVED.value,
                ),
            ).rowcount
            if updated != 1:
                return ApprovalDecisionResult(
                    ticket=ticket, error_code="APPROVAL_EXECUTION_CLAIM_CONFLICT"
                )
        return ApprovalDecisionResult(ticket=self.get(approval_id, workspace_id=workspace_id))

    def finalize_execution_success(
        self, *, approval_id: str, workspace_id: str, attempt_id: str, result_hash: str
    ) -> ApprovalDecisionResult:
        return self._finalize_execution(
            approval_id=approval_id,
            workspace_id=workspace_id,
            attempt_id=attempt_id,
            status=ApprovalStatus.EXECUTED,
            execution_status=ExecutionStatus.EXECUTED,
            result_hash=result_hash,
            error_code=None,
        )

    def finalize_execution_failure(
        self, *, approval_id: str, workspace_id: str, attempt_id: str, error_code: str
    ) -> ApprovalDecisionResult:
        return self._finalize_execution(
            approval_id=approval_id,
            workspace_id=workspace_id,
            attempt_id=attempt_id,
            status=ApprovalStatus.EXECUTION_FAILED,
            execution_status=ExecutionStatus.EXECUTION_FAILED,
            result_hash=None,
            error_code=error_code,
        )

    def _finalize_execution(
        self,
        *,
        approval_id: str,
        workspace_id: str,
        attempt_id: str,
        status: ApprovalStatus,
        execution_status: ExecutionStatus,
        result_hash: str | None,
        error_code: str | None,
    ) -> ApprovalDecisionResult:
        now = datetime.now(UTC)
        with self._conn() as conn:
            updated = conn.execute(
                """UPDATE approvals SET status = ?, execution_status = ?, executed_at = ?,
                execution_result_hash = ?, execution_error_code = ?, version = version + 1
                WHERE approval_id = ? AND workspace_id = ? AND status = ?
                  AND execution_attempt_id = ?""",
                (
                    status.value,
                    execution_status.value,
                    now.isoformat(),
                    result_hash,
                    error_code,
                    approval_id,
                    workspace_id,
                    ApprovalStatus.EXECUTING.value,
                    attempt_id,
                ),
            ).rowcount
        if updated != 1:
            return ApprovalDecisionResult(
                ticket=self.get(approval_id, workspace_id=workspace_id),
                error_code="APPROVAL_EXECUTION_ATTEMPT_MISMATCH",
            )
        return ApprovalDecisionResult(ticket=self.get(approval_id, workspace_id=workspace_id))

    def expire_pending(self) -> None:
        now_iso = datetime.now(UTC).isoformat()
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE approvals
                SET status = ?, version = version + 1
                WHERE status IN (?, ?) AND expires_at <= ?
                """,
                (
                    ApprovalStatus.EXPIRED.value,
                    ApprovalStatus.PENDING.value,
                    ApprovalStatus.APPROVED.value,
                    now_iso,
                ),
            )

    def decide(
        self,
        *,
        approval_id: str,
        workspace_id: str | None = None,
        approve: bool,
        actor: str,
        reason: str | None,
    ) -> ApprovalDecisionResult:
        self.expire_pending()
        ticket = self.get(approval_id, workspace_id=workspace_id)
        if ticket is None:
            return ApprovalDecisionResult(ticket=None, error_code="APPROVAL_NOT_FOUND")
        if ticket.status != ApprovalStatus.PENDING:
            return ApprovalDecisionResult(ticket=ticket, error_code="APPROVAL_CONFLICT")
        now = datetime.now(UTC)
        new_status = ApprovalStatus.APPROVED if approve else ApprovalStatus.REJECTED

        with self._conn() as conn:
            updated = conn.execute(
                """
                UPDATE approvals
                SET status = ?, actor = ?, decision_reason = ?, decided_at = ?,
                    version = version + 1
                WHERE approval_id = ? AND workspace_id = ? AND version = ? AND status = ?
                """,
                (
                    new_status.value,
                    actor,
                    reason,
                    now.isoformat(),
                    approval_id,
                    ticket.workspace_id,
                    ticket.version,
                    ApprovalStatus.PENDING.value,
                ),
            ).rowcount
        if updated == 0:
            return ApprovalDecisionResult(
                ticket=self.get(approval_id, workspace_id=workspace_id),
                error_code="APPROVAL_CONFLICT",
            )
        return ApprovalDecisionResult(
            ticket=self.get(approval_id, workspace_id=workspace_id), error_code=None
        )

    def mark_executed(
        self,
        *,
        approval_id: str,
        workspace_id: str | None = None,
        executed_by: str,
    ) -> ApprovalDecisionResult:
        self.expire_pending()
        ticket = self.get(approval_id, workspace_id=workspace_id)
        if ticket is None:
            return ApprovalDecisionResult(ticket=None, error_code="APPROVAL_NOT_FOUND")
        if ticket.status != ApprovalStatus.APPROVED:
            return ApprovalDecisionResult(ticket=ticket, error_code="APPROVAL_CONFLICT")
        if ticket.execution_status == ExecutionStatus.EXECUTED:
            return ApprovalDecisionResult(ticket=ticket, error_code="REPLAY_BLOCKED")

        now = datetime.now(UTC)
        with self._conn() as conn:
            updated = conn.execute(
                """
                UPDATE approvals
                SET status = ?, execution_status = ?, executed_at = ?, executed_by = ?,
                    version = version + 1
                WHERE approval_id = ? AND workspace_id = ? AND version = ? AND status = ?
                """,
                (
                    ApprovalStatus.EXECUTED.value,
                    ExecutionStatus.EXECUTED.value,
                    now.isoformat(),
                    executed_by,
                    approval_id,
                    ticket.workspace_id,
                    ticket.version,
                    ApprovalStatus.APPROVED.value,
                ),
            ).rowcount
        if updated == 0:
            return ApprovalDecisionResult(
                ticket=self.get(approval_id, workspace_id=workspace_id),
                error_code="APPROVAL_CONFLICT",
            )
        return ApprovalDecisionResult(
            ticket=self.get(approval_id, workspace_id=workspace_id), error_code=None
        )

    def mark_execution_failed(
        self,
        *,
        approval_id: str,
        error_code: str,
        workspace_id: str | None = None,
    ) -> ApprovalDecisionResult:
        ticket = self.get(approval_id, workspace_id=workspace_id)
        if ticket is None:
            return ApprovalDecisionResult(ticket=None, error_code="APPROVAL_NOT_FOUND")
        now = datetime.now(UTC)
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE approvals
                SET status = ?, execution_status = ?, executed_at = ?,
                    execution_error_code = ?, version = version + 1
                WHERE approval_id = ? AND workspace_id = ?
                """,
                (
                    ApprovalStatus.EXECUTION_FAILED.value,
                    ExecutionStatus.EXECUTION_FAILED.value,
                    now.isoformat(),
                    error_code,
                    approval_id,
                    ticket.workspace_id,
                ),
            )
        return ApprovalDecisionResult(
            ticket=self.get(approval_id, workspace_id=workspace_id), error_code=None
        )

    def mark_consumed(
        self,
        *,
        approval_id: str,
        workspace_id: str,
        consumed_by_job_id: str,
        execution_contract_hash: str | None = None,
        resume_token_ref: str | None = None,
    ) -> ApprovalDecisionResult:
        ticket = self.get(approval_id, workspace_id=workspace_id)
        if ticket is None:
            return ApprovalDecisionResult(ticket=None, error_code="APPROVAL_NOT_FOUND")
        if ticket.status != ApprovalStatus.EXECUTED:
            return ApprovalDecisionResult(ticket=ticket, error_code="APPROVAL_CONFLICT")
        effective_contract_hash = self._effective_execution_contract_hash(ticket)
        if (
            effective_contract_hash
            and execution_contract_hash
            and effective_contract_hash != execution_contract_hash
        ):
            return ApprovalDecisionResult(ticket=ticket, error_code="STALE_APPROVAL_SNAPSHOT")
        if effective_contract_hash and not execution_contract_hash:
            return ApprovalDecisionResult(ticket=ticket, error_code="STALE_APPROVAL_SNAPSHOT")
        if (
            ticket.resume_token_ref
            and resume_token_ref
            and ticket.resume_token_ref != resume_token_ref
        ):
            return ApprovalDecisionResult(ticket=ticket, error_code="APPROVAL_CONFLICT")

        now = datetime.now(UTC)
        with self._conn() as conn:
            updated = conn.execute(
                """
                UPDATE approvals
                SET status = ?, consumed_by_job_id = ?, consumed_at = ?, version = version + 1
                WHERE approval_id = ? AND workspace_id = ? AND version = ? AND status = ?
                """,
                (
                    ApprovalStatus.CONSUMED.value,
                    consumed_by_job_id,
                    now.isoformat(),
                    approval_id,
                    workspace_id,
                    ticket.version,
                    ApprovalStatus.EXECUTED.value,
                ),
            ).rowcount
        if updated == 0:
            return ApprovalDecisionResult(
                ticket=self.get(approval_id, workspace_id=workspace_id),
                error_code="APPROVAL_CONFLICT",
            )
        return ApprovalDecisionResult(
            ticket=self.get(approval_id, workspace_id=workspace_id), error_code=None
        )

    def attach_execution_contract(
        self,
        *,
        approval_id: str,
        workspace_id: str,
        execution_contract: dict[str, Any],
        execution_contract_hash: str,
        snapshot_hash: str,
    ) -> ApprovalDecisionResult:
        ticket = self.get(approval_id, workspace_id=workspace_id)
        if ticket is None:
            return ApprovalDecisionResult(ticket=None, error_code="APPROVAL_NOT_FOUND")
        snapshot = dict(ticket.snapshot)
        snapshot["execution_contract"] = execution_contract
        effective_snapshot_hash = _payload_hash(snapshot)
        _resume_token_ref, effective_contract_hash = derive_execution_contract_refs(
            source_job_id=ticket.run_id,
            approval_id=ticket.approval_id,
            snapshot_hash=effective_snapshot_hash,
            target_kind=ticket.target_kind,
            policy_hash=ticket.policy_hash,
            contract=execution_contract,
            fallback_action_hash=ticket.action_hash,
        )
        with self._conn() as conn:
            updated = conn.execute(
                """
                UPDATE approvals
                SET snapshot_hash = ?, snapshot_json = ?, execution_contract_hash = ?,
                    resume_token_ref = NULL, resume_claimed_job_id = NULL, resume_claimed_at = NULL,
                    version = version + 1
                WHERE approval_id = ? AND workspace_id = ? AND version = ?
                """,
                (
                    effective_snapshot_hash,
                    json.dumps(snapshot, ensure_ascii=False, sort_keys=True),
                    effective_contract_hash or execution_contract_hash,
                    approval_id,
                    workspace_id,
                    ticket.version,
                ),
            ).rowcount
        if updated == 0:
            return ApprovalDecisionResult(
                ticket=self.get(approval_id, workspace_id=workspace_id),
                error_code="APPROVAL_CONFLICT",
            )
        return ApprovalDecisionResult(
            ticket=self.get(approval_id, workspace_id=workspace_id), error_code=None
        )

    def claim_resume(
        self,
        *,
        approval_id: str,
        workspace_id: str,
        resume_job_id: str,
        resume_token_ref: str,
        execution_contract_hash: str,
    ) -> ApprovalDecisionResult:
        ticket = self.get(approval_id, workspace_id=workspace_id)
        if ticket is None:
            return ApprovalDecisionResult(ticket=None, error_code="APPROVAL_NOT_FOUND")
        if ticket.status != ApprovalStatus.EXECUTED:
            return ApprovalDecisionResult(ticket=ticket, error_code="APPROVAL_CONFLICT")
        if ticket.consumed_at is not None or ticket.consumed_by_job_id is not None:
            return ApprovalDecisionResult(ticket=ticket, error_code="REPLAY_BLOCKED")
        effective_contract_hash = self._effective_execution_contract_hash(ticket)
        if effective_contract_hash and effective_contract_hash != execution_contract_hash:
            return ApprovalDecisionResult(ticket=ticket, error_code="STALE_APPROVAL_SNAPSHOT")
        if (
            ticket.resume_claimed_job_id == resume_job_id
            and ticket.resume_token_ref == resume_token_ref
        ):
            return ApprovalDecisionResult(ticket=ticket, error_code=None)
        if (
            ticket.resume_claimed_job_id is not None
            and ticket.resume_claimed_job_id != resume_job_id
        ):
            return ApprovalDecisionResult(ticket=ticket, error_code="RESUME_DUPLICATE_SUPPRESSED")

        now = datetime.now(UTC)
        with self._conn() as conn:
            updated = conn.execute(
                """
                UPDATE approvals
                SET resume_token_ref = ?, resume_claimed_job_id = ?, resume_claimed_at = ?,
                    version = version + 1
                WHERE approval_id = ? AND workspace_id = ? AND version = ? AND status = ?
                  AND consumed_at IS NULL
                  AND (
                      resume_claimed_job_id IS NULL
                      OR (
                          resume_claimed_job_id = ?
                          AND resume_token_ref = ?
                      )
                  )
                """,
                (
                    resume_token_ref,
                    resume_job_id,
                    now.isoformat(),
                    approval_id,
                    workspace_id,
                    ticket.version,
                    ApprovalStatus.EXECUTED.value,
                    resume_job_id,
                    resume_token_ref,
                ),
            ).rowcount
        if updated == 0:
            current = self.get(approval_id, workspace_id=workspace_id)
            if (
                current is not None
                and current.resume_claimed_job_id == resume_job_id
                and current.resume_token_ref == resume_token_ref
            ):
                return ApprovalDecisionResult(ticket=current, error_code=None)
            return ApprovalDecisionResult(ticket=current, error_code="RESUME_DUPLICATE_SUPPRESSED")
        return ApprovalDecisionResult(
            ticket=self.get(approval_id, workspace_id=workspace_id), error_code=None
        )

    @staticmethod
    def _row_to_ticket(row: sqlite3.Row) -> ApprovalTicket:
        snapshot = json.loads(str(row["snapshot_json"]))
        ticket = ApprovalTicket(
            version=int(row["version"]),
            approval_id=str(row["approval_id"]),
            workspace_id=str(row["workspace_id"]),
            run_id=str(row["run_id"]),
            status=ApprovalStatus(str(row["status"])),
            target_kind=str(row["target_kind"]),
            target_ref=str(row["target_ref"]),
            action_hash=str(row["action_hash"]),
            policy_hash=str(row["policy_hash"]),
            request_hash=str(row["request_hash"]),
            snapshot_hash=str(row["snapshot_hash"]),
            snapshot=snapshot,
            expires_at=datetime.fromisoformat(str(row["expires_at"])),
            actor=str(row["actor"]) if row["actor"] else None,
            decision_reason=str(row["decision_reason"]) if row["decision_reason"] else None,
            execution_status=ExecutionStatus(str(row["execution_status"])),
            executed_at=(
                datetime.fromisoformat(str(row["executed_at"])) if row["executed_at"] else None
            ),
            execution_error_code=(
                str(row["execution_error_code"]) if row["execution_error_code"] else None
            ),
            executed_by=(str(row["executed_by"]) if row["executed_by"] else None),
            execution_contract_hash=(
                str(row["execution_contract_hash"]) if row["execution_contract_hash"] else None
            ),
            execution_attempt_id=(
                str(row["execution_attempt_id"]) if row["execution_attempt_id"] else None
            ),
            execution_claimed_at=(
                datetime.fromisoformat(str(row["execution_claimed_at"]))
                if row["execution_claimed_at"]
                else None
            ),
            execution_result_hash=(
                str(row["execution_result_hash"]) if row["execution_result_hash"] else None
            ),
            resume_token_ref=(str(row["resume_token_ref"]) if row["resume_token_ref"] else None),
            resume_claimed_job_id=(
                str(row["resume_claimed_job_id"]) if row["resume_claimed_job_id"] else None
            ),
            resume_claimed_at=(
                datetime.fromisoformat(str(row["resume_claimed_at"]))
                if row["resume_claimed_at"]
                else None
            ),
            consumed_by_job_id=(
                str(row["consumed_by_job_id"]) if row["consumed_by_job_id"] else None
            ),
            consumed_at=(
                datetime.fromisoformat(str(row["consumed_at"])) if row["consumed_at"] else None
            ),
            idempotency_key=str(row["idempotency_key"]),
            created_at=datetime.fromisoformat(str(row["created_at"])),
            decided_at=(
                datetime.fromisoformat(str(row["decided_at"])) if row["decided_at"] else None
            ),
        )
        effective_contract_hash = ApprovalStore._effective_execution_contract_hash(ticket)
        if effective_contract_hash is not None:
            ticket.execution_contract_hash = effective_contract_hash
        return ticket

    @staticmethod
    def _effective_execution_contract_hash(ticket: ApprovalTicket) -> str | None:
        contract = ticket.snapshot.get("execution_contract", {})
        if not isinstance(contract, dict) or not contract:
            return ticket.execution_contract_hash
        _resume_token_ref, effective_contract_hash = derive_execution_contract_refs(
            source_job_id=ticket.run_id,
            approval_id=ticket.approval_id,
            snapshot_hash=ticket.snapshot_hash,
            target_kind=ticket.target_kind,
            policy_hash=ticket.policy_hash,
            contract=contract,
            fallback_action_hash=ticket.action_hash,
        )
        return effective_contract_hash or ticket.execution_contract_hash


def _payload_hash(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _build_resume_token_ref(
    *,
    source_job_id: str,
    task_run_id: str,
    approval_id: str,
    snapshot_hash: str,
    target_kind: str,
) -> str:
    return _payload_hash(
        {
            "source_job_id": source_job_id,
            "task_run_id": task_run_id,
            "approval_id": approval_id,
            "snapshot_hash": snapshot_hash,
            "target_kind": target_kind,
        }
    )


def _build_execution_contract_hash(
    *,
    resume_token_ref: str,
    action_hash: str,
    policy_hash: str,
    contract: dict[str, Any],
) -> str:
    return _payload_hash(
        {
            "resume_token_ref": resume_token_ref,
            "action_hash": action_hash,
            "policy_hash": policy_hash,
            "contract": json.loads(json.dumps(contract, sort_keys=True, ensure_ascii=False)),
        }
    )


def derive_execution_contract_refs(
    *,
    source_job_id: str,
    approval_id: str,
    snapshot_hash: str,
    target_kind: str,
    policy_hash: str,
    contract: dict[str, Any],
    fallback_action_hash: str | None = None,
) -> tuple[str | None, str | None]:
    contract_task_run_id = str(contract.get("task_run_id") or "").strip()
    effective_target_kind = str(contract.get("target_kind") or target_kind or "").strip()
    effective_action_hash = str(
        contract.get("action_payload_hash") or fallback_action_hash or ""
    ).strip()
    if not (
        source_job_id
        and approval_id
        and snapshot_hash
        and contract_task_run_id
        and effective_target_kind
        and effective_action_hash
    ):
        return None, None
    resume_token_ref = _build_resume_token_ref(
        source_job_id=source_job_id,
        task_run_id=contract_task_run_id,
        approval_id=approval_id,
        snapshot_hash=snapshot_hash,
        target_kind=effective_target_kind,
    )
    execution_contract_hash = _build_execution_contract_hash(
        resume_token_ref=resume_token_ref,
        action_hash=effective_action_hash,
        policy_hash=policy_hash,
        contract=contract,
    )
    return resume_token_ref, execution_contract_hash
