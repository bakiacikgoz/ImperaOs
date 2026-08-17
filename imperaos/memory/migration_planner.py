from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from imperaos.memory.models import sha256_text
from imperaos.memory.workspace_models import (
    LegacyMemoryMigrationPlanRequest,
    LegacyMemoryMigrationPlanResult,
    LegacyMemoryRecordPlan,
)


def plan_legacy_memory_migration(
    request: LegacyMemoryMigrationPlanRequest,
) -> LegacyMemoryMigrationPlanResult:
    legacy_path = Path(request.legacy_db_path)
    if not legacy_path.exists():
        result = LegacyMemoryMigrationPlanResult(
            status="blocked",
            workspaceId=request.workspace_id,
            warnings=["MEMORY_LEGACY_DB_MISSING"],
        )
        _write_plan_if_requested(result, request.output_path)
        return result

    try:
        rows = _load_legacy_rows(legacy_path)
    except sqlite3.Error as exc:
        result = LegacyMemoryMigrationPlanResult(
            status="blocked",
            workspaceId=request.workspace_id,
            warnings=[f"MEMORY_LEGACY_DB_READ_FAILED:{type(exc).__name__}"],
        )
        _write_plan_if_requested(result, request.output_path)
        return result

    plans: list[LegacyMemoryRecordPlan] = []
    warnings: list[str] = []
    for row in rows:
        source_id = str(row.get("memory_id") or row.get("id") or row.get("rowid"))
        summary = str(row.get("content_summary") or row.get("summary") or "")
        content_hash = str(row.get("content_hash") or sha256_text(summary))
        scope_type, scope_id = _target_scope(row, request.default_scope)
        plan_warnings: list[str] = []
        if not summary:
            plan_warnings.append("MEMORY_LEGACY_SUMMARY_EMPTY")
        if row.get("raw_content") or row.get("candidate_text"):
            plan_warnings.append("MEMORY_LEGACY_RAW_CONTENT_IGNORED")
        if plan_warnings:
            warnings.extend(plan_warnings)
        plans.append(
            LegacyMemoryRecordPlan(
                sourceRecordId=source_id,
                targetScopeType=scope_type,
                targetScopeId=scope_id,
                summaryHash=sha256_text(summary),
                contentHash=content_hash,
                warnings=plan_warnings,
            )
        )

    result = LegacyMemoryMigrationPlanResult(
        status="warning" if warnings else "pass",
        workspaceId=request.workspace_id,
        recordsSeen=len(rows),
        recordsPlanned=len(plans),
        plans=plans,
        warnings=sorted(set(warnings)),
    )
    _write_plan_if_requested(result, request.output_path)
    return result


def _load_legacy_rows(path: Path) -> list[dict[str, Any]]:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        table = _first_existing_table(
            conn,
            (
                "memory_records_v3",
                "memory_records",
                "memories",
                "memory",
            ),
        )
        if table is None:
            return []
        rows = conn.execute(f"SELECT rowid, * FROM {table} ORDER BY rowid ASC").fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def _first_existing_table(conn: sqlite3.Connection, names: tuple[str, ...]) -> str | None:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    available = {str(row["name"]) for row in rows}
    for name in names:
        if name in available:
            return name
    return None


def _target_scope(row: dict[str, Any], default_scope: str) -> tuple[str, str]:
    scope = str(row.get("scope") or default_scope or "personal")
    if scope not in {"personal", "agent", "team", "project", "case", "organization"}:
        scope = "personal"
    owner = (
        row.get("owner_id")
        or row.get("owner")
        or row.get("source_agent_id")
        or row.get("sourceAgentId")
        or "legacy"
    )
    return scope, str(owner)


def _write_plan_if_requested(
    result: LegacyMemoryMigrationPlanResult,
    output_path: str | None,
) -> None:
    if output_path is None:
        return
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(result.model_dump(mode="json", by_alias=True), indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
