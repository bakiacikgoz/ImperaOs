from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from imperaos.memory.manager import MemoryManager
from imperaos.memory.persistent_store import PersistentMemoryStore
from imperaos.memory.salience_gate import SalienceGate


def test_memory_store_dedup_by_content_hash(tmp_path: Path) -> None:
    store = PersistentMemoryStore(db_path=tmp_path / "mem.sqlite3")

    first = store.write(
        session_id="s1",
        task_type="plan",
        content="same-content",
        salience=0.7,
        ttl_days=7,
    )
    second = store.write(
        session_id="s2",
        task_type="plan",
        content="same-content",
        salience=0.8,
        ttl_days=7,
    )

    assert first == second
    assert store.count() == 1


def test_memory_manager_skips_expired_records_in_context(tmp_path: Path) -> None:
    db_path = tmp_path / "mem2.sqlite3"
    store = PersistentMemoryStore(db_path=db_path)
    gate = SalienceGate(threshold=0.1, decay=0.9)
    manager = MemoryManager(enabled=True, store=store, gate=gate, max_rows=100, ttl_days=1)

    manager.maybe_write(
        session_id="s1",
        task_type="plan",
        user_input="remember important deadline",
        assistant_output="stored",
        expert_payload={"x": 1},
    )

    past = (datetime.now(UTC) - timedelta(days=1)).isoformat().replace("+00:00", "Z")
    store._conn.execute("UPDATE memories SET expires_at = ?", (past,))
    store._conn.commit()

    snippets = manager.context_snippets("deadline", limit=3)
    assert snippets == []
