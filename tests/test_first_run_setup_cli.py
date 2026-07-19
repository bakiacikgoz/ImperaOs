from __future__ import annotations

import json

from typer.testing import CliRunner

from imperaos.cli import app

runner = CliRunner()


def test_setup_first_run_reports_safe_diagnostic(monkeypatch) -> None:
    monkeypatch.setattr(
        "imperaos.cli._assistant_models_contract",
        lambda *, profile, provider: {
            "schemaVersion": "assistant.provider-models/v1",
            "profile": profile,
            "providers": [],
            "selectedDefault": None,
            "blockingReasons": ["ASSISTANT_MODEL_UNAVAILABLE"],
        },
    )

    result = runner.invoke(
        app,
        [
            "setup",
            "first-run",
            "--profile",
            "enterprise",
            "--mode",
            "local-enterprise",
            "--json",
        ],
    )

    assert result.exit_code == 3, result.stdout
    payload = json.loads(result.stdout)
    assert payload["schemaVersion"] == "setup.first-run/v1"
    assert payload["profile"] == "enterprise"
    assert payload["mode"] == "local-enterprise"
    assert payload["status"] == "setup_required"
    assert "ASSISTANT_MODEL_UNAVAILABLE" in payload["blockingReasons"]
    assert all(check["mutation"] == "none" for check in payload["checks"])
