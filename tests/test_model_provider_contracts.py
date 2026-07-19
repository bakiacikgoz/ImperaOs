from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from imperaos.model_providers.errors import InvalidProviderConfig
from imperaos.model_providers.models import ResolvedProviderRegistry
from imperaos.model_providers.registry import resolve_model_provider_registry
from imperaos.runtime.config import RuntimeConfig


def test_schema_generator_writes_model_provider_contracts() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/generate_model_provider_contract_schemas.py"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    schema = json.loads(Path("contracts/model_providers/provider_registry.schema.json").read_text())
    assert schema["title"] == "ResolvedProviderRegistry"
    assert Path("contracts/model_providers/provider_conformance_matrix.schema.json").exists()
    assert Path("contracts/model_providers/native_adapter_v2_request.schema.json").exists()
    assert Path("contracts/model_providers/native_adapter_v2_response.schema.json").exists()
    assert Path("contracts/model_providers/openai_responses_request.schema.json").exists()
    assert Path("contracts/model_providers/openai_responses_result.schema.json").exists()
    assert Path("contracts/model_providers/provider_tool_policy_decision.schema.json").exists()
    assert Path("contracts/model_providers/provider_tool_proposal.schema.json").exists()


def test_provider_registry_fixture_matches_contract() -> None:
    payload = json.loads(
        Path("contracts/model_providers/fixtures/provider_registry_valid.json").read_text()
    )

    registry = ResolvedProviderRegistry.model_validate(payload)

    assert registry.get("company-internal") is not None
    assert registry.policy_for("company-internal").fallback_allowed_to == ["local-transformers"]


def test_inline_secret_fixture_is_rejected() -> None:
    with pytest.raises(InvalidProviderConfig):
        resolve_model_provider_registry(
            config=RuntimeConfig.from_profile("lite"),
            profile="lite",
            provider_config_path=Path(
                "contracts/model_providers/fixtures/provider_registry_invalid_inline_secret.toml"
            )
        )
