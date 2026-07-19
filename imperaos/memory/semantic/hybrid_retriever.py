from __future__ import annotations

from datetime import UTC, datetime

from imperaos.memory.semantic.embedding_provider import cosine_similarity
from imperaos.memory.semantic.models import HybridRetrievalScore, MemoryIndexRecord


def lexical_score(query: str, text: str) -> float:
    query_terms = {term for term in query.lower().split() if len(term) > 1}
    text_terms = {term for term in text.lower().split() if len(term) > 1}
    if not query_terms:
        return 0.0
    return len(query_terms & text_terms) / len(query_terms)


def recency_score(updated_at: datetime, *, now: datetime | None = None) -> float:
    current = now or datetime.now(UTC)
    updated = updated_at if updated_at.tzinfo else updated_at.replace(tzinfo=UTC)
    age_days = max(0.0, (current - updated).total_seconds() / 86400.0)
    return max(0.0, min(1.0, 1.0 / (1.0 + age_days / 30.0)))


def score_record(
    *,
    query: str,
    query_vector: tuple[float, ...],
    record: MemoryIndexRecord,
    semantic_weight: float = 0.55,
    lexical_weight: float = 0.35,
    recency_weight: float = 0.10,
) -> HybridRetrievalScore:
    semantic = cosine_similarity(query_vector, record.embedding)
    lexical = lexical_score(query, record.redacted_summary)
    recent = recency_score(record.updated_at_utc)
    final = min(
        1.0,
        semantic * semantic_weight + lexical * lexical_weight + recent * recency_weight,
    )
    return HybridRetrievalScore(
        semantic=round(semantic, 6),
        lexical=round(lexical, 6),
        recency=round(recent, 6),
        final=round(final, 6),
    )
