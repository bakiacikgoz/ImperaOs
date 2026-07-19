from __future__ import annotations

from pathlib import Path

from imperaos.tools.sandbox_runner import SandboxRunner


def test_sandbox_runner_rejects_unauthorized_command(tmp_path: Path) -> None:
    runner = SandboxRunner(workdir=tmp_path)
    result = runner.run(["rm", "-rf", "/tmp/should-not-run"])

    assert result.allowed is False
    assert result.exit_code == 126


def test_sandbox_runner_allows_safe_command(tmp_path: Path) -> None:
    runner = SandboxRunner(workdir=tmp_path)
    result = runner.run(["python", "-c", "print('ok')"])

    assert result.allowed is True
    assert result.exit_code == 0
    assert "ok" in result.stdout
