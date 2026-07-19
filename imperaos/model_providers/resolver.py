from __future__ import annotations

from imperaos.model_providers.models import ModelProviderRecord, ResolvedProviderRegistry

LEGACY_PROVIDER_TO_ID = {
    "auto": "local-ollama",
    "ollama": "local-ollama",
    "transformers": "local-transformers",
    "hf": "local-transformers",
    "huggingface": "local-transformers",
}


def resolve_provider_id(
    *,
    registry: ResolvedProviderRegistry,
    provider_id: str | None = None,
    legacy_provider: str | None = None,
) -> str:
    if provider_id:
        return provider_id
    normalized = (legacy_provider or "auto").strip().lower()
    mapped = LEGACY_PROVIDER_TO_ID.get(normalized, normalized)
    if registry.get(mapped) is not None:
        return mapped
    return mapped


def get_provider_or_none(
    *,
    registry: ResolvedProviderRegistry,
    provider_id: str,
) -> ModelProviderRecord | None:
    return registry.get(provider_id)
