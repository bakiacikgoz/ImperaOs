from __future__ import annotations

from threading import Thread

from imperaos.team.checkpoint_store import TeamCheckpointStore


def test_team_checkpoint_store_parallel_upserts(tmp_path) -> None:
    store = TeamCheckpointStore(tmp_path / "checkpoints.sqlite3")
    errors: list[str] = []

    def worker(worker_id: int) -> None:
        try:
            for idx in range(30):
                store.upsert(
                    job_id=f"job-{idx % 4}",
                    case_id="case-1",
                    team_id="team-1",
                    status="running" if idx % 2 == 0 else "blocked",
                    payload={"worker": worker_id, "idx": idx},
                )
        except Exception as exc:  # noqa: BLE001
            errors.append(type(exc).__name__)

    threads = [Thread(target=worker, args=(item,)) for item in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert store.get("job-0") is not None
    store.close()
