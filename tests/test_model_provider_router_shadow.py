from __future__ import annotations

from imperaos.model_providers.models import DataClass, ProviderRouteShadowRequest
from imperaos.model_providers.registry import resolve_model_provider_registry
from imperaos.model_providers.router_shadow import recommend_provider_shadow
from imperaos.runtime.config import RuntimeConfig


def test_router_shadow_confidential_prefers_local_without_override() -> None:
    config = RuntimeConfig.from_profile("enterprise")
    registry = resolve_model_provider_registry(config=config, profile="enterprise")

    decision = recommend_provider_shadow(
        registry=registry,
        request=ProviderRouteShadowRequest(data_classes=[DataClass.CONFIDENTIAL]),
    )

    assert decision.shadow_only is True
    assert decision.recommended_provider_id == "local-ollama"
    assert "openai-public" in {item.provider_id for item in decision.blocked_providers}


def test_router_shadow_required_capability_filters_candidates() -> None:
    config = RuntimeConfig.from_profile("enterprise")
    registry = resolve_model_provider_registry(config=config, profile="enterprise")

    decision = recommend_provider_shadow(
        registry=registry,
        request=ProviderRouteShadowRequest(
            data_classes=[DataClass.PUBLIC],
            required_capabilities=["tool_calling"],
        ),
    )

    assert decision.shadow_only is True
    assert any(
        item.reason_code == "PROVIDER_UNSUPPORTED_CAPABILITY" for item in decision.candidates
    )
    assert all(
        not item.allowed or item.provider_id != "local-ollama" for item in decision.candidates
    )
