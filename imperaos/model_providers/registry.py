from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from imperaos.model_providers.errors import InvalidProviderConfig, ProviderRegistryError
from imperaos.model_providers.models import (
    AuthMode,
    DataBoundary,
    ModelProviderRecord,
    ProviderKind,
    ProviderPolicy,
    ResolvedProviderRegistry,
    RetentionPolicy,
    RiskTier,
)
from imperaos.runtime.config import RuntimeConfig

SECRET_FIELD_NAMES = {"api_key", "secret", "token", "password", "authorization"}


def resolve_model_provider_registry(
    *,
    config: RuntimeConfig,
    profile: str,
    provider_config_path: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> ResolvedProviderRegistry:
    """Load and validate provider registry without resolving secret values."""

    payload = _load_provider_payload(provider_config_path)
    _reject_inline_secrets(payload)

    providers = _synthetic_local_providers(config)
    policies: list[ProviderPolicy] = []
    remote_enabled = bool(getattr(config, "remote_providers_enabled", False))

    settings = payload.get("settings", {})
    if isinstance(settings, Mapping) and "remote_providers_enabled" in settings:
        remote_enabled = remote_enabled or bool(settings["remote_providers_enabled"])

    raw_providers = payload.get("providers", {})
    if raw_providers and not isinstance(raw_providers, Mapping):
        raise InvalidProviderConfig("providers must be a TOML table")
    for provider_id, raw in raw_providers.items():
        if not isinstance(raw, Mapping):
            raise InvalidProviderConfig(f"provider {provider_id} must be a table")
        record_payload = {"provider_id": str(provider_id), **dict(raw)}
        try:
            record = ModelProviderRecord.model_validate(record_payload)
        except ValidationError as exc:
            raise InvalidProviderConfig(str(exc)) from exc
        providers = [item for item in providers if item.provider_id != record.provider_id]
        providers.append(
            _apply_env_activation(
                record,
                remote_enabled=remote_enabled,
                env=env or os.environ,
            )
        )

    raw_policies = payload.get("provider_policies", {})
    if raw_policies and not isinstance(raw_policies, Mapping):
        raise InvalidProviderConfig("provider_policies must be a TOML table")
    for provider_id, raw in raw_policies.items():
        if not isinstance(raw, Mapping):
            raise InvalidProviderConfig(f"provider policy {provider_id} must be a table")
        policy_payload = {"provider_id": str(provider_id), **dict(raw)}
        try:
            policies.append(ProviderPolicy.model_validate(policy_payload))
        except ValidationError as exc:
            raise InvalidProviderConfig(str(exc)) from exc

    _validate_unique_provider_ids(providers)
    _validate_policy_refs(providers, policies)
    _mark_missing_secret_warnings(providers, env or os.environ)
    return ResolvedProviderRegistry(
        profile=profile,
        remote_providers_enabled=remote_enabled,
        providers=providers,
        policies=policies,
    )


def load_provider_registry_from_path(path: Path) -> dict[str, Any]:
    return _load_provider_payload(path)


def _load_provider_payload(path: Path | None) -> dict[str, Any]:
    if path is None:
        default_path = Path("config/providers.toml")
        example_path = Path("config/providers.example.toml")
        path = default_path if default_path.exists() else example_path
    if path is None or not path.exists():
        return {}
    with path.open("rb") as file_obj:
        return tomllib.load(file_obj)


def _synthetic_local_providers(config: RuntimeConfig) -> list[ModelProviderRecord]:
    return [
        ModelProviderRecord(
            provider_id="local-ollama",
            kind=ProviderKind.LOCAL_OLLAMA,
            enabled=True,
            display_name="Local Ollama",
            auth_mode=AuthMode.NONE,
            default_model=config.model_name,
            models=[config.model_name] if config.model_name else [],
            data_boundary=DataBoundary.LOCAL,
            retention_policy=RetentionPolicy.NONE_CLAIMED,
            supports_streaming=True,
            supports_json_mode=True,
            risk_tier=RiskTier.LOW,
            fallback_priority=10,
        ),
        ModelProviderRecord(
            provider_id="local-transformers",
            kind=ProviderKind.LOCAL_TRANSFORMERS,
            enabled=True,
            display_name="Local Transformers",
            auth_mode=AuthMode.NONE,
            default_model=config.hf_model_id,
            models=[config.hf_model_id] if config.hf_model_id else [],
            data_boundary=DataBoundary.LOCAL,
            retention_policy=RetentionPolicy.NONE_CLAIMED,
            supports_streaming=True,
            risk_tier=RiskTier.LOW,
            fallback_priority=20,
        ),
    ]


def _reject_inline_secrets(value: Any, path: str = "") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key)
            lowered = key_text.lower()
            current_path = f"{path}.{key_text}" if path else key_text
            if lowered in SECRET_FIELD_NAMES:
                raise InvalidProviderConfig(f"INLINE_SECRET_REJECTED at {current_path}")
            _reject_inline_secrets(item, current_path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _reject_inline_secrets(item, f"{path}[{index}]")


def _validate_unique_provider_ids(providers: list[ModelProviderRecord]) -> None:
    seen: set[str] = set()
    for item in providers:
        if item.provider_id in seen:
            raise ProviderRegistryError(f"duplicate provider_id: {item.provider_id}")
        seen.add(item.provider_id)


def _validate_policy_refs(
    providers: list[ModelProviderRecord],
    policies: list[ProviderPolicy],
) -> None:
    ids = {item.provider_id for item in providers}
    for policy in policies:
        if policy.provider_id not in ids:
            raise InvalidProviderConfig(f"policy references unknown provider: {policy.provider_id}")
        for fallback_id in policy.fallback_allowed_to:
            if fallback_id not in ids:
                raise InvalidProviderConfig(
                    f"policy {policy.provider_id} references unknown fallback: {fallback_id}"
                )


def _mark_missing_secret_warnings(
    providers: list[ModelProviderRecord],
    env: Mapping[str, str],
) -> None:
    # Registry resolution deliberately does not fail for missing env vars. Doctor reports it.
    for provider in providers:
        if provider.api_key_env and provider.api_key_env in env:
            continue


def _apply_env_activation(
    provider: ModelProviderRecord,
    *,
    remote_enabled: bool,
    env: Mapping[str, str],
) -> ModelProviderRecord:
    if not remote_enabled or provider.enabled or not provider.api_key_env:
        return provider
    if not str(env.get(provider.api_key_env, "")).strip():
        return provider
    return provider.model_copy(update={"enabled": True})
