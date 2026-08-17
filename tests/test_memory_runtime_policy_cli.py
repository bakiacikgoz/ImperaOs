import json

from typer.testing import CliRunner

from imperaos.cli import app

runner = CliRunner()


def test_memory_runtime_policy_cli_doctor_default_disabled() -> None:
    result = runner.invoke(app, ["memory", "runtime", "policy", "doctor", "--profile", "balanced"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["policyEnforcementEnabled"] is False
    assert payload["rawContentIncluded"] is False


def test_memory_runtime_policy_cli_simulate_read_hash_only() -> None:
    result = runner.invoke(
        app,
        [
            "memory",
            "runtime",
            "policy",
            "simulate",
            "--operation",
            "read",
            "--query",
            "hash only policy evidence",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "pass"
    assert "hash only policy evidence" not in result.stdout
    assert payload["rawContentIncluded"] is False
