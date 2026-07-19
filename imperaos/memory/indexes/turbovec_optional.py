from __future__ import annotations

import importlib.util
import math
from collections.abc import Iterable
from pathlib import Path

from imperaos.memory.models import (
    MemoryHit,
    MemoryIndexDeleteResult,
    MemoryIndexRebuildResult,
    MemoryIndexRecord,
    MemoryIndexStatus,
    MemoryIndexWriteResult,
    MemoryScopeFilter,
    MemoryVisibility,
)
from imperaos.runtime.paths import MEMORY_TURBOVEC_ROOT


class TurboVecOptionalIndex:
    backend_name = "turbovec_experimental"

    def __init__(
        self,
        *,
        enabled: bool = False,
        dim: int = 16,
        bits_per_coord: int = 4,
        index_path: str | Path = MEMORY_TURBOVEC_ROOT,
        dim_guard_max: int = 4096,
    ) -> None:
        self.enabled = enabled
        self.dim = dim
        self.bits_per_coord = bits_per_coord
        self.index_path = Path(index_path)
        self.dim_guard_max = dim_guard_max

    def status(self) -> MemoryIndexStatus:
        if not self.enabled:
            return MemoryIndexStatus(
                backend=self.backend_name,
                status="disabled",
                degradedReason="experimental_backend_disabled",
                experimental=True,
            )
        if self.dim <= 0 or self.dim > self.dim_guard_max:
            return MemoryIndexStatus(
                backend=self.backend_name,
                status="unavailable",
                degradedReason="dimension_guard_rejected",
                blockingReasons=["MEMORY_INDEX_UNAVAILABLE"],
                experimental=True,
            )
        if importlib.util.find_spec("turbovec") is None:
            return MemoryIndexStatus(
                backend=self.backend_name,
                status="unavailable",
                degradedReason="python_binding_not_installed",
                experimental=True,
            )
        return MemoryIndexStatus(
            backend=self.backend_name,
            status="pass",
            experimental=True,
        )

    def add(self, records: list[MemoryIndexRecord]) -> MemoryIndexWriteResult:
        status = self.status()
        if status.status != "pass":
            return MemoryIndexWriteResult(
                status="disabled" if status.status == "disabled" else "degraded",
                indexedCount=0,
                blockingReasons=status.blocking_reasons,
            )
        for record in records:
            if record.vector is not None:
                _validate_vector(record.vector, self.dim)
        return MemoryIndexWriteResult(status="pass", indexedCount=len(records))

    def search(
        self,
        *,
        query: str,
        scope_filters: list[MemoryScopeFilter],
        visibility_filters: list[MemoryVisibility],
        limit: int,
    ) -> list[MemoryHit]:
        _ = query, scope_filters, visibility_filters, limit
        return []

    def delete(self, memory_ids: list[str]) -> MemoryIndexDeleteResult:
        return MemoryIndexDeleteResult(status="pass", deletedCount=len(memory_ids))

    def rebuild(self, records: Iterable[MemoryIndexRecord]) -> MemoryIndexRebuildResult:
        added = self.add(list(records))
        return MemoryIndexRebuildResult(
            status=added.status,
            indexedCount=added.indexed_count,
            blockingReasons=added.blocking_reasons,
        )


def _validate_vector(vector: list[float], dim: int) -> None:
    if len(vector) != dim:
        raise ValueError("MEMORY_INDEX_DIMENSION_MISMATCH")
    if not all(math.isfinite(value) for value in vector):
        raise ValueError("MEMORY_INDEX_NONFINITE_VECTOR")
