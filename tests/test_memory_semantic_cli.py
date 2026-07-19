import json

from typer.testing import CliRunner

from imperaos.cli import app

runner = CliRunner()


def test_semantic_cli_status_and_backend_doctor_default_disabled() -> None:
    status = runner.invoke(app, ["memory", "semantic", "status", "--workspace-id", "default"])
    assert status.exit_code == 0
    assert json.loads(status.stdout)["status"] == "available_disabled"

    doctor = runner.invoke(app, ["memory", "semantic", "backend", "doctor"])
    assert doctor.exit_code == 0
    payload = json.loads(doctor.stdout)
    assert payload["rawContentIncluded"] is False
    assert payload["turbovec"]["status"] in {"unavailable_optional", "blocked"}
