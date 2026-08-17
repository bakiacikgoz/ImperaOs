import sqlite3
from pathlib import Path

from imperaos.memory.migration_planner import plan_legacy_memory_migration
from imperaos.memory.workspace_models import LegacyMemoryMigrationPlanRequest


def test_legacy_memory_migration_is_dry_run_and_hash_only(tmp_path: Path) -> None:
    legacy = tmp_path / "legacy.sqlite3"
    conn = sqlite3.connect(legacy)
    conn.execute(
        """
        CREATE TABLE memory_records_v3 (
            memory_id TEXT,
            scope TEXT,
            owner_id TEXT,
            content_summary TEXT,
            raw_content TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO memory_records_v3(
            memory_id, scope, owner_id, content_summary, raw_content
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (
            "mem_legacy_1",
            "personal",
            "operator-local",
            "Release owner is platform",
            "raw secret",
        ),
    )
    conn.commit()
    conn.close()
    output = tmp_path / "plan.json"

    result = plan_legacy_memory_migration(
        LegacyMemoryMigrationPlanRequest(
            legacyDbPath=str(legacy),
            workspaceId="default",
            defaultScope="personal",
            outputPath=str(output),
        )
    )

    assert result.status == "warning"
    assert result.records_planned == 1
    assert result.raw_content_included is False
    written = output.read_text(encoding="utf-8")
    assert "raw secret" not in written
    assert "Release owner is platform" not in written
    assert "MEMORY_LEGACY_RAW_CONTENT_IGNORED" in written
