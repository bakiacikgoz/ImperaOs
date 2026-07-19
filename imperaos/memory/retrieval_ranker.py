from __future__ import annotations

from datetime import UTC, datetime

from imperaos.memory.persistent_store import MemoryRecord


def rank_records(
    records: list[MemoryRecord],
    *,
    salience_weight: float = 0.7,
    recency_weight: float = 0.3,
) -> list[MemoryRecord]:
    now = datetime.now(UTC)
    total = max(salience_weight + recency_weight, 1e-9)
    salience_w = salience_weight / total
    recency_w = recency_weight / total

    def score(record: MemoryRecord) -> float:
        try:
            created = datetime.fromisoformat(record.created_at.replace("Z", "+00:00"))
        except ValueError:
            created = now
        age_h = max((now - created).total_seconds() / 3600, 0.0)
        recency = 1 / (1 + age_h / 24)
        return (record.salience * salience_w) + (recency * recency_w)

    return sorted(records, key=score, reverse=True)
