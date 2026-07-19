from __future__ import annotations

import json
import os
from pathlib import Path

from typer.testing import CliRunner

from imperaos.cli import app

runner = CliRunner()


def _write_status(root_dir: Path, job_id: str, payload: dict[str, object], index: int) -> None:
    job_dir = root_dir / job_id
    job_dir.mkdir(parents=True)
    status_path = job_dir / "status.json"
    status_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    touched = 1_700_000_000 + index
    os.utime(status_path, (touched, touched))


def test_computer_use_summary_handles_missing_root(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "computer-use",
            "summary",
            "--root-dir",
            str(tmp_path / "missing"),
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["contractVersion"] == "3.0"
    assert payload["status"] == "ok"
    assert payload["window"]["observed"] == 0
    assert payload["counts"] == {
        "success": 0,
        "blocked": 0,
        "failed": 0,
        "stopped": 0,
        "active": 0,
    }


def test_computer_use_summary_aggregates_and_clips_recent_outcomes(tmp_path: Path) -> None:
    root_dir = tmp_path / "jobs"
    fixtures = [
        (
            "cu-success",
            {
                "job": {
                    "job_id": "cu-success",
                    "status": "completed",
                    "finished_at": "2026-03-14T10:00:00Z",
                },
                "computer_use": {"session_state": "completed"},
            },
        ),
        (
            "cu-blocked",
            {
                "job": {
                    "job_id": "cu-blocked",
                    "status": "blocked",
                    "finished_at": "2026-03-14T10:05:00Z",
                },
                "computer_use": {
                    "session_state": "awaiting_approval",
                    "last_control_result": {"reason": "approval_not_executed"},
                    "raw_screenshot_path": str(tmp_path / "private-screen.png"),
                },
            },
        ),
        (
            "cu-failed",
            {
                "job": {
                    "job_id": "cu-failed",
                    "status": "failed",
                    "finished_at": "2026-03-14T10:10:00Z",
                },
                "computer_use": {
                    "session_state": "failed",
                    "surface_mismatch": {"code": "wrong_tab"},
                },
            },
        ),
        (
            "cu-stopped",
            {
                "job": {
                    "job_id": "cu-stopped",
                    "status": "failed",
                    "finished_at": "2026-03-14T10:15:00Z",
                },
                "computer_use": {
                    "session_state": "stopped",
                    "stopped_by_user": True,
                },
            },
        ),
    ]
    for index, (job_id, payload) in enumerate(fixtures):
        _write_status(root_dir, job_id, payload, index)

    result = runner.invoke(
        app,
        [
            "computer-use",
            "summary",
            "--root-dir",
            str(root_dir),
            "--limit",
            "3",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["window"] == {"limit": 3, "observed": 3}
    assert payload["counts"] == {
        "success": 0,
        "blocked": 1,
        "failed": 1,
        "stopped": 1,
        "active": 0,
    }
    assert payload["top_failure_codes"][0]["code"] in {
        "wrong_tab",
        "approval_not_executed",
    }
    encoded = json.dumps(payload, sort_keys=True)
    assert "raw_screenshot_path" not in encoded
    assert "private-screen.png" not in encoded


def test_computer_use_summary_no_json_prints_human_summary(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "computer-use",
            "summary",
            "--root-dir",
            str(tmp_path / "missing"),
            "--no-json",
        ],
    )

    assert result.exit_code == 0
    assert "No computer-use pilot runs" in result.stdout
