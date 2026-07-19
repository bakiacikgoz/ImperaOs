from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import RLock
from typing import Any

from imperaos.runtime.paths import MEMORY_DB_PATH


@dataclass(slots=True)
class MemoryRecord:
    id: int
    session_id: str
    task_type: str
    scope: str
    team_id: str | None
    case_id: str | None
    job_id: str | None
    producer_agent_id: str | None
    producer_role: str | None
    visibility: str
    content: str
    content_hash: str
    salience: float
    created_at: str
    expires_at: str | None
    metadata: dict[str, Any]


@dataclass(slots=True)
class MemoryWriteStatus:
    record_id: int | None
    dedup_hit: bool
    conflict_detected: bool = False
    expected_state_version: int | None = None
    committed_state_version: int | None = None
    memory_target: str | None = None


class PersistentMemoryStore:
    """Local SQLite store for long-term memory candidates."""
    SCHEMA_VERSION = "2.0"

    def __init__(self, db_path: str | Path = MEMORY_DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = RLock()
        self._configure_connection()
        self._ensure_schema()

    def _configure_connection(self) -> None:
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.execute("PRAGMA busy_timeout=5000")

    def _ensure_schema(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    scope TEXT NOT NULL DEFAULT 'session',
                    team_id TEXT,
                    case_id TEXT,
                    job_id TEXT,
                    producer_agent_id TEXT,
                    producer_role TEXT,
                    visibility TEXT NOT NULL DEFAULT 'private',
                    content TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    salience REAL NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                    expires_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_memories_created_at ON memories(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_memories_task_type ON memories(task_type);
                CREATE INDEX IF NOT EXISTS idx_memories_session_id ON memories(session_id);

                CREATE TABLE IF NOT EXISTS memory_targets (
                    target_key TEXT PRIMARY KEY,
                    scope TEXT NOT NULL,
                    team_id TEXT,
                    case_id TEXT,
                    visibility TEXT NOT NULL,
                    memory_target TEXT NOT NULL,
                    current_version INTEGER NOT NULL DEFAULT 0,
                    current_record_id INTEGER,
                    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                );

                CREATE TABLE IF NOT EXISTS memory_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
            )

            existing_cols = {
                row["name"]
                for row in self._conn.execute("PRAGMA table_info(memories)").fetchall()
            }
            migrations = {
                "content_hash": "ALTER TABLE memories ADD COLUMN content_hash TEXT DEFAULT ''",
                "expires_at": "ALTER TABLE memories ADD COLUMN expires_at TEXT",
                "scope": "ALTER TABLE memories ADD COLUMN scope TEXT DEFAULT 'session'",
                "team_id": "ALTER TABLE memories ADD COLUMN team_id TEXT",
                "case_id": "ALTER TABLE memories ADD COLUMN case_id TEXT",
                "job_id": "ALTER TABLE memories ADD COLUMN job_id TEXT",
                "producer_agent_id": "ALTER TABLE memories ADD COLUMN producer_agent_id TEXT",
                "producer_role": "ALTER TABLE memories ADD COLUMN producer_role TEXT",
                "visibility": "ALTER TABLE memories ADD COLUMN visibility TEXT DEFAULT 'private'",
            }
            for column, statement in migrations.items():
                if column not in existing_cols:
                    self._conn.execute(statement)

            if "content_hash" not in existing_cols:
                self._conn.execute(
                    "UPDATE memories "
                    "SET content_hash = lower(hex(randomblob(16))) "
                    "WHERE content_hash = ''"
                )

            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memories_hash ON memories(content_hash)"
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memories_expires_at ON memories(expires_at)"
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memories_scope ON memories(scope)"
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memories_team_case ON memories(team_id, case_id)"
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memories_scope_visibility "
                "ON memories(scope, visibility)"
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memory_targets_team_case "
                "ON memory_targets(team_id, case_id, memory_target)"
            )
            self._conn.execute(
                """
                INSERT INTO memory_metadata(key, value)
                VALUES ('schema_version', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (self.SCHEMA_VERSION,),
            )
            self._conn.commit()

    def write(
        self,
        session_id: str,
        task_type: str,
        content: str,
        salience: float,
        metadata: dict[str, Any] | None = None,
        ttl_days: int | None = 30,
        *,
        scope: str = "session",
        team_id: str | None = None,
        case_id: str | None = None,
        job_id: str | None = None,
        producer_agent_id: str | None = None,
        producer_role: str | None = None,
        visibility: str = "private",
        memory_target: str | None = None,
        expected_state_version: int | None = None,
    ) -> int | None:
        status = self.write_with_status(
            session_id=session_id,
            task_type=task_type,
            content=content,
            salience=salience,
            metadata=metadata,
            ttl_days=ttl_days,
            scope=scope,
            team_id=team_id,
            case_id=case_id,
            job_id=job_id,
            producer_agent_id=producer_agent_id,
            producer_role=producer_role,
            visibility=visibility,
            memory_target=memory_target,
            expected_state_version=expected_state_version,
        )
        return status.record_id

    def write_with_status(
        self,
        session_id: str,
        task_type: str,
        content: str,
        salience: float,
        metadata: dict[str, Any] | None = None,
        ttl_days: int | None = 30,
        *,
        scope: str = "session",
        team_id: str | None = None,
        case_id: str | None = None,
        job_id: str | None = None,
        producer_agent_id: str | None = None,
        producer_role: str | None = None,
        visibility: str = "private",
        memory_target: str | None = None,
        expected_state_version: int | None = None,
    ) -> MemoryWriteStatus:
        with self._lock:
            content_hash = hashlib.sha256(content.strip().encode("utf-8")).hexdigest()
            now = _utc_now_iso()
            expires_at = _expires_at_iso(ttl_days)
            meta_json = json.dumps(metadata or {}, ensure_ascii=False)
            normalized_target = memory_target.strip() if memory_target else None
            target_key = (
                _target_key(
                    scope=scope,
                    team_id=team_id,
                    case_id=case_id,
                    visibility=visibility,
                    memory_target=normalized_target,
                )
                if normalized_target
                else None
            )
            current_target_version = None

            if target_key is not None:
                row = self._conn.execute(
                    "SELECT current_version FROM memory_targets WHERE target_key = ?",
                    (target_key,),
                ).fetchone()
                current_target_version = int(row["current_version"]) if row is not None else 0
                if expected_state_version is None:
                    return MemoryWriteStatus(
                        record_id=None,
                        dedup_hit=False,
                        conflict_detected=True,
                        expected_state_version=None,
                        committed_state_version=current_target_version,
                        memory_target=normalized_target,
                    )
                if current_target_version != expected_state_version:
                    return MemoryWriteStatus(
                        record_id=None,
                        dedup_hit=False,
                        conflict_detected=True,
                        expected_state_version=expected_state_version,
                        committed_state_version=current_target_version,
                        memory_target=normalized_target,
                    )

            existing = self._conn.execute(
                """
                SELECT id FROM memories
                WHERE content_hash = ?
                  AND scope = ?
                  AND COALESCE(team_id, '') = COALESCE(?, '')
                  AND COALESCE(case_id, '') = COALESCE(?, '')
                  AND COALESCE(job_id, '') = COALESCE(?, '')
                  AND visibility = ?
                  AND (expires_at IS NULL OR expires_at > ?)
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (content_hash, scope, team_id, case_id, job_id, visibility, now),
            ).fetchone()

            if existing is not None:
                record_id = int(existing["id"])
                self._conn.execute(
                    """
                    UPDATE memories
                    SET session_id = ?,
                        task_type = ?,
                        scope = ?,
                        team_id = ?,
                        case_id = ?,
                        job_id = ?,
                        producer_agent_id = ?,
                        producer_role = ?,
                        visibility = ?,
                        content = ?,
                        salience = CASE WHEN salience > ? THEN salience ELSE ? END,
                        metadata_json = ?,
                        created_at = ?,
                        expires_at = ?,
                        content_hash = ?
                    WHERE id = ?
                    """,
                    (
                        session_id,
                        task_type,
                        scope,
                        team_id,
                        case_id,
                        job_id,
                        producer_agent_id,
                        producer_role,
                        visibility,
                        content,
                        salience,
                        salience,
                        meta_json,
                        now,
                        expires_at,
                        content_hash,
                        record_id,
                    ),
                )
                committed_state_version = self._commit_target_head(
                    target_key=target_key,
                    scope=scope,
                    team_id=team_id,
                    case_id=case_id,
                    visibility=visibility,
                    memory_target=normalized_target,
                    expected_state_version=expected_state_version,
                    record_id=record_id,
                    updated_at=now,
                )
                self._conn.commit()
                return MemoryWriteStatus(
                    record_id=record_id,
                    dedup_hit=True,
                    conflict_detected=False,
                    expected_state_version=expected_state_version,
                    committed_state_version=committed_state_version,
                    memory_target=normalized_target,
                )

            cursor = self._conn.execute(
                """
                INSERT INTO memories (
                    session_id,
                    task_type,
                    scope,
                    team_id,
                    case_id,
                    job_id,
                    producer_agent_id,
                    producer_role,
                    visibility,
                    content,
                    content_hash,
                    salience,
                    metadata_json,
                    created_at,
                    expires_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    task_type,
                    scope,
                    team_id,
                    case_id,
                    job_id,
                    producer_agent_id,
                    producer_role,
                    visibility,
                    content,
                    content_hash,
                    salience,
                    meta_json,
                    now,
                    expires_at,
                ),
            )
            record_id = int(cursor.lastrowid)
            committed_state_version = self._commit_target_head(
                target_key=target_key,
                scope=scope,
                team_id=team_id,
                case_id=case_id,
                visibility=visibility,
                memory_target=normalized_target,
                expected_state_version=expected_state_version,
                record_id=record_id,
                updated_at=now,
            )
            self._conn.commit()
            return MemoryWriteStatus(
                record_id=record_id,
                dedup_hit=False,
                conflict_detected=False,
                expected_state_version=expected_state_version,
                committed_state_version=committed_state_version,
                memory_target=normalized_target,
            )

    def recent(self, limit: int = 10, include_expired: bool = False) -> list[MemoryRecord]:
        with self._lock:
            if include_expired:
                query = """
                    SELECT id, session_id, task_type, scope, team_id, case_id, job_id,
                           producer_agent_id, producer_role, visibility, content, content_hash,
                           salience, metadata_json, created_at, expires_at
                    FROM memories
                    ORDER BY created_at DESC
                    LIMIT ?
                """
                params: tuple[object, ...] = (limit,)
            else:
                query = """
                    SELECT id, session_id, task_type, scope, team_id, case_id, job_id,
                           producer_agent_id, producer_role, visibility, content, content_hash,
                           salience, metadata_json, created_at, expires_at
                    FROM memories
                    WHERE (expires_at IS NULL OR expires_at > ?)
                    ORDER BY created_at DESC
                    LIMIT ?
                """
                params = (self._now_iso(), limit)
            rows = self._conn.execute(query, params).fetchall()
            return [self._row_to_record(row) for row in rows]

    def search(
        self,
        keyword: str,
        limit: int = 10,
        include_expired: bool = False,
        *,
        scope: str | None = None,
        team_id: str | None = None,
        case_id: str | None = None,
        job_id: str | None = None,
        visibility: str | None = None,
    ) -> list[MemoryRecord]:
        with self._lock:
            clauses = ["content LIKE ?"]
            params: list[object] = [f"%{keyword}%"]

            if not include_expired:
                clauses.append("(expires_at IS NULL OR expires_at > ?)")
                params.append(self._now_iso())

            if scope is not None:
                clauses.append("scope = ?")
                params.append(scope)
            if team_id is not None:
                clauses.append("COALESCE(team_id, '') = COALESCE(?, '')")
                params.append(team_id)
            if case_id is not None:
                clauses.append("COALESCE(case_id, '') = COALESCE(?, '')")
                params.append(case_id)
            if job_id is not None:
                clauses.append("COALESCE(job_id, '') = COALESCE(?, '')")
                params.append(job_id)
            if visibility is not None:
                clauses.append("visibility = ?")
                params.append(visibility)

            where_sql = " AND ".join(clauses)
            query = (
                "SELECT id, session_id, task_type, scope, team_id, case_id, job_id, "
                "producer_agent_id, producer_role, visibility, content, content_hash, salience, "
                "metadata_json, created_at, expires_at "
                "FROM memories "
                f"WHERE {where_sql} "
                "ORDER BY salience DESC, created_at DESC "
                "LIMIT ?"
            )
            params.append(limit)
            rows = self._conn.execute(query, tuple(params)).fetchall()
            return [self._row_to_record(row) for row in rows]

    def prune_to_limit(self, max_rows: int) -> int:
        with self._lock:
            if max_rows <= 0:
                return 0

            now = self._now_iso()
            expired_deleted = self._conn.execute(
                "DELETE FROM memories WHERE expires_at IS NOT NULL AND expires_at <= ?",
                (now,),
            ).rowcount

            total = self.count(include_expired=False)
            if total <= max_rows:
                self._conn.commit()
                return int(expired_deleted)

            to_delete = total - max_rows
            self._conn.execute(
                """
                DELETE FROM memories
                WHERE id IN (
                    SELECT id FROM memories
                    WHERE (expires_at IS NULL OR expires_at > ?)
                    ORDER BY created_at ASC
                    LIMIT ?
                )
                """,
                (now, to_delete),
            )
            self._conn.commit()
            return int(expired_deleted + to_delete)

    def count(self, include_expired: bool = False) -> int:
        with self._lock:
            if include_expired:
                row = self._conn.execute("SELECT COUNT(*) AS c FROM memories").fetchone()
            else:
                row = self._conn.execute(
                    "SELECT COUNT(*) AS c FROM memories "
                    "WHERE (expires_at IS NULL OR expires_at > ?)",
                    (self._now_iso(),),
                ).fetchone()
            return int(row["c"]) if row is not None else 0

    def get_target_version(
        self,
        *,
        scope: str,
        team_id: str | None,
        case_id: str | None,
        visibility: str,
        memory_target: str,
    ) -> int:
        target_key = _target_key(
            scope=scope,
            team_id=team_id,
            case_id=case_id,
            visibility=visibility,
            memory_target=memory_target,
        )
        with self._lock:
            row = self._conn.execute(
                "SELECT current_version FROM memory_targets WHERE target_key = ?",
                (target_key,),
            ).fetchone()
        if row is None:
            return 0
        return int(row["current_version"])

    def schema_version(self) -> str:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM memory_metadata WHERE key = 'schema_version'"
            ).fetchone()
        if row is None:
            return self.SCHEMA_VERSION
        return str(row["value"])

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _commit_target_head(
        self,
        *,
        target_key: str | None,
        scope: str,
        team_id: str | None,
        case_id: str | None,
        visibility: str,
        memory_target: str | None,
        expected_state_version: int | None,
        record_id: int,
        updated_at: str,
    ) -> int | None:
        if target_key is None or memory_target is None:
            return None
        committed_state_version = int(expected_state_version or 0) + 1
        self._conn.execute(
            """
            INSERT INTO memory_targets (
                target_key, scope, team_id, case_id, visibility, memory_target,
                current_version, current_record_id, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(target_key) DO UPDATE SET
                current_version = excluded.current_version,
                current_record_id = excluded.current_record_id,
                updated_at = excluded.updated_at
            """,
            (
                target_key,
                scope,
                team_id,
                case_id,
                visibility,
                memory_target,
                committed_state_version,
                record_id,
                updated_at,
            ),
        )
        return committed_state_version

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> MemoryRecord:
        return MemoryRecord(
            id=int(row["id"]),
            session_id=str(row["session_id"]),
            task_type=str(row["task_type"]),
            scope=str(row["scope"]),
            team_id=str(row["team_id"]) if row["team_id"] is not None else None,
            case_id=str(row["case_id"]) if row["case_id"] is not None else None,
            job_id=str(row["job_id"]) if row["job_id"] is not None else None,
            producer_agent_id=(
                str(row["producer_agent_id"]) if row["producer_agent_id"] is not None else None
            ),
            producer_role=str(row["producer_role"]) if row["producer_role"] is not None else None,
            visibility=str(row["visibility"]),
            content=str(row["content"]),
            content_hash=str(row["content_hash"]),
            salience=float(row["salience"]),
            created_at=str(row["created_at"]),
            expires_at=str(row["expires_at"]) if row["expires_at"] is not None else None,
            metadata=json.loads(str(row["metadata_json"] or "{}")),
        )

    @staticmethod
    def _now_iso() -> str:
        return _utc_now_iso()


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _expires_at_iso(ttl_days: int | None) -> str | None:
    if ttl_days is None or ttl_days <= 0:
        return None
    expires = datetime.now(UTC) + timedelta(days=ttl_days)
    return expires.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _target_key(
    *,
    scope: str,
    team_id: str | None,
    case_id: str | None,
    visibility: str,
    memory_target: str | None,
) -> str:
    raw = json.dumps(
        {
            "scope": scope,
            "team_id": team_id or "",
            "case_id": case_id or "",
            "visibility": visibility,
            "memory_target": memory_target or "",
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
