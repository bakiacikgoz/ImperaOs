from __future__ import annotations

from typer.testing import CliRunner

from imperaos.cli import app


def test_release_decision_build_cli_writes_conditional_pack(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "artifacts" / "release-gates" / "mainline-rc").mkdir(parents=True)
    (tmp_path / "artifacts" / "mainline-rc-freeze").mkdir(parents=True)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "release",
            "decision",
            "build",
            "--profile",
            "enterprise",
            "--artifact-root",
            "artifacts",
            "--output-root",
            "artifacts/rc-release-decision",
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert "release-decision-dossier/v1" in result.stdout


def test_release_decision_signoff_template_cli(tmp_path) -> None:
    output = tmp_path / "release_owner.template.json"
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "release",
            "decision",
            "signoff-template",
            "--dossier-sha256",
            "a" * 64,
            "--role",
            "release_owner",
            "--output",
            str(output),
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert output.exists()
