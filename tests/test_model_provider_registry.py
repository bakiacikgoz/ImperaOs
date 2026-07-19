from __future__ import annotations

from pathlib import Path

import pytest

from imperaos.model_providers.errors import InvalidProviderConfig
from imperaos.model_providers.registry import resolve_model_provider_registry
from imperaos.runtime.config import RuntimeConfig


def test_resolves_synthetic_local_providers_when_registry_file_missing(tmp_path: Path) -> None:
    config = RuntimeConfig(provider_registry_path=str(tmp_path / "missing.toml"))
    registry = resolve_model_provider_registry(config=config, profile="balanced")

    ids = {item.provider_id for item in registry.providers}
    assert {"local-ollama", "local-transformers"} <= ids
    assert registry.remote_providers_enabled is False


def test_valid_example_registry_loads() -> None:
    registry = resolve_model_provider_registry(
        config=RuntimeConfig(),
        profile="balanced",
        provider_config_path=Path("config/providers.example.toml"),
    )

    assert registry.get("company-internal") is not None
    assert registry.get("openai-public") is not None
    assert registry.policy_for("openai-public").allowed_data_classes == ["public"]


def test_env_can_activate_remote_provider_when_runtime_allows_remote() -> None:
    registry = resolve_model_provider_registry(
        config=RuntimeConfig(remote_providers_enabled=True),
        profile="balanced",
        provider_config_path=Path("config/providers.example.toml"),
        env={"DEEPSEEK_API_KEY": "test-key"},
    )

    provider = registry.get("deepseek-public")
    assert registry.remote_providers_enabled is True
    assert provider is not None
    assert provider.enabled is True


def test_blank_env_secret_does_not_activate_remote_provider() -> None:
    registry = resolve_model_provider_registry(
        config=RuntimeConfig(remote_providers_enabled=True),
        profile="balanced",
        provider_config_path=Path("config/providers.example.toml"),
        env={"DEEPSEEK_API_KEY": "  "},
    )

    provider = registry.get("deepseek-public")
    assert provider is not None
    assert provider.enabled is False


def test_inline_secret_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "providers.toml"
    path.write_text(
        """
[providers.bad]
kind = "openai_compatible"
enabled = true
base_url = "https://example.com/v1"
api_key = "sk-test-secret"
auth_mode = "bearer_env"
api_key_env = "BAD_KEY"
default_model = "bad"
data_boundary = "public_cloud"
retention_policy = "provider_default"
""",
        encoding="utf-8",
    )

    with pytest.raises(InvalidProviderConfig, match="INLINE_SECRET_REJECTED"):
        resolve_model_provider_registry(
            config=RuntimeConfig(),
            profile="balanced",
            provider_config_path=path,
        )
