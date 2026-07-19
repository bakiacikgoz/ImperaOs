from __future__ import annotations

import json
import math
from typing import Protocol

from imperaos.memory.models import sha256_text
from imperaos.memory.redaction import MemoryRedactor
from imperaos.memory.semantic.models import EmbeddingRequest, EmbeddingResult


class MemoryEmbeddingProvider(Protocol):
    profile_id: str
    dimensions: int

    def embed(self, request: EmbeddingRequest) -> EmbeddingResult: ...


class DeterministicFixtureEmbeddingProvider:
    profile_id = "deterministic-fixture-v1"

    def __init__(self, dimensions: int = 16, redactor: MemoryRedactor | None = None) -> None:
        self.dimensions = dimensions
        self.redactor = redactor or MemoryRedactor()

    def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        normalized = " ".join(request.text.split())
        if request.text_hash != sha256_text(normalized):
            return EmbeddingResult(
                status="blocked",
                profileId=request.profile_id,
                provider="deterministic_fixture",
                reasonCodes=("MEMORY_EMBEDDING_TEXT_HASH_MISMATCH",),
            )
        redaction = self.redactor.redact_candidate(candidate_text=normalized)
        if redaction.secret_detected:
            return EmbeddingResult(
                status="blocked",
                profileId=request.profile_id,
                provider="deterministic_fixture",
                reasonCodes=("MEMORY_EMBEDDING_SECRET_INPUT_BLOCKED",),
            )
        vector = _normalize(_token_vector(redaction.redacted_summary.lower(), self.dimensions))
        embedding_hash = sha256_text(json.dumps(vector, sort_keys=True, separators=(",", ":")))
        return EmbeddingResult(
            status="pass",
            profileId=request.profile_id,
            provider="deterministic_fixture",
            dimensions=self.dimensions,
            vector=tuple(vector),
            embeddingHash=embedding_hash,
        )


class NullEmbeddingProvider:
    profile_id = "null"
    dimensions = 0

    def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        return EmbeddingResult(
            status="blocked",
            profileId=request.profile_id,
            provider="null",
            reasonCodes=("MEMORY_EMBEDDING_PROVIDER_DISABLED",),
        )


def build_embedding_provider(profile_id: str) -> MemoryEmbeddingProvider:
    if profile_id == "deterministic-fixture-v1":
        return DeterministicFixtureEmbeddingProvider()
    return NullEmbeddingProvider()


def cosine_similarity(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    score = sum(a * b for a, b in zip(left, right, strict=True))
    return max(0.0, min(1.0, score))


def _token_vector(text: str, dimensions: int) -> list[float]:
    vector = [0.0] * dimensions
    for token in text.split():
        digest = sha256_text(token)
        bucket = int(digest[:8], 16) % dimensions
        weight = 1.0 + (int(digest[8:10], 16) / 255.0)
        vector[bucket] += weight
    return vector


def _normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm <= 0.0:
        return vector
    return [round(value / norm, 6) for value in vector]
