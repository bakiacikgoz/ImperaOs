from __future__ import annotations

from threading import Thread

from imperaos.memory.persistent_store import PersistentMemoryStore


def test_persistent_memory_store_parallel_writes(tmp_path) -> None:
    store = PersistentMemoryStore(db_path=tmp_path / "memory.sqlite3")
    errors: list[str] = []

    def worker(worker_id: int) -> None:
        try:
            for idx in range(40):
                _ = store.write_with_status(
                    session_id=f"session-{worker_id % 3}",
                    task_type="chat",
                    content=f"shared note {idx % 10}",
                    salience=0.7,
                    metadata={"worker": worker_id, "idx": idx},
                    scope="case",
                    team_id="team-a",
                    case_id="case-a",
                    job_id=f"job-{idx % 4}",
                    producer_agent_id=f"agent-{worker_id}",
                    producer_role="Intake Agent",
                    visibility="team",
                )
        except Exception as exc:  # noqa: BLE001
            errors.append(type(exc).__name__)

    threads = [Thread(target=worker, args=(item,)) for item in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert store.count() >= 1
    assert store.recent(limit=5)
    store.close()
