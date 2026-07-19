from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from imperaos.memory.models import sha256_text, stable_id, utc_now
from imperaos.memory.workspace_models import (
    WorkspaceMemoryConflict,
    WorkspaceMemoryRecord,
    WorkspaceMemorySyncImportReport,
    WorkspaceMemorySyncPack,
    WorkspaceMemorySyncPackManifest,
    WorkspaceMemorySyncVerifyResult,
)
from imperaos.memory.workspace_store import WorkspaceMemoryStore


class WorkspaceMemorySyncCoordinator:
    def __init__(self, *, store: WorkspaceMemoryStore):
        self.store = store

    def export_pack(
        self,
        *,
        workspace_id: str,
        source_client_id: str,
        output_path: str | Path,
        limit: int = 10000,
    ) -> WorkspaceMemorySyncPack:
        records = self.store.records_for_sync(workspace_id=workspace_id, limit=limit)
        item_hashes = {_record_hash_key(record): _record_hash(record) for record in records}
        generated_at = utc_now().isoformat()
        cursor_to = generated_at
        manifest_payload = {
            "schemaVersion": "workspace-memory-sync-pack/v2",
            "packId": stable_id("wm_pack", workspace_id, source_client_id, cursor_to),
            "workspaceId": workspace_id,
            "sourceClientId": source_client_id,
            "generatedAtUtc": generated_at,
            "cursorTo": cursor_to,
            "recordCount": len(records),
            "tombstoneCount": 0,
            "conflictCount": 0,
            "evidenceMode": "hash_only",
            "rawContentIncluded": False,
            "itemHashes": item_hashes,
        }
        manifest = WorkspaceMemorySyncPackManifest(**manifest_payload, manifestHash="0" * 64)
        normalized_manifest_payload = manifest.model_dump(mode="json", by_alias=True)
        normalized_manifest_payload.pop("manifestHash")
        manifest = manifest.model_copy(
            update={"manifest_hash": _manifest_hash(normalized_manifest_payload)}
        )
        pack = WorkspaceMemorySyncPack(manifest=manifest, records=records, tombstones=[])
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(pack.model_dump(mode="json", by_alias=True), indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        return pack

    def verify_pack(self, input_path: str | Path) -> WorkspaceMemorySyncVerifyResult:
        try:
            pack = load_workspace_sync_pack(input_path)
        except (OSError, ValidationError, json.JSONDecodeError) as exc:
            return WorkspaceMemorySyncVerifyResult(
                status="fail",
                blockingReasons=[f"MEMORY_SYNC_PACK_INVALID:{type(exc).__name__}"],
            )
        reasons = _verify_pack_integrity(pack)
        return WorkspaceMemorySyncVerifyResult(
            status="pass" if not reasons else "fail",
            packId=pack.manifest.pack_id,
            blockingReasons=reasons,
        )

    def import_pack(
        self,
        *,
        input_path: str | Path,
        dry_run: bool = True,
        approval_id: str | None = None,
    ) -> WorkspaceMemorySyncImportReport:
        try:
            pack = load_workspace_sync_pack(input_path)
        except (OSError, ValidationError, json.JSONDecodeError) as exc:
            return WorkspaceMemorySyncImportReport(
                status="blocked",
                packId=None,
                dryRun=dry_run,
                blockingReasons=[f"MEMORY_SYNC_PACK_INVALID:{type(exc).__name__}"],
            )
        integrity_reasons = _verify_pack_integrity(pack)
        if integrity_reasons:
            return WorkspaceMemorySyncImportReport(
                status="blocked",
                packId=pack.manifest.pack_id,
                dryRun=dry_run,
                recordsSeen=len(pack.records),
                blockingReasons=integrity_reasons,
            )
        conflicts = self._detect_conflicts(pack.records)
        if dry_run:
            return WorkspaceMemorySyncImportReport(
                status="pass" if not conflicts else "blocked",
                packId=pack.manifest.pack_id,
                dryRun=True,
                recordsSeen=len(pack.records),
                conflicts=conflicts,
                blockingReasons=["MEMORY_SYNC_IMPORT_CONFLICTS_PENDING"] if conflicts else [],
            )
        if approval_id is None:
            return WorkspaceMemorySyncImportReport(
                status="blocked",
                packId=pack.manifest.pack_id,
                dryRun=False,
                recordsSeen=len(pack.records),
                conflicts=conflicts,
                blockingReasons=["MEMORY_SYNC_IMPORT_APPROVAL_REQUIRED"],
            )
        if conflicts:
            return WorkspaceMemorySyncImportReport(
                status="blocked",
                packId=pack.manifest.pack_id,
                dryRun=False,
                recordsSeen=len(pack.records),
                conflicts=conflicts,
                approvalId=approval_id,
                blockingReasons=["MEMORY_SYNC_IMPORT_CONFLICTS_PENDING"],
            )

        applied = 0
        for record in pack.records:
            result = self.store.write_record(
                record,
                expected_state_version=None,
                changed_by_principal_id=record.owner_principal_id,
                change_reason=f"workspace sync import {approval_id}",
            )
            if result.status == "committed":
                applied += 1
        return WorkspaceMemorySyncImportReport(
            status="applied",
            packId=pack.manifest.pack_id,
            dryRun=False,
            recordsSeen=len(pack.records),
            recordsApplied=applied,
            approvalId=approval_id,
        )

    def _detect_conflicts(
        self,
        records: list[WorkspaceMemoryRecord],
    ) -> list[WorkspaceMemoryConflict]:
        conflicts: list[WorkspaceMemoryConflict] = []
        for record in records:
            if record.memory_target is None:
                continue
            local = self.store.find_record_by_target(
                workspace_id=record.workspace_id,
                scope_type=record.scope_type,
                scope_id=record.scope_id,
                memory_target=record.memory_target,
            )
            if local is None or local.content_hash == record.content_hash:
                continue
            conflicts.append(
                WorkspaceMemoryConflict(
                    conflictId=stable_id(
                        "wm_conflict",
                        record.workspace_id,
                        record.memory_target,
                        local.content_hash,
                        record.content_hash,
                    ),
                    workspaceId=record.workspace_id,
                    memoryId=record.memory_id,
                    memoryTarget=record.memory_target,
                    localStateVersion=local.state_version,
                    incomingStateVersion=record.state_version,
                    conflictType="same_target_different_hash",
                    requiresApproval=True,
                )
            )
        return conflicts


def load_workspace_sync_pack(path: str | Path) -> WorkspaceMemorySyncPack:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return WorkspaceMemorySyncPack.model_validate(payload)


def _verify_pack_integrity(pack: WorkspaceMemorySyncPack) -> list[str]:
    reasons: list[str] = []
    if pack.manifest.raw_content_included:
        reasons.append("MEMORY_SYNC_RAW_CONTENT_FORBIDDEN")
    if pack.manifest.record_count != len(pack.records):
        reasons.append("MEMORY_SYNC_RECORD_COUNT_MISMATCH")
    for record in pack.records:
        key = _record_hash_key(record)
        expected = pack.manifest.item_hashes.get(key)
        if expected != _record_hash(record):
            reasons.append(f"MEMORY_SYNC_ITEM_HASH_MISMATCH:{key}")
    manifest_payload = pack.manifest.model_dump(mode="json", by_alias=True)
    expected_manifest_hash = manifest_payload.pop("manifestHash")
    if _manifest_hash(manifest_payload) != expected_manifest_hash:
        reasons.append("MEMORY_SYNC_MANIFEST_HASH_MISMATCH")
    return reasons


def _record_hash_key(record: WorkspaceMemoryRecord) -> str:
    return f"{record.memory_id}:{record.state_version}"


def _record_hash(record: WorkspaceMemoryRecord) -> str:
    payload = record.model_dump(mode="json", by_alias=True)
    return sha256_text(json.dumps(payload, sort_keys=True))


def _manifest_hash(payload: dict[str, Any]) -> str:
    hash_payload = dict(payload)
    hash_payload.pop("manifestHash", None)
    return sha256_text(json.dumps(hash_payload, sort_keys=True))
