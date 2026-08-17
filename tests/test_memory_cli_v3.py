import json

from typer.testing import CliRunner

from imperaos.cli import app

runner = CliRunner()


def test_memory_cli_doctor_and_propose_org_approval() -> None:
    with runner.isolated_filesystem():
        doctor = runner.invoke(app, ["memory", "doctor", "--profile", "balanced"])
        assert doctor.exit_code == 0
        doctor_payload = json.loads(doctor.stdout)
        assert doctor_payload["contractVersion"] == "memory.authority-snapshot/v1"
        assert doctor_payload["privacy"]["rawPromptPersistence"] is False

        propose = runner.invoke(
            app,
            [
                "memory",
                "propose",
                "--profile",
                "balanced",
                "--scope",
                "organization",
                "--owner-type",
                "org",
                "--owner",
                "imperaos",
                "--visibility",
                "organization",
                "--text",
                "organization policy summary",
                "--reason",
                "approval test",
            ],
        )
        assert propose.exit_code == 0
        payload = json.loads(propose.stdout)
        assert payload["status"] == "approval_required"
        assert payload["rawContentIncluded"] is False
