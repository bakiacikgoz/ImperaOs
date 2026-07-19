from __future__ import annotations

from pathlib import Path

from imperaos.memory.manager import MemoryManager
from imperaos.memory.persistent_store import PersistentMemoryStore
from imperaos.memory.salience_gate import SalienceGate


def test_memory_manager_reports_tuning_metrics(tmp_path: Path) -> None:
    store = PersistentMemoryStore(db_path=tmp_path / "memory.sqlite3")
    gate = SalienceGate(
        threshold=0.1,
        decay=0.9,
        task_bonus=0.08,
        expert_bonus=0.06,
        spike_reduction=0.5,
    )
    manager = MemoryManager(
        enabled=True,
        store=store,
        gate=gate,
        max_rows=100,
        ttl_days=30,
        rank_salience_weight=0.7,
        rank_recency_weight=0.3,
    )

    manager.maybe_write(
        session_id="s1",
        task_type="plan",
        user_input="remember the deployment deadline",
        assistant_output="I will remember the deployment deadline",
        expert_payload={"plan_steps": ["deploy"]},
    )
    manager.maybe_write(
        session_id="s1",
        task_type="plan",
        user_input="remember the deployment deadline",
        assistant_output="I will remember the deployment deadline",
        expert_payload={"plan_steps": ["deploy"]},
    )

    snippets = manager.context_snippets("deployment deadline", limit=3)
    assert snippets

    stats = manager.stats()
    assert stats["memory_write_rate"] > 0
    assert stats["dedup_hit_rate"] > 0
    assert stats["retrieval_hit_rate"] > 0
    assert stats["retrieval_usefulness_rate"] > 0
    assert stats["stale_retrieval_ratio"] >= 0
