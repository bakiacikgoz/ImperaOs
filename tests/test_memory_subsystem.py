from pathlib import Path

from imperaos.memory.manager import MemoryManager
from imperaos.memory.persistent_store import PersistentMemoryStore
from imperaos.memory.salience_gate import SalienceGate


def test_memory_store_write_and_search(tmp_path: Path) -> None:
    db_path = tmp_path / "mem.sqlite3"
    store = PersistentMemoryStore(db_path=db_path)

    row_id = store.write(
        session_id="s1",
        task_type="plan",
        content="User wants a weekly plan",
        salience=0.8,
        metadata={"tag": "plan"},
    )

    assert row_id > 0
    assert store.count() == 1

    found = store.search("weekly", limit=3)
    assert len(found) == 1
    assert "weekly" in found[0].content


def test_memory_manager_respects_disabled_mode(tmp_path: Path) -> None:
    store = PersistentMemoryStore(db_path=tmp_path / "mem2.sqlite3")
    gate = SalienceGate(threshold=0.1, decay=0.9)
    manager = MemoryManager(enabled=False, store=store, gate=gate, max_rows=100)

    result = manager.maybe_write(
        session_id="s1",
        task_type="chat",
        user_input="remember this",
        assistant_output="ok",
    )

    assert result.written is False
    assert store.count() == 0


def test_salience_gate_triggers_for_high_signal() -> None:
    gate = SalienceGate(threshold=0.2, decay=0.8)
    decision = gate.evaluate(
        task_type="plan",
        user_input="Please remember this important deadline",
        assistant_output="I will keep this deadline in memory.",
        expert_payload={"plan_steps": ["A"]},
    )

    assert decision.should_write is True
    assert decision.spike is True
