from __future__ import annotations

import sqlite3
from pathlib import Path

from imperaos.memory.persistent_store import PersistentMemoryStore


def test_legacy_memory_schema_migrates_without_scope_index_failure(tmp_path: Path) -> None:
    db = tmp_path / "legacy.sqlite3"
    conn = sqlite3.connect(db)
    conn.execute(
        """
        CREATE TABLE memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            task_type TEXT NOT NULL,
            content TEXT NOT NULL,
            salience REAL NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            expires_at TEXT
        )
        """
    )
    conn.commit()
    conn.close()

    store = PersistentMemoryStore(db_path=db)
    try:
        row_id = store.write(
            session_id="s1",
            task_type="chat",
            content="legacy migration check",
            salience=0.7,
            scope="case",
            team_id="team-1",
            case_id="case-1",
            job_id="job-1",
            producer_agent_id="agent-1",
            producer_role="Intake Agent",
            visibility="team",
        )
    finally:
        store.close()

    assert row_id > 0
