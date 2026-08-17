from __future__ import annotations

import subprocess
from pathlib import Path

from scripts import run_product_complete_closure_gate as gate


def test_command_timeout_fails_closed(monkeypatch) -> None:
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], timeout=1, output="partial")

    monkeypatch.setattr(gate.subprocess, "run", timeout)
    result = gate._run(["stuck"], name="required", required=True)
    assert result["status"] == "fail"
    assert result["reasonCode"] == "COMMAND_TIMEOUT"


def test_empty_readiness_starts_every_required_check_as_not_run() -> None:
    readiness = gate._empty_readiness()

    assert all(readiness[key] == "not_run" for key in gate.REQUIRED_READINESS)


def test_skipping_commands_cannot_report_product_complete_pass(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(gate, "_git", lambda _args: "test")

    report = gate.run_product_complete_closure_gate(
        output_root=tmp_path,
        profile="enterprise",
        skip_commands=True,
    )

    assert report["status"] == "fail"
    assert report["checks"] == []
    assert report["productReadiness"] == gate._empty_readiness()
    for readiness_key in gate.REQUIRED_READINESS:
        assert (
            f"PRODUCT_COMPLETE_REQUIRED_CHECK_NOT_RUN:{readiness_key}" in report["noShipBlockers"]
        )
        assert report["readinessEvidence"][readiness_key] == {
            "checkName": gate.READINESS_CHECKS[readiness_key],
            "status": "not_run",
            "artifactRef": None,
        }
