from __future__ import annotations

from pathlib import Path

from imperaos.model_providers.models import ChatMessage, DataClass, ProviderCallRequest
from imperaos.model_providers.policy import GovernanceContext, evaluate_provider_policy
from imperaos.model_providers.registry import resolve_model_provider_registry
from imperaos.runtime.config import RuntimeConfig


def _registry(remote_enabled: bool = False):
    return resolve_model_provider_registry(
        config=RuntimeConfig(remote_providers_enabled=remote_enabled),
        profile="enterprise",
        provider_config_path=Path("config/providers.example.toml"),
    )


def _request(provider_id: str, data_classes: list[DataClass]) -> ProviderCallRequest:
    return ProviderCallRequest(
        call_id="test",
        run_id="run",
        provider_id=provider_id,
        model="model",
        messages=[ChatMessage(role="user", content="hello")],
        data_classes=data_classes,
    )


def test_public_cloud_confidential_is_denied() -> None:
    registry = _registry(remote_enabled=True)
    provider = registry.get("openai-public")
    assert provider is not None

    decision = evaluate_provider_policy(
        request=_request("openai-public", [DataClass.CONFIDENTIAL]),
        provider=provider,
        policy=registry.policy_for(provider.provider_id),
        governance_context=GovernanceContext(remote_providers_enabled=True),
    )

    assert decision.status == "deny"
    assert decision.reason_code == "PROVIDER_DATA_BOUNDARY_DENIED"
    assert decision.safe_to_call_provider is False


def test_remote_provider_disabled_flag_blocks_public_call() -> None:
    registry = _registry(remote_enabled=False)
    provider = registry.get("company-internal")
    assert provider is not None

    decision = evaluate_provider_policy(
        request=_request("company-internal", [DataClass.PUBLIC]),
        provider=provider,
        policy=registry.policy_for(provider.provider_id),
        governance_context=GovernanceContext(remote_providers_enabled=False),
    )

    assert decision.reason_code == "PROVIDER_REMOTE_DISABLED"
    assert decision.safe_to_call_provider is False


def test_local_provider_allows_confidential_by_default() -> None:
    registry = _registry()
    provider = registry.get("local-ollama")
    assert provider is not None

    decision = evaluate_provider_policy(
        request=_request("local-ollama", [DataClass.CONFIDENTIAL]),
        provider=provider,
        policy=registry.policy_for(provider.provider_id),
        governance_context=GovernanceContext(remote_providers_enabled=False),
    )

    assert decision.safe_to_call_provider is True
    assert decision.reason_code == "PROVIDER_READY"


def test_secret_class_is_always_blocked() -> None:
    registry = _registry()
    provider = registry.get("local-ollama")
    assert provider is not None

    decision = evaluate_provider_policy(
        request=_request("local-ollama", [DataClass.SECRET]),
        provider=provider,
        policy=registry.policy_for(provider.provider_id),
        governance_context=GovernanceContext(),
    )

    assert decision.reason_code == "PROVIDER_BLOCKED_DATA_CLASS"
    assert decision.safe_to_call_provider is False
