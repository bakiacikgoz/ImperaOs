from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from imperaos.memory.models import sha256_text, stable_id, utc_now
from imperaos.memory.workspace_models import (
    MemoryPrincipal,
    MemoryScopeAclRule,
    MemoryWorkspace,
    MemoryWorkspaceMembership,
    StoreWriteResult,
    WorkspaceMemoryCommitResult,
    WorkspaceMemoryConflict,
    WorkspaceMemoryRecord,
    WorkspaceMemoryTombstoneRequest,
    WorkspaceMemoryTombstoneResult,
)


class WorkspaceMemoryStore:
    SCHEMA_VERSION = "workspace-memory-store/v1"

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self.initialize_schema()

    def initialize_schema(self) -> None:
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS memory_workspaces (
                    workspace_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS memory_principals (
                    principal_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS memory_memberships (
                    membership_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    principal_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    UNIQUE(workspace_id, principal_id)
                );
                CREATE TABLE IF NOT EXISTS memory_scope_acl_rules (
                    acl_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    scope_type TEXT NOT NULL,
                    scope_id TEXT NOT NULL,
                    principal_id TEXT,
                    role TEXT,
                    effect TEXT NOT NULL,
                    permissions_json TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS workspace_memory_records (
                    memory_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    scope_type TEXT NOT NULL,
                    scope_id TEXT NOT NULL,
                    memory_target TEXT,
                    state_version INTEGER NOT NULL,
                    content_hash TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    classification TEXT NOT NULL,
                    tombstoned_at_utc TEXT,
                    payload_json TEXT NOT NULL,
                    updated_at_utc TEXT NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS idx_workspace_memory_target
                    ON workspace_memory_records(workspace_id, scope_type, scope_id, memory_target)
                    WHERE memory_target IS NOT NULL AND tombstoned_at_utc IS NULL;
                CREATE INDEX IF NOT EXISTS idx_workspace_memory_query
                    ON workspace_memory_records(workspace_id, scope_type, scope_id, updated_at_utc);
                CREATE TABLE IF NOT EXISTS workspace_memory_versions (
                    version_id TEXT PRIMARY KEY,
                    memory_id TEXT NOT NULL,
                    state_version INTEGER NOT NULL,
                    content_hash TEXT NOT NULL,
                    summary_hash TEXT NOT NULL,
                    changed_by_principal_id TEXT NOT NULL,
                    change_reason TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS workspace_memory_conflicts (
                    conflict_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS workspace_memory_proposals (
                    proposal_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    principal_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS workspace_memory_tombstones (
                    tombstone_id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    memory_id TEXT NOT NULL,
                    principal_id TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL
                );
                """
            )
            self._conn.commit()

    def create_workspace(self, workspace: MemoryWorkspace) -> StoreWriteResult:
        payload = workspace.model_dump(mode="json", by_alias=True)
        with self._lock:
            existed = self._conn.execute(
                "SELECT 1 FROM memory_workspaces WHERE workspace_id = ?",
                (workspace.workspace_id,),
            ).fetchone()
            self._conn.execute(
                """
                INSERT OR REPLACE INTO memory_workspaces(
                    workspace_id, payload_json, status, updated_at_utc
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    workspace.workspace_id,
                    json.dumps(payload, sort_keys=True),
                    workspace.status,
                    workspace.updated_at_utc.isoformat(),
                ),
            )
            self._conn.commit()
        return StoreWriteResult(
            status="updated" if existed else "created",
            id=workspace.workspace_id,
        )

    def upsert_principal(self, principal: MemoryPrincipal) -> StoreWriteResult:
        payload = principal.model_dump(mode="json", by_alias=True)
        with self._lock:
            existed = self._conn.execute(
                "SELECT 1 FROM memory_principals WHERE principal_id = ?",
                (principal.principal_id,),
            ).fetchone()
            self._conn.execute(
                """
                INSERT OR REPLACE INTO memory_principals(principal_id, payload_json, status)
                VALUES (?, ?, ?)
                """,
                (principal.principal_id, json.dumps(payload, sort_keys=True), principal.status),
            )
            self._conn.commit()
        return StoreWriteResult(
            status="updated" if existed else "created",
            id=principal.principal_id,
        )

    def grant_membership(self, membership: MemoryWorkspaceMembership) -> StoreWriteResult:
        payload = membership.model_dump(mode="json", by_alias=True)
        with self._lock:
            existed = self._conn.execute(
                "SELECT 1 FROM memory_memberships WHERE workspace_id = ? AND principal_id = ?",
                (membership.workspace_id, membership.principal_id),
            ).fetchone()
            self._conn.execute(
                """
                INSERT OR REPLACE INTO memory_memberships(
                    membership_id, workspace_id, principal_id, payload_json, status
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    membership.membership_id,
                    membership.workspace_id,
                    membership.principal_id,
                    json.dumps(payload, sort_keys=True),
                    membership.status,
                ),
            )
            self._conn.commit()
        return StoreWriteResult(
            status="updated" if existed else "created",
            id=membership.membership_id,
        )

    def upsert_acl_rule(self, rule: MemoryScopeAclRule) -> StoreWriteResult:
        payload = rule.model_dump(mode="json", by_alias=True)
        with self._lock:
            existed = self._conn.execute(
                "SELECT 1 FROM memory_scope_acl_rules WHERE acl_id = ?",
                (rule.acl_id,),
            ).fetchone()
            self._conn.execute(
                """
                INSERT OR REPLACE INTO memory_scope_acl_rules(
                    acl_id, workspace_id, scope_type, scope_id, principal_id, role,
                    effect, permissions_json, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rule.acl_id,
                    rule.workspace_id,
                    rule.scope_type,
                    rule.scope_id,
                    rule.principal_id,
                    rule.role,
                    rule.effect,
                    json.dumps(list(rule.permissions), sort_keys=True),
                    json.dumps(payload, sort_keys=True),
                ),
            )
            self._conn.commit()
        return StoreWriteResult(status="updated" if existed else "created", id=rule.acl_id)

    def write_record(
        self,
        record: WorkspaceMemoryRecord,
        *,
        expected_state_version: int | None,
        changed_by_principal_id: str | None = None,
        change_reason: str = "workspace memory write",
    ) -> WorkspaceMemoryCommitResult:
        with self._lock:
            existing = self._target_row(record)
            if existing is not None:
                local_version = int(existing["state_version"])
                if existing["content_hash"] == record.content_hash:
                    return WorkspaceMemoryCommitResult(
                        status="committed",
                        memoryId=str(existing["memory_id"]),
                        stateVersion=local_version,
                    )
                if expected_state_version is not None and expected_state_version != local_version:
                    conflict = self._create_conflict(
                        record=record,
                        local_state_version=local_version,
                        conflict_type="state_version_mismatch",
                    )
                    return WorkspaceMemoryCommitResult(status="conflict", conflict=conflict)
                if (
                    expected_state_version is None
                    and existing["content_hash"] != record.content_hash
                ):
                    conflict = self._create_conflict(
                        record=record,
                        local_state_version=local_version,
                        conflict_type="same_target_different_hash",
                    )
                    return WorkspaceMemoryCommitResult(status="conflict", conflict=conflict)
                committed_id = str(existing["memory_id"])
                committed_version = local_version + 1
            else:
                committed_id = record.memory_id
                committed_version = max(1, (expected_state_version or 0) + 1)

            committed = record.model_copy(
                update={
                    "memory_id": committed_id,
                    "state_version": committed_version,
                    "updated_at_utc": utc_now(),
                }
            )
            payload = committed.model_dump(mode="json", by_alias=True)
            self._conn.execute(
                """
                INSERT OR REPLACE INTO workspace_memory_records(
                    memory_id, workspace_id, scope_type, scope_id, memory_target, state_version,
                    content_hash, summary, classification, tombstoned_at_utc, payload_json,
                    updated_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    committed.memory_id,
                    committed.workspace_id,
                    committed.scope_type,
                    committed.scope_id,
                    committed.memory_target,
                    committed.state_version,
                    committed.content_hash,
                    committed.summary,
                    committed.classification,
                    committed.tombstoned_at_utc.isoformat()
                    if committed.tombstoned_at_utc
                    else None,
                    json.dumps(payload, sort_keys=True),
                    committed.updated_at_utc.isoformat(),
                ),
            )
            version_id = stable_id("wm_ver", committed.memory_id, committed.state_version)
            self._conn.execute(
                """
                INSERT OR REPLACE INTO workspace_memory_versions(
                    version_id, memory_id, state_version, content_hash, summary_hash,
                    changed_by_principal_id, change_reason, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    version_id,
                    committed.memory_id,
                    committed.state_version,
                    committed.content_hash,
                    sha256_text(committed.summary),
                    changed_by_principal_id or committed.owner_principal_id,
                    change_reason,
                    utc_now().isoformat(),
                ),
            )
            self._conn.commit()
            return WorkspaceMemoryCommitResult(
                status="committed",
                memoryId=committed.memory_id,
                stateVersion=committed.state_version,
            )

    def query_records(
        self,
        *,
        workspace_id: str,
        scope_type: str,
        scope_id: str,
        query: str = "",
        limit: int = 50,
        include_secret_like: bool = False,
    ) -> list[WorkspaceMemoryRecord]:
        clauses = [
            "workspace_id = ?",
            "scope_type = ?",
            "scope_id = ?",
            "tombstoned_at_utc IS NULL",
        ]
        params: list[Any] = [workspace_id, scope_type, scope_id]
        if not include_secret_like:
            clauses.append("classification != 'secret_like'")
        terms = [term.lower() for term in query.split() if len(term) > 1][:8]
        if terms:
            term_clauses = []
            for term in terms:
                term_clauses.append("lower(summary) LIKE ?")
                params.append(f"%{term}%")
            clauses.append("(" + " OR ".join(term_clauses) + ")")
        sql = (
            "SELECT payload_json FROM workspace_memory_records WHERE "
            + " AND ".join(clauses)
            + " ORDER BY state_version DESC, updated_at_utc DESC LIMIT ?"
        )
        params.append(max(1, min(limit, 50)))
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [
            WorkspaceMemoryRecord.model_validate_json(str(row["payload_json"])) for row in rows
        ]

    def tombstone_record(
        self,
        request: WorkspaceMemoryTombstoneRequest,
    ) -> WorkspaceMemoryTombstoneResult:
        now = utc_now()
        with self._lock:
            row = self._conn.execute(
                """
                SELECT payload_json FROM workspace_memory_records
                WHERE workspace_id = ? AND memory_id = ? AND tombstoned_at_utc IS NULL
                """,
                (request.workspace_id, request.memory_id),
            ).fetchone()
            if row is None:
                return WorkspaceMemoryTombstoneResult(status="missing", memoryId=request.memory_id)
            record = WorkspaceMemoryRecord.model_validate_json(str(row["payload_json"]))
            updated = record.model_copy(update={"tombstoned_at_utc": now, "updated_at_utc": now})
            self._conn.execute(
                """
                UPDATE workspace_memory_records
                SET tombstoned_at_utc = ?, updated_at_utc = ?, payload_json = ?
                WHERE memory_id = ?
                """,
                (
                    now.isoformat(),
                    now.isoformat(),
                    json.dumps(updated.model_dump(mode="json", by_alias=True), sort_keys=True),
                    request.memory_id,
                ),
            )
            self._conn.execute(
                """
                INSERT OR REPLACE INTO workspace_memory_tombstones(
                    tombstone_id, workspace_id, memory_id, principal_id, reason, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    stable_id("wm_tomb", request.workspace_id, request.memory_id, now.isoformat()),
                    request.workspace_id,
                    request.memory_id,
                    request.principal_id,
                    request.reason,
                    now.isoformat(),
                ),
            )
            self._conn.commit()
        return WorkspaceMemoryTombstoneResult(status="tombstoned", memoryId=request.memory_id)

    def get_workspace(self, workspace_id: str) -> MemoryWorkspace | None:
        row = self._fetch_one(
            "SELECT payload_json FROM memory_workspaces WHERE workspace_id = ?",
            (workspace_id,),
        )
        return MemoryWorkspace.model_validate_json(str(row["payload_json"])) if row else None

    def get_principal(self, principal_id: str) -> MemoryPrincipal | None:
        row = self._fetch_one(
            "SELECT payload_json FROM memory_principals WHERE principal_id = ?",
            (principal_id,),
        )
        return MemoryPrincipal.model_validate_json(str(row["payload_json"])) if row else None

    def get_membership(
        self,
        *,
        workspace_id: str,
        principal_id: str,
    ) -> MemoryWorkspaceMembership | None:
        row = self._fetch_one(
            """
            SELECT payload_json FROM memory_memberships
            WHERE workspace_id = ? AND principal_id = ?
            """,
            (workspace_id, principal_id),
        )
        return (
            MemoryWorkspaceMembership.model_validate_json(str(row["payload_json"]))
            if row
            else None
        )

    def acl_rules(
        self,
        *,
        workspace_id: str,
        scope_type: str,
        scope_id: str,
    ) -> list[MemoryScopeAclRule]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT payload_json FROM memory_scope_acl_rules
                WHERE workspace_id = ? AND scope_type = ? AND scope_id = ?
                ORDER BY effect DESC, acl_id ASC
                """,
                (workspace_id, scope_type, scope_id),
            ).fetchall()
        return [MemoryScopeAclRule.model_validate_json(str(row["payload_json"])) for row in rows]

    def record_proposal(
        self,
        *,
        proposal_id: str,
        workspace_id: str,
        principal_id: str,
        payload: dict[str, Any],
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO workspace_memory_proposals(
                    proposal_id, workspace_id, principal_id, status, payload_json, created_at_utc
                ) VALUES (?, ?, ?, 'pending', ?, ?)
                """,
                (
                    proposal_id,
                    workspace_id,
                    principal_id,
                    json.dumps(payload, sort_keys=True),
                    utc_now().isoformat(),
                ),
            )
            self._conn.commit()

    def list_conflicts(self, workspace_id: str) -> list[WorkspaceMemoryConflict]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT payload_json FROM workspace_memory_conflicts
                WHERE workspace_id = ? AND decision = 'pending'
                ORDER BY created_at_utc DESC
                """,
                (workspace_id,),
            ).fetchall()
        return [
            WorkspaceMemoryConflict.model_validate_json(str(row["payload_json"]))
            for row in rows
        ]

    def stats(self, workspace_id: str | None = None) -> dict[str, int]:
        workspace_clause = "WHERE workspace_id = ?" if workspace_id else ""
        workspace_params = (workspace_id,) if workspace_id else ()
        with self._lock:
            workspace_count = self._count("memory_workspaces", "", ())
            principal_count = self._count("memory_principals", "", ())
            scope_clause = (
                f"{workspace_clause} AND tombstoned_at_utc IS NULL"
                if workspace_id
                else "WHERE tombstoned_at_utc IS NULL"
            )
            proposal_clause = (
                f"{workspace_clause} AND status = 'pending'"
                if workspace_id
                else "WHERE status = 'pending'"
            )
            conflict_clause = (
                f"{workspace_clause} AND decision = 'pending'"
                if workspace_id
                else "WHERE decision = 'pending'"
            )
            scope_count = self._count(
                "workspace_memory_records",
                scope_clause,
                workspace_params,
            )
            proposal_count = self._count(
                "workspace_memory_proposals",
                proposal_clause,
                workspace_params,
            )
            conflict_count = self._count(
                "workspace_memory_conflicts",
                conflict_clause,
                workspace_params,
            )
        return {
            "workspaceCount": workspace_count,
            "principalCount": principal_count,
            "activeScopeCount": scope_count,
            "pendingProposalCount": proposal_count,
            "pendingConflictCount": conflict_count,
        }

    def records_for_sync(
        self,
        workspace_id: str,
        limit: int = 10000,
    ) -> list[WorkspaceMemoryRecord]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT payload_json FROM workspace_memory_records
                WHERE workspace_id = ? AND tombstoned_at_utc IS NULL
                ORDER BY updated_at_utc ASC LIMIT ?
                """,
                (workspace_id, max(1, min(limit, 10000))),
            ).fetchall()
        return [WorkspaceMemoryRecord.model_validate_json(str(row["payload_json"])) for row in rows]

    def find_record_by_target(
        self,
        *,
        workspace_id: str,
        scope_type: str,
        scope_id: str,
        memory_target: str,
    ) -> WorkspaceMemoryRecord | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT payload_json FROM workspace_memory_records
                WHERE workspace_id = ? AND scope_type = ? AND scope_id = ?
                  AND memory_target = ? AND tombstoned_at_utc IS NULL
                """,
                (workspace_id, scope_type, scope_id, memory_target),
            ).fetchone()
        return WorkspaceMemoryRecord.model_validate_json(str(row["payload_json"])) if row else None

    def _target_row(self, record: WorkspaceMemoryRecord) -> sqlite3.Row | None:
        if record.memory_target is None:
            return None
        return self._conn.execute(
            """
            SELECT * FROM workspace_memory_records
            WHERE workspace_id = ? AND scope_type = ? AND scope_id = ?
              AND memory_target = ? AND tombstoned_at_utc IS NULL
            """,
            (record.workspace_id, record.scope_type, record.scope_id, record.memory_target),
        ).fetchone()

    def _create_conflict(
        self,
        *,
        record: WorkspaceMemoryRecord,
        local_state_version: int | None,
        conflict_type: str,
    ) -> WorkspaceMemoryConflict:
        conflict = WorkspaceMemoryConflict(
            conflictId=stable_id(
                "wm_conflict",
                record.workspace_id,
                record.memory_target or record.memory_id,
                record.content_hash,
                local_state_version,
            ),
            workspaceId=record.workspace_id,
            memoryId=record.memory_id,
            memoryTarget=record.memory_target,
            localStateVersion=local_state_version,
            incomingStateVersion=record.state_version,
            conflictType=conflict_type,
            requiresApproval=True,
        )
        self._conn.execute(
            """
            INSERT OR REPLACE INTO workspace_memory_conflicts(
                conflict_id, workspace_id, decision, payload_json, created_at_utc
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                conflict.conflict_id,
                conflict.workspace_id,
                conflict.decision,
                json.dumps(conflict.model_dump(mode="json", by_alias=True), sort_keys=True),
                conflict.created_at_utc.isoformat(),
            ),
        )
        self._conn.commit()
        return conflict

    def _fetch_one(self, sql: str, params: tuple[Any, ...]) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(sql, params).fetchone()

    def _count(self, table: str, clause: str, params: tuple[Any, ...]) -> int:
        row = self._conn.execute(
            f"SELECT count(*) AS count FROM {table} {clause}",
            params,
        ).fetchone()
        return int(row["count"]) if row is not None else 0
