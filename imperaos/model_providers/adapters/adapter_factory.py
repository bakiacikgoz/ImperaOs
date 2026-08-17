from __future__ import annotations

from collections.abc import Mapping

from imperaos.core.providers import OllamaProvider, TransformersProvider
from imperaos.model_providers.adapters.openai_compatible import OpenAICompatibleProvider
from imperaos.model_providers.errors import ProviderNotFound
from imperaos.model_providers.models import (
    ModelProviderRecord,
    ProviderKind,
    ResolvedProviderRegistry,
)


class ProviderAdapterFactory:
    def __init__(self, *, registry: ResolvedProviderRegistry, env: Mapping[str, str] | None = None):
        self.registry = registry
        self.env = env

    def create(self, provider_id: str):
        provider = self.registry.get(provider_id)
        if provider is None:
            raise ProviderNotFound(f"provider not found: {provider_id}")
        return create_adapter(provider, env=self.env)


def create_adapter(provider: ModelProviderRecord, *, env: Mapping[str, str] | None = None):
    if provider.kind == ProviderKind.LOCAL_OLLAMA:
        return OllamaProvider(model_name=provider.default_model)
    if provider.kind == ProviderKind.LOCAL_TRANSFORMERS:
        return TransformersProvider(
            model_name=provider.default_model,
            hf_model_id=provider.default_model,
        )
    if provider.kind in {
        ProviderKind.OPENAI_COMPATIBLE,
        ProviderKind.COMPANY_INTERNAL_API,
        ProviderKind.OPENAI,
        ProviderKind.DEEPSEEK,
        ProviderKind.OPENROUTER,
        ProviderKind.CUSTOM_HTTP,
    }:
        return OpenAICompatibleProvider(provider=provider, env=env)
    raise ProviderNotFound(f"provider kind is not supported by adapter factory: {provider.kind}")
