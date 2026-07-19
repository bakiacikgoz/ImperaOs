from __future__ import annotations

import shutil
from pathlib import Path

from imperaos.runtime.config import redact_config_payload, resolve_runtime_config


def test_resolve_runtime_config_precedence_cli_wins_over_env_and_profile() -> None:
    env = {
        "IMPERAOS_LLM_PROVIDER": "ollama",
        "IMPERAOS_FALLBACK_PROVIDER": "transformers",
    }
    cfg, source_map = resolve_runtime_config(
        profile="lite",
        env=env,
        cli_overrides={"llm_provider": "transformers"},
    )

    assert cfg.llm_provider == "transformers"
    assert cfg.fallback_provider == "transformers"
    assert source_map["llm_provider"] == "cli"
    assert source_map["fallback_provider"] == "env"


def test_resolve_runtime_config_model_and_hf_source_map() -> None:
    env = {
        "IMPERAOS_MODEL_NAME": "env-model",
        "IMPERAOS_HF_MODEL_ID": "env/hf-model",
    }
    cfg, source_map = resolve_runtime_config(
        profile="lite",
        env=env,
        cli_overrides={"model_name": "cli-model"},
    )

    assert cfg.model_name == "cli-model"
    assert cfg.hf_model_id == "env/hf-model"
    assert source_map["model_name"] == "cli"
    assert source_map["hf_model_id"] == "env"


def test_resolve_runtime_config_is_deterministic() -> None:
    env = {"IMPERAOS_ROUTER_MODE": "rule"}
    first, _ = resolve_runtime_config(profile="balanced", env=env)
    second, _ = resolve_runtime_config(profile="balanced", env=env)
    assert first.model_dump(mode="python") == second.model_dump(mode="python")


def test_resolve_runtime_config_uses_explicit_config_root(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    shutil.copytree(Path("config"), config_dir)

    cfg, source_map = resolve_runtime_config(
        profile="balanced",
        env={
            "IMPERAOS_CONFIG_ROOT": str(config_dir),
            "IMPERAOS_REMOTE_PROVIDERS_ENABLED": "true",
        },
    )

    assert cfg.profile_name == "balanced"
    assert cfg.remote_providers_enabled is True
    assert source_map["remote_providers_enabled"] == "env"


def test_resolve_runtime_config_ignores_legacy_project_prefixes() -> None:
    legacy_product_prefix = "BIN" + "LIQUID"
    former_product_prefix = "AE" + "GIS" + "OS"

    cfg, source_map = resolve_runtime_config(
        profile="lite",
        env={
            f"{legacy_product_prefix}_MODEL_NAME": "legacy-model",
            f"{former_product_prefix}_MODEL_NAME": "former-model",
        },
    )

    assert cfg.model_name == "lfm2.5-thinking:1.2b"
    assert source_map["model_name"] == "profile"


def test_resolve_runtime_config_ignores_legacy_config_root(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    shutil.copytree(Path("config"), config_dir)
    config_path = config_dir / "balanced.toml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            'model_name = "lfm2.5-thinking:1.2b"',
            'model_name = "legacy-root-model"',
            1,
        ),
        encoding="utf-8",
    )
    legacy_config_root = ("BIN" + "LIQUID") + "_CONFIG_ROOT"

    cfg, _ = resolve_runtime_config(
        profile="balanced",
        env={legacy_config_root: str(config_dir)},
    )

    assert cfg.model_name == "lfm2.5-thinking:1.2b"


def test_redact_config_payload_masks_sensitive_keys() -> None:
    signing_secret = "fixture-signing-secret"
    payload = {
        "llm_provider": "auto",
        "api_token": "secret-value",
        "nested": {"service_key": "k-123"},
        "environment": {"IMPERAOS_AUDIT_SIGNING_KEY": signing_secret},
    }
    redacted = redact_config_payload(payload)
    assert redacted["api_token"] == "***REDACTED***"
    assert redacted["nested"]["service_key"] == "***REDACTED***"
    assert redacted["environment"]["IMPERAOS_AUDIT_SIGNING_KEY"] == "***REDACTED***"
    assert signing_secret not in repr(redacted)
