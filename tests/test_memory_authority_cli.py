import json

from typer.testing import CliRunner

from imperaos.cli import app

runner = CliRunner()


def test_workspace_memory_cli_smoke() -> None:
    with runner.isolated_filesystem():
        init = runner.invoke(
            app,
            [
                "memory",
                "workspace",
                "init",
                "--workspace-id",
                "default",
                "--owner-principal-id",
                "agent-local",
            ],
        )
        assert init.exit_code == 0

        write = runner.invoke(
            app,
            [
                "memory",
                "authority",
                "propose-write",
                "--workspace-id",
                "default",
                "--principal-id",
                "agent-local",
                "--scope-type",
                "personal",
                "--scope-id",
                "agent-local",
                "--summary",
                "CLI memory authority smoke.",
                "--memory-target",
                "cli-smoke",
            ],
        )
        assert write.exit_code == 0
        assert json.loads(write.stdout)["status"] == "committed"

        query = runner.invoke(
            app,
            [
                "memory",
                "authority",
                "query",
                "--workspace-id",
                "default",
                "--principal-id",
                "agent-local",
                "--scope-type",
                "personal",
                "--scope-id",
                "agent-local",
                "--query",
                "CLI",
            ],
        )
        assert query.exit_code == 0
        assert json.loads(query.stdout)["rawContentIncluded"] is False

        export = runner.invoke(
            app,
            [
                "memory",
                "workspace",
                "sync",
                "export",
                "--workspace-id",
                "default",
                "--output",
                "workspace-pack.json",
            ],
        )
        assert export.exit_code == 0

        verify = runner.invoke(
            app,
            ["memory", "workspace", "sync", "verify", "--input", "workspace-pack.json"],
        )
        assert verify.exit_code == 0
