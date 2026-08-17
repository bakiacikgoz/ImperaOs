from __future__ import annotations

import json

from typer.testing import CliRunner

from imperaos.cli import app
from imperaos.control_plane.provider_conformance import run_provider_native_gate

runner = CliRunner()


def test_provider_native_gate_runs_openai_and_anthropic_offline(tmp_path) -> None:
    gate = run_provider_native_gate(profile="enterprise", output_dir=tmp_path)

    assert gate["status"] == "pass"
    assert {item["providerKind"] for item in gate["reports"]} == {
        "openai_responses",
        "anthropic_messages",
    }
    for item in gate["reports"]:
        assert item["offline"] is True
        assert item["fixturesRun"] > 0


def test_provider_cli_registry_inspect_and_conformance(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    registry = runner.invoke(
        app,
        ["provider", "registry", "--profile", "enterprise", "--json"],
    )
    assert registry.exit_code == 0
    registry_payload = json.loads(registry.stdout)
    assert registry_payload["contractVersion"] == "control-plane.provider-governance/v1"

    inspect = runner.invoke(
        app,
        [
            "provider",
            "inspect",
            "--provider",
            "openai_responses",
            "--profile",
            "enterprise",
            "--json",
        ],
    )
    assert inspect.exit_code == 0
    inspect_payload = json.loads(inspect.stdout)
    assert inspect_payload["providerKind"] == "openai_responses"
    assert inspect_payload["credentialState"] == "missing"

    conformance = runner.invoke(
        app,
        [
            "provider",
            "native",
            "conformance",
            "--provider",
            "openai_responses",
            "--profile",
            "enterprise",
            "--offline",
            "--output-dir",
            str(tmp_path),
            "--json",
        ],
    )
    assert conformance.exit_code == 0
    conformance_payload = json.loads(conformance.stdout)
    assert conformance_payload["status"] == "pass"
    assert conformance_payload["providerKind"] == "openai_responses"
