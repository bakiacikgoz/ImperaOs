from imperaos.memory.models import sha256_text, utc_now
from imperaos.memory.semantic.embedding_provider import DeterministicFixtureEmbeddingProvider
from imperaos.memory.semantic.hybrid_retriever import score_record
from imperaos.memory.semantic.models import EmbeddingRequest, MemoryIndexRecord


def test_hybrid_retriever_scores_matching_record_higher() -> None:
    provider = DeterministicFixtureEmbeddingProvider()
    query = "provider governance target evidence"
    embedding = provider.embed(
        EmbeddingRequest(text=query, textHash=sha256_text(query), workspaceId="default")
    )
    assert embedding.vector is not None
    record = MemoryIndexRecord(
        memoryId="mem_a",
        workspaceId="default",
        scopeType="personal",
        scopeId="agent-local",
        contentHash=sha256_text("content"),
        redactedSummary="provider governance target evidence",
        summaryHash=sha256_text("provider governance target evidence"),
        embeddingHash=sha256_text("embedding"),
        embedding=embedding.vector,
        stateVersion=1,
        createdAtUtc=utc_now(),
        updatedAtUtc=utc_now(),
    )

    score = score_record(query=query, query_vector=embedding.vector, record=record)

    assert score.final > 0.8
    assert score.lexical == 1.0
