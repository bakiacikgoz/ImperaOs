from __future__ import annotations

from datetime import UTC, datetime

from imperaos.memory.models import MemoryRecordV3


def is_retrievable(record: MemoryRecordV3, *, now: datetime | None = None) -> bool:
    current = now or datetime.now(UTC)
    if record.status != "active":
        return False
    if record.expires_at is None:
        return True
    expires = (
        record.expires_at
        if record.expires_at.tzinfo
        else record.expires_at.replace(tzinfo=UTC)
    )
    return expires > current
