from __future__ import annotations

import json

from typer.testing import CliRunner

from imperaos.cli import app

runner = CliRunner()


def test_provider_registry_list_cli_outputs_safe_registry() -> None:
    result = runner.invoke(app, ["provider", "registry", "list", "--profile", "balanced", "--json"])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["contractVersion"] == "model_provider.registry/v1"
    assert "providers" in payload
    assert "sk-" not in result.stdout


def test_provider_policy_simulate_deny_exits_zero_with_decision() -> None:
    result = runner.invoke(
        app,
        [
            "provider",
            "policy",
            "simulate",
            "--profile",
            "balanced",
            "--provider-id",
            "openai-public",
            "--data-class",
            "confidential",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["reasonCode"] in {
        "PROVIDER_REMOTE_DISABLED",
        "PROVIDER_DATA_BOUNDARY_DENIED",
    }
    assert payload["safeToCallProvider"] is False


def test_provider_models_includes_registry_driven_contract() -> None:
    result = runner.invoke(
        app,
        ["provider", "models", "--profile", "balanced", "--provider", "all", "--json"],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["contractVersion"] == "operator-panel.assistant-provider-models/v4"
    assert any(item["provider"] == "local-ollama" for item in payload["providers"])
