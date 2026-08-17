from imperaos.memory.models import sha256_text
from imperaos.memory.semantic.embedding_provider import DeterministicFixtureEmbeddingProvider
from imperaos.memory.semantic.models import EmbeddingRequest


def test_embedding_provider_is_deterministic_and_hash_only() -> None:
    provider = DeterministicFixtureEmbeddingProvider()
    text = "provider governance target evidence"

    first = provider.embed(
        EmbeddingRequest(text=text, textHash=sha256_text(text), workspaceId="default")
    )
    second = provider.embed(
        EmbeddingRequest(text=text, textHash=sha256_text(text), workspaceId="default")
    )

    assert first.status == "pass"
    assert first.vector == second.vector
    assert first.raw_content_included is False


def test_embedding_provider_blocks_secret_like_input() -> None:
    provider = DeterministicFixtureEmbeddingProvider()
    text = "token = abcdefghijklmnop"

    result = provider.embed(
        EmbeddingRequest(text=text, textHash=sha256_text(text), workspaceId="default")
    )

    assert result.status == "blocked"
    assert "MEMORY_EMBEDDING_SECRET_INPUT_BLOCKED" in result.reason_codes
