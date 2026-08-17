from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from imperaos.cli import app

runner = CliRunner()


def test_team_pilot_check_deterministic_passes(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    spec_path = Path(__file__).resolve().parents[1] / "examples" / "team" / "restricted_pilot.yaml"
    report_path = tmp_path / "artifacts" / "team_pilot_report.json"
    pilot_root = tmp_path / "pilot-root"

    result = runner.invoke(
        app,
        [
            "team",
            "pilot-check",
            "--spec",
            str(spec_path),
            "--profile",
            "restricted",
            "--mode",
            "deterministic",
            "--root-dir",
            str(pilot_root),
            "--report",
            str(report_path),
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["overall_status"] == "pass"
    assert payload["checks"]["approval_lifecycle"]["status"] == "pass"
    assert payload["checks"]["audit_completeness"]["status"] == "pass"
    assert payload["checks"]["replay_integrity"]["status"] == "pass"
    assert payload["checks"]["scope_isolation"]["status"] == "pass"
    assert payload["checks"]["handoff_contract"]["status"] == "pass"
    assert payload["checks"]["policy_profile_enforcement"]["status"] == "pass"
    assert payload["checks"]["bounded_concurrency"]["status"] == "pass"
    assert payload["checks"]["determinism"]["status"] == "pass"
    assert payload["bounded_concurrency_status"] == "pass"
    assert payload["counters"]["approvals_consumed"] >= 1
    assert payload["counters"]["memory_read_count"] >= 1
    assert payload["counters"]["memory_write_count"] >= 1
    assert payload["counters"]["handoff_count"] >= 1
    assert payload["counters"]["stale_approval_count"] == 0
    assert payload["counters"]["memory_conflict_count"] == 0
    assert payload["counters"]["tamper_verify_unexpected_pass_count"] == 0
    assert payload["counters"]["approval_reuse_unexpected_success_count"] == 0
    assert payload["counters"]["scope_violation_unexpected_success_count"] == 0
    assert any(
        item["name"] == "tamper-probe" and item["status"] == "pass"
        for item in payload["scenario_runs"]
    )
    assert any(
        item["name"] == "reuse-probe" and item["status"] == "pass"
        for item in payload["scenario_runs"]
    )
    assert any(
        item["name"] == "scope-probe" and item["status"] == "pass"
        for item in payload["scenario_runs"]
    )

    report_body = json.loads(report_path.read_text(encoding="utf-8"))
    assert report_body["artifact"] == "team_pilot_report"
    assert report_body["status"] == "ok"
    assert report_body["data"]["overall_status"] == "pass"
    assert Path(report_body["data"]["artifacts"]["pilot_root"]).exists()
