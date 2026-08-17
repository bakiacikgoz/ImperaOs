from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field

from imperaos.memory.authority import build_memory_authority
from imperaos.memory.models import MemoryRecordV3, StrictModel, sha256_text
from imperaos.memory.sync_conflicts import MemorySyncConflict, target_version_conflict
from imperaos.memory.sync_pack import load_memory_sync_pack, verify_memory_sync_pack
from imperaos.runtime.config import RuntimeConfig


class MemorySyncImportReport(StrictModel):
    version: Literal["memory.sync-import-report/v1"] = "memory.sync-import-report/v1"
    status: Literal["pass", "blocked", "applied"]
    pack_id: str | None = Field(default=None, alias="packId")
    dry_run: bool = Field(alias="dryRun")
    records_seen: int = Field(default=0, alias="recordsSeen")
    records_applied: int = Field(default=0, alias="recordsApplied")
    conflicts: list[MemorySyncConflict] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")
    approval_id: str | None = Field(default=None, alias="approvalId")
    raw_content_included: Literal[False] = Field(default=False, alias="rawContentIncluded")


def import_memory_sync_pack(
    *,
    config: RuntimeConfig,
    input_path: str | Path,
    dry_run: bool = True,
    approval_id: str | None = None,
) -> MemorySyncImportReport:
    verify = verify_memory_sync_pack(input_path)
    if verify.status != "pass":
        return MemorySyncImportReport(
            status="blocked",
            packId=verify.pack_id,
            dryRun=dry_run,
            blockingReasons=verify.blocking_reasons,
        )
    pack = load_memory_sync_pack(input_path)
    blocking: list[str] = []
    if not config.memory.sync.enabled:
        blocking.append("MEMORY_SYNC_DISABLED")
    if not dry_run and not config.memory.sync.allow_cross_environment_import:
        blocking.append("MEMORY_SYNC_CROSS_ENVIRONMENT_IMPORT_DISABLED")
    if (
        not dry_run
        and config.memory.sync.import_apply_requires_approval
        and not approval_id
    ):
        blocking.append("MEMORY_SYNC_IMPORT_APPROVAL_REQUIRED")

    authority = build_memory_authority(config)
    conflicts = [_conflict_for_record(authority.store, record) for record in pack.records]
    conflicts = [item for item in conflicts if item is not None]
    if conflicts:
        blocking.append("MEMORY_SYNC_CONFLICTS_PRESENT")
    if dry_run or blocking:
        return MemorySyncImportReport(
            status="blocked" if blocking else "pass",
            packId=pack.manifest.pack_id,
            dryRun=dry_run,
            recordsSeen=len(pack.records),
            conflicts=conflicts,
            blockingReasons=sorted(set(blocking)),
            approvalId=approval_id,
        )

    applied = 0
    for record in pack.records:
        result = authority.store.write_record(
            record,
            idempotency_key=sha256_text(f"sync:{pack.manifest.pack_id}:{record.memory_id}"),
            expected_state_version=None,
        )
        if not result.conflict_detected:
            applied += 1
    return MemorySyncImportReport(
        status="applied",
        packId=pack.manifest.pack_id,
        dryRun=False,
        recordsSeen=len(pack.records),
        recordsApplied=applied,
        approvalId=approval_id,
    )


def _conflict_for_record(store, record: MemoryRecordV3) -> MemorySyncConflict | None:
    if not record.memory_target:
        return None
    local_version = store.target_version(
        scope=record.scope,
        owner_type=record.owner_type,
        owner_id_hash=record.owner_id_hash,
        visibility=record.visibility,
        namespace=record.namespace,
        memory_target=record.memory_target,
    )
    return target_version_conflict(record=record, local_state_version=local_version)
