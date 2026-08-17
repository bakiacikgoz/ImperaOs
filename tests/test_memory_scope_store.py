from __future__ import annotations

from pathlib import Path

from imperaos.memory.persistent_store import PersistentMemoryStore


def test_scoped_memory_write_and_search(tmp_path: Path) -> None:
    store = PersistentMemoryStore(db_path=tmp_path / "mem.sqlite3")

    record_id = store.write(
        session_id="s1",
        task_type="plan",
        content="Case scoped memory sample",
        salience=0.9,
        metadata={"tag": "team"},
        scope="case",
        team_id="team-1",
        case_id="case-1",
        job_id="job-1",
        producer_agent_id="agent-1",
        producer_role="Reviewer/QA Agent",
        visibility="team",
    )

    assert record_id > 0

    found = store.search(
        "scoped",
        scope="case",
        team_id="team-1",
        case_id="case-1",
    )
    assert len(found) == 1
    assert found[0].scope == "case"
    assert found[0].team_id == "team-1"
    assert found[0].case_id == "case-1"

    not_found = store.search("scoped", scope="session")
    assert len(not_found) == 0
