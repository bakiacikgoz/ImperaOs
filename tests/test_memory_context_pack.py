from imperaos.memory.context_pack import context_pack_from_retrieval
from imperaos.memory.models import (
    MemoryHit,
    MemoryPolicyDecision,
    MemoryRetrievalResult,
    sha256_text,
    utc_now,
)


def test_context_pack_is_bounded_and_never_raw() -> None:
    summary = "minimalist black and white UI preference"
    result = MemoryRetrievalResult(
        status="pass",
        queryHash=sha256_text("ui preference"),
        hits=[
            MemoryHit(
                memoryId="mem_ctx_hit",
                scope="personal",
                visibility="private",
                ownerIdHash="0" * 64,
                contentSummary=summary,
                contentHash=sha256_text(summary),
                score=0.9,
                createdAt=utc_now(),
            )
        ],
        policyDecision=MemoryPolicyDecision(
            decision="allow",
            reasonCode="MEMORY_RETRIEVAL_ALLOWED",
        ),
        retrievalFingerprint="abc",
        indexBackend="sqlite_text",
        rawContentIncluded=False,
    )

    pack = context_pack_from_retrieval(run_id="run-1", result=result, max_context_chars=12)

    assert pack.raw_content_included is False
    assert pack.truncated is True
    assert pack.hits[0].redacted_summary.endswith("...")
