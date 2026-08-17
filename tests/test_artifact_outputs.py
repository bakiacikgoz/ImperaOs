from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from imperaos.cli import app
from imperaos.runtime.config import ComputerUseRuntimeConfig, RuntimeConfig

runner = CliRunner()


class _WindowsPlatform:
    label = "windows"
    system = "Windows"
    machine = "AMD64"
    release = "test"


def _blocked_computer_use_config() -> RuntimeConfig:
    return RuntimeConfig(
        computer_use=ComputerUseRuntimeConfig(
            runtime_mode="vision_first",
            vision_enabled=True,
            vision_provider="ollama",
            vision_model="llava",
            max_steps=1,
        )
    )


def _patch_blocked_computer_use_cli(monkeypatch) -> None:
    monkeypatch.setattr(
        "imperaos.cli.resolve_runtime_config",
        lambda **_kwargs: (_blocked_computer_use_config(), {}),
    )
    monkeypatch.setattr("imperaos.cli._require_permission_or_exit", lambda *_args: None)
    monkeypatch.setattr(
        "imperaos.computer_use.runtime.current_platform",
        lambda: _WindowsPlatform(),
    )
    monkeypatch.setattr(
        "imperaos.computer_use.runtime._current_git_sha",
        lambda: "fixture-commit",
    )


def test_cli_doctor_creates_artifact_scaffold(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)

    def fake_status(**_: object):
        return {
            "selected_provider": "transformers",
            "primary": {"daemon_ok": False, "model_present": False},
            "secondary": {"runtime_available": True},
        }

    monkeypatch.setattr("imperaos.cli.check_provider_chain", fake_status)
    result = runner.invoke(app, ["doctor", "--profile", "lite"])

    assert result.exit_code == 0
    root = tmp_path / "artifacts"
    assert (root / "status.json").exists()
    assert (root / "test_summary.json").exists()
    assert (root / "benchmark_summary.json").exists()
    assert (root / "router_shadow_summary.json").exists()
    assert (root / "research_summary.json").exists()
    assert (root / "governance_summary.json").exists()


def test_cli_benchmark_updates_benchmark_summary(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)

    def fake_bench(**_: object):
        return {"results": {"A": {"success_rate": 1.0}}, "output_path": "x.json"}

    monkeypatch.setattr("imperaos.cli.run_smoke_benchmark", fake_bench)
    result = runner.invoke(app, ["benchmark", "smoke", "--mode", "A"])

    assert result.exit_code == 0
    summary = json.loads((tmp_path / "artifacts" / "benchmark_summary.json").read_text())
    assert summary["artifact"] == "benchmark_summary"
    assert summary["status"] == "ok"


def test_cli_computer_use_run_json_includes_blocked_runtime_preflight(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _patch_blocked_computer_use_cli(monkeypatch)
    result = runner.invoke(
        app,
        [
            "computer-use",
            "run",
            "--once",
            "Click export",
            "--runtime",
            "vision-first",
            "--root-dir",
            str(tmp_path / "jobs"),
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    runtime_preflight = payload["computer_use"]["runtimePreflight"]
    encoded = json.dumps(payload, sort_keys=True)
    assert payload["job"]["status"] == "blocked"
    assert runtime_preflight["status"] == "blocked"
    assert runtime_preflight["reasonCode"] == "WINDOWS_COMPUTER_USE_NOT_QUALIFIED"
    assert runtime_preflight["publicLiveClaimAllowed"] is False
    assert runtime_preflight["liveExecutionAttempted"] is False
    assert runtime_preflight["captureAttempted"] is False
    assert runtime_preflight["providerAttempted"] is False
    assert runtime_preflight["executorAttempted"] is False
    assert runtime_preflight["approvalCreated"] is False
    assert runtime_preflight["approvalConsumed"] is False
    assert "rawScreenshotPath" not in encoded
    assert "providerRawResponse" not in encoded
    assert "approvalSnapshotBody" not in encoded
    assert "duzey" not in encoded


def test_cli_computer_use_run_non_json_reports_reason_and_doctor_hint(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _patch_blocked_computer_use_cli(monkeypatch)
    result = runner.invoke(
        app,
        [
            "computer-use",
            "run",
            "--once",
            "Click export",
            "--runtime",
            "vision-first",
            "--root-dir",
            str(tmp_path / "jobs"),
            "--no-json",
        ],
    )

    assert result.exit_code == 0
    assert "status=blocked" in result.stdout
    assert "reason_code=WINDOWS_COMPUTER_USE_NOT_QUALIFIED" in result.stdout
    assert "computer-use doctor --json" in result.stdout
    assert "rawScreenshotPath" not in result.stdout
    assert "approvalSnapshotBody" not in result.stdout
    assert "duzey" not in result.stdout
