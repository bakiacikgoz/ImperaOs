from __future__ import annotations

import json
from pathlib import Path

from imperaos.memory.workspace_models import (
    LegacyMemoryMigrationPlanResult,
    MemoryAccessDecision,
    MemoryPrincipal,
    MemoryScopeAclRule,
    MemoryWorkspace,
    MemoryWorkspaceMembership,
    WorkspaceMemoryAuthorityHealth,
    WorkspaceMemoryConflict,
    WorkspaceMemoryRecord,
    WorkspaceMemorySyncImportReport,
    WorkspaceMemorySyncPack,
    WorkspaceMemoryTombstoneResult,
)

SCHEMAS = {
    "workspace.schema.json": MemoryWorkspace,
    "principal.schema.json": MemoryPrincipal,
    "membership.schema.json": MemoryWorkspaceMembership,
    "scope_acl.schema.json": MemoryScopeAclRule,
    "workspace_memory_record.schema.json": WorkspaceMemoryRecord,
    "memory_access_decision.schema.json": MemoryAccessDecision,
    "workspace_authority_health.schema.json": WorkspaceMemoryAuthorityHealth,
    "workspace_sync_pack.schema.json": WorkspaceMemorySyncPack,
    "workspace_sync_import_report.schema.json": WorkspaceMemorySyncImportReport,
    "workspace_sync_conflict.schema.json": WorkspaceMemoryConflict,
    "memory_tombstone.schema.json": WorkspaceMemoryTombstoneResult,
    "memory_migration_plan.schema.json": LegacyMemoryMigrationPlanResult,
}


def main() -> None:
    output_dir = Path("contracts/memory/workspace")
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename, model in SCHEMAS.items():
        schema = model.model_json_schema(by_alias=True)
        (output_dir / filename).write_text(
            json.dumps(schema, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
