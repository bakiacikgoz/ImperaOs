from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Any

from imperaos.memory.models import (
    MemoryOwnerType,
    MemoryRecordV3,
    MemoryScope,
    MemoryScopeFilter,
    MemoryVisibility,
)
from imperaos.runtime.paths import MEMORY_DB_PATH


@dataclass(slots=True)
class MemoryStoreWriteStatus:
    status: str
    memory_id: str | None
    dedup_hit: bool = False
    conflict_detected: bool = False
    expected_state_version: int | None = None
    committed_state_version: int | None = None
    memory_target: str | None = None
    blocking_reasons: list[str] | None = None


class MemoryStoreV3:
    SCHEMA_VERSION = "memory.v3"

    def __init__(self, db_path: str | Path = MEMORY_DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = RLock()
        self._configure_connection()
        self.ensure_schema()

    def _configure_connection(self) -> None:
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.execute("PRAGMA busy_timeout=5000")

    def ensure_schema(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS memory_records_v3 (
                    memory_id TEXT PRIMARY KEY,
                    schema_version TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    owner_type TEXT NOT NULL,
                    owner_id_hash TEXT NOT NULL,
                    visibility TEXT NOT NULL,
                    namespace TEXT NOT NULL DEFAULT 'default',
                    memory_target TEXT,
                    state_version INTEGER NOT NULL DEFAULT 1,
                    content_summary TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    embedding_ref TEXT,
                    salience REAL NOT NULL,
                    confidence REAL NOT NULL,
                    source_type TEXT NOT NULL,
                    source_run_id TEXT,
                    source_agent_id TEXT,
                    source_user_hash TEXT,
                    policy_tags_json TEXT NOT NULL DEFAULT '[]',
                    retention_class TEXT NOT NULL DEFAULT 'standard',
                    ttl_days INTEGER,
                    expires_at TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    provenance_json TEXT NOT NULL DEFAULT '{}',
                    idempotency_key TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE UNIQUE INDEX IF NOT EXISTS idx_mem_v3_idempotency
                    ON memory_records_v3(idempotency_key)
                    WHERE idempotency_key IS NOT NULL;
                CREATE INDEX IF NOT EXISTS idx_mem_v3_scope_owner
                    ON memory_records_v3(scope, owner_type, owner_id_hash, visibility);
                CREATE INDEX IF NOT EXISTS idx_mem_v3_status_expiry
                    ON memory_records_v3(status, expires_at);
                CREATE INDEX IF NOT EXISTS idx_mem_v3_target
                    ON memory_records_v3(
                        scope, owner_type, owner_id_hash, visibility, memory_target
                    );
                CREATE INDEX IF NOT EXISTS idx_mem_v3_source_run
                    ON memory_records_v3(source_run_id);
                CREATE INDEX IF NOT EXISTS idx_mem_v3_content_hash
                    ON memory_records_v3(content_hash);

                CREATE TABLE IF NOT EXISTS memory_targets_v3 (
                    target_key TEXT PRIMARY KEY,
                    scope TEXT NOT NULL,
                    owner_type TEXT NOT NULL,
                    owner_id_hash TEXT NOT NULL,
                    visibility TEXT NOT NULL,
                    namespace TEXT NOT NULL DEFAULT 'default',
                    memory_target TEXT NOT NULL,
                    current_version INTEGER NOT NULL DEFAULT 0,
                    current_memory_id TEXT,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS memory_events_v3 (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    memory_id TEXT,
                    proposal_id TEXT,
                    actor_id_hash TEXT,
                    agent_id TEXT,
                    policy_decision_json TEXT NOT NULL,
                    event_hash TEXT NOT NULL,
                    evidence_ref TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS memory_vectors_v3 (
                    embedding_ref TEXT PRIMARY KEY,
                    memory_id TEXT NOT NULL,
                    backend TEXT NOT NULL,
                    dim INTEGER NOT NULL,
                    vector_hash TEXT NOT NULL,
                    vector_blob BLOB,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS memory_authority_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )
            self._conn.execute(
                """
                INSERT INTO memory_authority_metadata(key, value)
                VALUES ('memory_v3_schema_version', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (self.SCHEMA_VERSION,),
            )
            self._conn.commit()

    def write_record(
        self,
        record: MemoryRecordV3,
        *,
        idempotency_key: str,
        expected_state_version: int | None,
    ) -> MemoryStoreWriteStatus:
        with self._lock:
            existing = self._conn.execute(
                "SELECT memory_id, state_version FROM memory_records_v3 WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            if existing is not None:
                return MemoryStoreWriteStatus(
                    status="dedup",
                    memory_id=str(existing["memory_id"]),
                    dedup_hit=True,
                    committed_state_version=int(existing["state_version"]),
                    memory_target=record.memory_target,
                )

            target_key = self._target_key(record) if record.memory_target else None
            committed_version = record.state_version
            if target_key is not None:
                current = self._conn.execute(
                    "SELECT current_version FROM memory_targets_v3 WHERE target_key = ?",
                    (target_key,),
                ).fetchone()
                current_version = int(current["current_version"]) if current is not None else 0
                if expected_state_version is None:
                    return MemoryStoreWriteStatus(
                        status="conflict",
                        memory_id=None,
                        conflict_detected=True,
                        expected_state_version=None,
                        committed_state_version=current_version,
                        memory_target=record.memory_target,
                        blocking_reasons=["MEMORY_TARGET_VERSION_REQUIRED"],
                    )
                if current_version != expected_state_version:
                    return MemoryStoreWriteStatus(
                        status="conflict",
                        memory_id=None,
                        conflict_detected=True,
                        expected_state_version=expected_state_version,
                        committed_state_version=current_version,
                        memory_target=record.memory_target,
                        blocking_reasons=["MEMORY_TARGET_VERSION_MISMATCH"],
                    )
                committed_version = current_version + 1
                record = record.model_copy(update={"state_version": committed_version})

            payload = record.model_dump(mode="json", by_alias=False)
            self._conn.execute(
                """
                INSERT INTO memory_records_v3(
                    memory_id, schema_version, scope, owner_type, owner_id_hash, visibility,
                    namespace, memory_target, state_version, content_summary, content_hash,
                    embedding_ref, salience, confidence, source_type, source_run_id,
                    source_agent_id, source_user_hash, policy_tags_json, retention_class,
                    ttl_days, expires_at, status, provenance_json, idempotency_key,
                    created_at, updated_at
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    payload["memory_id"],
                    payload["schema_version"],
                    payload["scope"],
                    payload["owner_type"],
                    payload["owner_id_hash"],
                    payload["visibility"],
                    payload["namespace"],
                    payload["memory_target"],
                    payload["state_version"],
                    payload["content_summary"],
                    payload["content_hash"],
                    payload["embedding_ref"],
                    payload["salience"],
                    payload["confidence"],
                    payload["source_type"],
                    payload["source_run_id"],
                    payload["source_agent_id"],
                    payload["source_user_hash"],
                    json.dumps(payload["policy_tags"], sort_keys=True),
                    payload["retention_class"],
                    payload["ttl_days"],
                    payload["expires_at"],
                    payload["status"],
                    json.dumps(payload["provenance"], sort_keys=True),
                    idempotency_key,
                    payload["created_at"],
                    payload["updated_at"],
                ),
            )
            if target_key is not None and record.memory_target is not None:
                self._conn.execute(
                    """
                    INSERT INTO memory_targets_v3(
                        target_key, scope, owner_type, owner_id_hash, visibility, namespace,
                        memory_target, current_version, current_memory_id, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(target_key) DO UPDATE SET
                        current_version = excluded.current_version,
                        current_memory_id = excluded.current_memory_id,
                        updated_at = excluded.updated_at
                    """,
                    (
                        target_key,
                        str(record.scope),
                        str(record.owner_type),
                        record.owner_id_hash,
                        str(record.visibility),
                        record.namespace,
                        record.memory_target,
                        committed_version,
                        record.memory_id,
                        _iso_now(),
                    ),
                )
            self._conn.commit()
            return MemoryStoreWriteStatus(
                status="written",
                memory_id=record.memory_id,
                committed_state_version=committed_version,
                expected_state_version=expected_state_version,
                memory_target=record.memory_target,
            )

    def get_record(self, memory_id: str) -> MemoryRecordV3 | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM memory_records_v3 WHERE memory_id = ?",
                (memory_id,),
            ).fetchone()
            return _row_to_record(row) if row is not None else None

    def search_records(
        self,
        *,
        query: str,
        scope_filters: list[MemoryScopeFilter],
        visibility_filters: list[MemoryVisibility],
        include_expired: bool = False,
        limit: int = 20,
    ) -> list[MemoryRecordV3]:
        clauses = ["status = 'active'"]
        params: list[Any] = []
        if not include_expired:
            clauses.append("(expires_at IS NULL OR expires_at > ?)")
            params.append(_iso_now())
        if visibility_filters:
            clauses.append(
                f"visibility IN ({','.join('?' for _ in visibility_filters)})"
            )
            params.extend(str(item) for item in visibility_filters)
        if scope_filters:
            scope_clauses: list[str] = []
            for item in scope_filters:
                scope_clauses.append(
                    "(scope = ? AND owner_type = ? AND owner_id_hash = ? AND namespace = ?)"
                )
                params.extend(
                    [str(item.scope), str(item.owner_type), item.owner_id_hash, item.namespace]
                )
            clauses.append("(" + " OR ".join(scope_clauses) + ")")
        terms = [term.lower() for term in query.split() if len(term) > 1][:8]
        if terms:
            like_clauses = []
            for term in terms:
                like_clauses.append("lower(content_summary) LIKE ?")
                params.append(f"%{term}%")
            clauses.append("(" + " OR ".join(like_clauses) + ")")
        sql = (
            "SELECT * FROM memory_records_v3 WHERE "
            + " AND ".join(clauses)
            + " ORDER BY salience DESC, created_at DESC LIMIT ?"
        )
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
            return [_row_to_record(row) for row in rows]

    def list_records(
        self,
        *,
        scope_filters: list[MemoryScopeFilter] | None = None,
        visibility_filters: list[MemoryVisibility] | None = None,
        include_expired: bool = False,
        limit: int = 500,
    ) -> list[MemoryRecordV3]:
        clauses = ["status = 'active'"]
        params: list[Any] = []
        if not include_expired:
            clauses.append("(expires_at IS NULL OR expires_at > ?)")
            params.append(_iso_now())
        if visibility_filters:
            clauses.append(
                f"visibility IN ({','.join('?' for _ in visibility_filters)})"
            )
            params.extend(str(item) for item in visibility_filters)
        if scope_filters:
            scope_clauses: list[str] = []
            for item in scope_filters:
                scope_clauses.append(
                    "(scope = ? AND owner_type = ? AND owner_id_hash = ? AND namespace = ?)"
                )
                params.extend(
                    [str(item.scope), str(item.owner_type), item.owner_id_hash, item.namespace]
                )
            clauses.append("(" + " OR ".join(scope_clauses) + ")")
        sql = (
            "SELECT * FROM memory_records_v3 WHERE "
            + " AND ".join(clauses)
            + " ORDER BY updated_at DESC, created_at DESC LIMIT ?"
        )
        params.append(limit)
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
            return [_row_to_record(row) for row in rows]

    def tombstone(
        self,
        *,
        memory_id: str,
        actor_id_hash: str,
        reason: str,
    ) -> bool:
        _ = actor_id_hash, reason
        with self._lock:
            cur = self._conn.execute(
                """
                UPDATE memory_records_v3
                SET status = 'tombstoned', updated_at = ?
                WHERE memory_id = ? AND status != 'tombstoned'
                """,
                (_iso_now(), memory_id),
            )
            self._conn.commit()
            return cur.rowcount > 0

    def target_version(
        self,
        *,
        scope: MemoryScope,
        owner_type: MemoryOwnerType,
        owner_id_hash: str,
        visibility: MemoryVisibility,
        namespace: str,
        memory_target: str,
    ) -> int:
        key = _target_key(
            scope=scope,
            owner_type=owner_type,
            owner_id_hash=owner_id_hash,
            visibility=visibility,
            namespace=namespace,
            memory_target=memory_target,
        )
        with self._lock:
            row = self._conn.execute(
                "SELECT current_version FROM memory_targets_v3 WHERE target_key = ?",
                (key,),
            ).fetchone()
            return int(row["current_version"]) if row is not None else 0

    def stats(self) -> dict[str, Any]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT status, count(*) AS count FROM memory_records_v3 GROUP BY status"
            ).fetchall()
            counts = {str(row["status"]): int(row["count"]) for row in rows}
            denied = self._conn.execute(
                "SELECT count(*) AS count FROM memory_events_v3 "
                "WHERE event_type = 'memory.write.denied'"
            ).fetchone()
            pending = self._conn.execute(
                "SELECT count(*) AS count FROM memory_events_v3 "
                "WHERE event_type IN ("
                "'memory.write.approval_required',"
                "'memory.write.proposal_only'"
                ")"
            ).fetchone()
            scopes = self._conn.execute(
                """
                SELECT scope, visibility, count(*) AS count
                FROM memory_records_v3
                WHERE status = 'active'
                GROUP BY scope, visibility
                ORDER BY scope, visibility
                """
            ).fetchall()
        return {
            "schemaVersion": self.SCHEMA_VERSION,
            "records": {
                "active": counts.get("active", 0),
                "expired": counts.get("expired", 0),
                "tombstoned": counts.get("tombstoned", 0),
                "deniedWrites": int(denied["count"]) if denied is not None else 0,
                "pendingProposals": int(pending["count"]) if pending is not None else 0,
            },
            "scopes": [
                {
                    "scope": str(row["scope"]),
                    "visibility": str(row["visibility"]),
                    "activeRecords": int(row["count"]),
                    "policy": "scoped_policy",
                }
                for row in scopes
            ],
        }

    def record_event(
        self,
        *,
        event_id: str,
        event_type: str,
        memory_id: str | None,
        proposal_id: str | None,
        actor_id_hash: str | None,
        agent_id: str | None,
        policy_decision: dict[str, Any],
        event_hash: str,
        evidence_ref: str | None,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO memory_events_v3(
                    event_id, event_type, memory_id, proposal_id, actor_id_hash, agent_id,
                    policy_decision_json, event_hash, evidence_ref, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    event_type,
                    memory_id,
                    proposal_id,
                    actor_id_hash,
                    agent_id,
                    json.dumps(policy_decision, sort_keys=True),
                    event_hash,
                    evidence_ref,
                    _iso_now(),
                ),
            )
            self._conn.commit()

    def _target_key(self, record: MemoryRecordV3) -> str:
        assert record.memory_target is not None
        return _target_key(
            scope=record.scope,
            owner_type=record.owner_type,
            owner_id_hash=record.owner_id_hash,
            visibility=record.visibility,
            namespace=record.namespace,
            memory_target=record.memory_target,
        )


def _target_key(
    *,
    scope: MemoryScope,
    owner_type: MemoryOwnerType,
    owner_id_hash: str,
    visibility: MemoryVisibility,
    namespace: str,
    memory_target: str,
) -> str:
    return "|".join(
        [
            str(scope),
            str(owner_type),
            owner_id_hash,
            str(visibility),
            namespace,
            memory_target,
        ]
    )


def _row_to_record(row: sqlite3.Row) -> MemoryRecordV3:
    return MemoryRecordV3(
        memoryId=row["memory_id"],
        schemaVersion=row["schema_version"],
        scope=row["scope"],
        ownerType=row["owner_type"],
        ownerIdHash=row["owner_id_hash"],
        visibility=row["visibility"],
        namespace=row["namespace"],
        memoryTarget=row["memory_target"],
        stateVersion=row["state_version"],
        contentSummary=row["content_summary"],
        contentHash=row["content_hash"],
        embeddingRef=row["embedding_ref"],
        salience=row["salience"],
        confidence=row["confidence"],
        sourceType=row["source_type"],
        sourceRunId=row["source_run_id"],
        sourceAgentId=row["source_agent_id"],
        sourceUserHash=row["source_user_hash"],
        policyTags=json.loads(row["policy_tags_json"] or "[]"),
        retentionClass=row["retention_class"],
        ttlDays=row["ttl_days"],
        expiresAt=row["expires_at"],
        status=row["status"],
        provenance=json.loads(row["provenance_json"] or "{}"),
        createdAt=row["created_at"],
        updatedAt=row["updated_at"],
    )


def _iso_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
