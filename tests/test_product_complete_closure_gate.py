from __future__ import annotations

from pathlib import Path

from scripts import run_product_complete_closure_gate as gate

HEAD = "a" * 40


def _fake_git(args: list[str]) -> str:
    return HEAD if args == ["rev-parse", "HEAD"] else "main"


def test_product_complete_closure_gate_passes_when_required_checks_pass(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(gate, "_git", _fake_git)
    monkeypatch.setattr(
        gate,
        "_run",
        lambda command, *, name, required=True: {
            "name": name,
            "command": command,
            "required": required,
            "returnCode": 0,
            "status": "pass",
            "reasonCode": "OK",
            "tail": [],
        },
    )

    report = gate.run_product_complete_closure_gate(
        output_root=tmp_path,
        profile="enterprise",
        skip_commands=False,
    )

    assert report["schemaVersion"] == "product-complete.closure/v1"
    assert report["status"] == "pass"
    assert report["headSha"] == HEAD
    assert report["noShipBlockers"] == []
    assert report["productReadiness"] == {
        "assistant": "pass",
        "operatorPanel": "pass",
        "enterpriseWorkspace": "pass",
        "governedWorkflow": "pass",
        "installerFirstRun": "pass",
        "evidence": "pass",
        "macosLocalTrial": "not_run",
    }
    assert all(
        report["readinessEvidence"][key]["status"] == "pass"
        for key in gate.REQUIRED_READINESS
    )
    assert (tmp_path / "product_complete_closure_report.json").exists()
    assert (tmp_path / "product_complete_pr_body.md").exists()


def test_product_complete_closure_gate_blocks_required_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(gate, "_git", _fake_git)

    def fake_run(command: list[str], *, name: str, required: bool = True) -> dict[str, object]:
        return {
            "name": name,
            "command": command,
            "required": required,
            "returnCode": 1 if name == "assistant_real_runtime_gate" else 0,
            "status": "fail" if name == "assistant_real_runtime_gate" else "pass",
            "reasonCode": "COMMAND_FAILED" if name == "assistant_real_runtime_gate" else "OK",
            "tail": [],
        }

    monkeypatch.setattr(gate, "_run", fake_run)

    report = gate.run_product_complete_closure_gate(
        output_root=tmp_path,
        profile="enterprise",
        skip_commands=False,
    )

    assert report["status"] == "fail"
    assert "PRODUCT_COMPLETE_CHECK_FAILED:assistant_real_runtime_gate" in report["noShipBlockers"]
    assert report["productReadiness"]["assistant"] == "fail"


def test_product_complete_closure_gate_can_include_conditional_local_trial(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(gate, "_git", _fake_git)

    def fake_run(command: list[str], *, name: str, required: bool = True) -> dict[str, object]:
        if name == "macos_local_trial_gate":
            return {
                "name": name,
                "command": command,
                "required": required,
                "returnCode": 3,
                "status": "conditional",
                "reasonCode": "MACOS_LOCAL_TRIAL_CONDITIONAL",
                "tail": [],
            }
        return {
            "name": name,
            "command": command,
            "required": required,
            "returnCode": 0,
            "status": "pass",
            "reasonCode": "OK",
            "tail": [],
        }

    monkeypatch.setattr(gate, "_run", fake_run)

    report = gate.run_product_complete_closure_gate(
        output_root=tmp_path,
        profile="enterprise",
        skip_commands=False,
        include_local_trial=True,
    )

    assert report["status"] == "pass"
    assert report["productReadiness"]["macosLocalTrial"] == "conditional"
    assert report["conditionalNotes"] == ["macOS local trial has setup-required notes."]
    assert report["noShipBlockers"] == []
