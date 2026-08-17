from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from imperaos.memory.authority import build_memory_authority
from imperaos.memory.models import (
    MemoryRecordV3,
    MemoryScopeFilter,
    MemoryVisibility,
    StrictModel,
    hash_identity,
    sha256_text,
    stable_id,
    utc_now,
)
from imperaos.runtime.config import RuntimeConfig


class MemorySyncPackManifest(StrictModel):
    version: Literal["memory.sync-pack/v1"] = "memory.sync-pack/v1"
    pack_id: str = Field(alias="packId")
    source_environment: str = Field(alias="sourceEnvironment")
    created_at_utc: Any = Field(alias="createdAtUtc")
    record_count: int = Field(alias="recordCount", ge=0)
    records_hash: str = Field(alias="recordsHash")
    raw_content_included: Literal[False] = Field(default=False, alias="rawContentIncluded")
    scope_filter_count: int = Field(default=0, alias="scopeFilterCount")

    @model_validator(mode="after")
    def _no_raw_content(self) -> MemorySyncPackManifest:
        if self.raw_content_included is not False:
            raise ValueError("memory sync pack v1 cannot include raw content")
        return self


class MemorySyncPack(StrictModel):
    manifest: MemorySyncPackManifest
    records: list[MemoryRecordV3] = Field(default_factory=list)


class MemorySyncVerifyResult(StrictModel):
    status: Literal["pass", "fail"]
    pack_id: str | None = Field(default=None, alias="packId")
    record_count: int = Field(default=0, alias="recordCount")
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")
    raw_content_included: Literal[False] = Field(default=False, alias="rawContentIncluded")


def export_memory_sync_pack(
    *,
    config: RuntimeConfig,
    output_path: str | Path,
    source_environment: str,
    scope_filters: list[MemoryScopeFilter] | None = None,
    visibility_filters: list[MemoryVisibility] | None = None,
    limit: int = 500,
) -> MemorySyncPack:
    if config.memory.sync.export_raw_content:
        raise ValueError("memory sync pack v1 does not support raw content export")
    authority = build_memory_authority(config)
    records = authority.store.list_records(
        scope_filters=scope_filters,
        visibility_filters=visibility_filters,
        include_expired=False,
        limit=limit,
    )
    records_payload = [record.model_dump(mode="json", by_alias=True) for record in records]
    records_hash = sha256_text(json.dumps(records_payload, sort_keys=True))
    manifest = MemorySyncPackManifest(
        packId=stable_id("mem_sync", source_environment, records_hash),
        sourceEnvironment=source_environment,
        createdAtUtc=utc_now(),
        recordCount=len(records),
        recordsHash=records_hash,
        rawContentIncluded=False,
        scopeFilterCount=len(scope_filters or []),
    )
    pack = MemorySyncPack(manifest=manifest, records=records)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(pack.model_dump(mode="json", by_alias=True), indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    return pack


def load_memory_sync_pack(path: str | Path) -> MemorySyncPack:
    return MemorySyncPack.model_validate_json(Path(path).read_text(encoding="utf-8"))


def verify_memory_sync_pack(path: str | Path) -> MemorySyncVerifyResult:
    try:
        pack = load_memory_sync_pack(path)
    except Exception as exc:  # noqa: BLE001
        return MemorySyncVerifyResult(
            status="fail",
            blockingReasons=[f"MEMORY_SYNC_PACK_INVALID:{type(exc).__name__}"],
        )
    records_payload = [
        record.model_dump(mode="json", by_alias=True) for record in pack.records
    ]
    actual_hash = sha256_text(json.dumps(records_payload, sort_keys=True))
    blocking: list[str] = []
    if actual_hash != pack.manifest.records_hash:
        blocking.append("MEMORY_SYNC_RECORDS_HASH_MISMATCH")
    if pack.manifest.record_count != len(pack.records):
        blocking.append("MEMORY_SYNC_RECORD_COUNT_MISMATCH")
    return MemorySyncVerifyResult(
        status="fail" if blocking else "pass",
        packId=pack.manifest.pack_id,
        recordCount=len(pack.records),
        blockingReasons=blocking,
        rawContentIncluded=False,
    )


def owner_filter(
    scope: str,
    owner_type: str,
    owner: str,
    namespace: str = "default",
) -> MemoryScopeFilter:
    return MemoryScopeFilter(
        scope=scope,
        ownerType=owner_type,
        ownerIdHash=hash_identity(owner),
        namespace=namespace,
    )
