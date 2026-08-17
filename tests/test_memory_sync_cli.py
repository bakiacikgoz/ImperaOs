import json

from typer.testing import CliRunner

from imperaos.cli import app

runner = CliRunner()


def test_memory_runtime_and_sync_cli_smoke() -> None:
    with runner.isolated_filesystem():
        runtime = runner.invoke(app, ["memory", "runtime", "doctor", "--profile", "balanced"])
        assert runtime.exit_code == 0
        assert json.loads(runtime.stdout)["enabled"] is False

        export = runner.invoke(
            app,
            [
                "memory",
                "sync",
                "export",
                "--profile",
                "balanced",
                "--output",
                "sync.json",
                "--source-environment",
                "cli-test",
            ],
        )
        assert export.exit_code == 0

        verify = runner.invoke(app, ["memory", "sync", "verify", "--input", "sync.json"])
        assert verify.exit_code == 0
