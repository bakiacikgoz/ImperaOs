from __future__ import annotations

from imperaos.model_providers.models import (
    AuthMode,
    DataBoundary,
    ModelProviderRecord,
    ProviderKind,
    ProviderPolicy,
)
from imperaos.model_providers.network import evaluate_provider_network


def _provider(
    *,
    provider_id: str = "openai-public",
    base_url: str = "https://api.openai.com/v1",
    boundary: DataBoundary = DataBoundary.PUBLIC_CLOUD,
) -> ModelProviderRecord:
    return ModelProviderRecord(
        provider_id=provider_id,
        kind=ProviderKind.OPENAI_COMPATIBLE,
        enabled=True,
        base_url=base_url,
        auth_mode=AuthMode.BEARER_ENV,
        api_key_env="OPENAI_API_KEY",
        default_model="gpt-5.1",
        data_boundary=boundary,
    )


def test_public_cloud_requires_explicit_host_allowlist() -> None:
    decision = evaluate_provider_network(
        provider=_provider(),
        policy=ProviderPolicy(provider_id="openai-public", allowed_hosts=[]),
    )

    assert not decision.allowed
    assert decision.reason_code == "PROVIDER_HOST_NOT_ALLOWLISTED"


def test_public_cloud_allowlisted_https_host_passes() -> None:
    decision = evaluate_provider_network(
        provider=_provider(),
        policy=ProviderPolicy(provider_id="openai-public", allowed_hosts=["api.openai.com"]),
    )

    assert decision.allowed
    assert decision.reason_code == "PROVIDER_HOST_ALLOWED"


def test_internal_private_host_passes_without_public_allowlist() -> None:
    decision = evaluate_provider_network(
        provider=_provider(
            provider_id="company-internal",
            base_url="https://llm.company.local/v1",
            boundary=DataBoundary.INTERNAL,
        ),
        policy=ProviderPolicy(provider_id="company-internal"),
    )

    assert decision.allowed
