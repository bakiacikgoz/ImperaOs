from __future__ import annotations

from typing import Literal

from pydantic import Field

from imperaos.memory.models import MemoryRecordV3, StrictModel


class MemorySyncConflict(StrictModel):
    conflict_id: str = Field(alias="conflictId")
    memory_id: str = Field(alias="memoryId")
    conflict_type: Literal["target_version", "cross_environment", "policy", "duplicate"] = Field(
        alias="conflictType"
    )
    reason_code: str = Field(alias="reasonCode")
    local_state_version: int | None = Field(default=None, alias="localStateVersion")
    remote_state_version: int | None = Field(default=None, alias="remoteStateVersion")
    resolution: Literal["skip", "manual_review", "reject"] = "skip"


def target_version_conflict(
    *,
    record: MemoryRecordV3,
    local_state_version: int,
) -> MemorySyncConflict | None:
    if not record.memory_target:
        return None
    if local_state_version in {0, record.state_version - 1, record.state_version}:
        return None
    return MemorySyncConflict(
        conflictId=f"sync_conflict_{record.memory_id}",
        memoryId=record.memory_id,
        conflictType="target_version",
        reasonCode="MEMORY_SYNC_TARGET_VERSION_CONFLICT",
        localStateVersion=local_state_version,
        remoteStateVersion=record.state_version,
        resolution="manual_review",
    )
