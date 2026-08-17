from __future__ import annotations

from pathlib import Path

from imperaos.memory.authority import build_memory_authority
from imperaos.memory.models import MemoryAuthoritySnapshot, MemoryIndexStatus
from imperaos.runtime.config import RuntimeConfig


def build_memory_governance_snapshot(
    *,
    config: RuntimeConfig,
    evidence_root: str | Path = "artifacts",
) -> MemoryAuthoritySnapshot:
    if not getattr(config.memory, "v3_enabled", False):
        return MemoryAuthoritySnapshot(
            enabled=False,
            authorityStatus="disabled",
            index=MemoryIndexStatus(
                backend=getattr(config.memory, "semantic_index_backend", "sqlite_text"),
                status="disabled",
                degradedReason="memory_v3_disabled",
            ),
            warnings=["MEMORY_V3_DISABLED"],
        )
    authority = build_memory_authority(
        config,
        evidence_root=Path(evidence_root) / "memory-governance",
    )
    return authority.snapshot()
