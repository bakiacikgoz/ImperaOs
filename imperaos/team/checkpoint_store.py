from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Any


@dataclass(slots=True)
class CheckpointRecord:
    job_id: str
    case_id: str
    team_id: str
    status: str
    updated_at: str
    payload: dict[str, Any]


class TeamCheckpointStore:
    SCHEMA_VERSION = "1.0"

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = RLock()
        self._configure_connection()
        self._init_db()

    def _configure_connection(self) -> None:
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.execute("PRAGMA busy_timeout=5000")

    def _init_db(self) -> None:
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS team_checkpoints (
                    job_id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL,
                    team_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS checkpoint_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                INSERT INTO checkpoint_metadata(key, value)
                VALUES ('schema_version', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (self.SCHEMA_VERSION,),
            )
            self._conn.commit()

    def upsert(
        self,
        *,
        job_id: str,
        case_id: str,
        team_id: str,
        status: str,
        payload: dict[str, Any],
    ) -> None:
        updated_at = datetime.now(UTC).isoformat()
        payload_json = json.dumps(payload, ensure_ascii=False)
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO team_checkpoints (
                    job_id,
                    case_id,
                    team_id,
                    status,
                    updated_at,
                    payload_json
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id)
                DO UPDATE SET
                    case_id = excluded.case_id,
                    team_id = excluded.team_id,
                    status = excluded.status,
                    updated_at = excluded.updated_at,
                    payload_json = excluded.payload_json
                """,
                (job_id, case_id, team_id, status, updated_at, payload_json),
            )
            self._conn.commit()

    def get(self, job_id: str) -> CheckpointRecord | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM team_checkpoints WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        if row is None:
            return None
        return CheckpointRecord(
            job_id=str(row["job_id"]),
            case_id=str(row["case_id"]),
            team_id=str(row["team_id"]),
            status=str(row["status"]),
            updated_at=str(row["updated_at"]),
            payload=json.loads(str(row["payload_json"])),
        )

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def schema_version(self) -> str:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM checkpoint_metadata WHERE key = 'schema_version'"
            ).fetchone()
        if row is None:
            return self.SCHEMA_VERSION
        return str(row["value"])
