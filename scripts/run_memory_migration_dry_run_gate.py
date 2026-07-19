from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

from imperaos.memory.migration_planner import plan_legacy_memory_migration
from imperaos.memory.workspace_models import LegacyMemoryMigrationPlanRequest


def main() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        legacy = root / "legacy.sqlite3"
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
                "mem_legacy_gate",
                "personal",
                "operator-local",
                "Gate summary",
                "raw should not leak",
            ),
        )
        conn.commit()
        conn.close()
        output = root / "migration_plan.json"
        result = plan_legacy_memory_migration(
            LegacyMemoryMigrationPlanRequest(
                legacyDbPath=str(legacy),
                workspaceId="default",
                defaultScope="personal",
                outputPath=str(output),
            )
        )
        written = output.read_text(encoding="utf-8")
        status = (
            "pass"
            if result.records_planned == 1
            and result.raw_content_included is False
            and "raw should not leak" not in written
            and "Gate summary" not in written
            else "fail"
        )
        payload = result.model_dump(mode="json", by_alias=True)
        payload["status"] = status
        print(json.dumps(payload, indent=2, sort_keys=True))
        if status != "pass":
            raise SystemExit(1)


if __name__ == "__main__":
    main()
