from __future__ import annotations

from imperaos.control_plane.provider_native import NativeProviderAdapter
from imperaos.control_plane.providers.anthropic_messages import AnthropicMessagesAdapter
from imperaos.control_plane.providers.openai_responses import OpenAIResponsesAdapter


def get_native_provider_adapter(provider_kind: str) -> NativeProviderAdapter:
    if provider_kind == "openai_responses":
        return OpenAIResponsesAdapter()
    if provider_kind == "anthropic_messages":
        return AnthropicMessagesAdapter()
    raise KeyError(provider_kind)


__all__ = [
    "AnthropicMessagesAdapter",
    "NativeProviderAdapter",
    "OpenAIResponsesAdapter",
    "get_native_provider_adapter",
]
