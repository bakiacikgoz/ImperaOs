from __future__ import annotations

import json
from pathlib import Path

from scripts import run_macos_local_trial_gate as gate


def _payload(status: str = "ready", **extra: object) -> str:
    data = {"status": status, **extra}
    return json.dumps(data)


def test_macos_local_trial_gate_passes_with_safe_claim_boundaries(
    tmp_path: Path, monkeypatch
) -> None:
    def fake_run(command: list[str]) -> tuple[int, str]:
        if "computer-use" in command:
            return 0, _payload(
                "blocked",
                capabilityResolution={
                    "public_live_claim_allowed": False,
                    "platforms": {"macos": {"liveEnabled": False}},
                },
            )
        if "tauri-launched-smoke.ts" in command:
            return 0, _payload("passed")
        return 0, _payload("ready", previewFallbackAllowed=False)

    monkeypatch.setattr(gate, "_run_command", fake_run)

    report = gate.run_macos_local_trial_gate(output_root=tmp_path)

    assert report["status"] == "pass"
    assert report["blockers"] == []
    assert (
        "PUBLIC_DESKTOP_RELEASE_REQUIRES_SIGNING_AND_NOTARIZATION_EVIDENCE"
        in report["noShipBoundaries"]
    )
    assert (tmp_path / "macos_local_trial_gate.json").exists()
    assert (tmp_path / "MACOS_LOCAL_TRIAL_GATE.md").exists()
    assert (tmp_path / "no_ship_boundaries.json").exists()


def test_macos_local_trial_gate_marks_assistant_setup_required_conditional(
    tmp_path: Path, monkeypatch
) -> None:
    def fake_run(command: list[str]) -> tuple[int, str]:
        if "assistant" in command and "doctor" in command:
            return 3, _payload("setup_required", previewFallbackAllowed=False)
        if any(item.endswith("tauri-launched-smoke.ts") for item in command):
            return 0, _payload("conditional")
        if "computer-use" in command:
            return 0, _payload("blocked", capabilityResolution={"public_live_claim_allowed": False})
        return 0, _payload("ready", previewFallbackAllowed=False)

    monkeypatch.setattr(gate, "_run_command", fake_run)

    report = gate.run_macos_local_trial_gate(output_root=tmp_path)

    assert report["status"] == "conditional"
    assert "assistant_doctor:ASSISTANT_SETUP_REQUIRED" in report["conditionalNotes"]
    assert (
        "tauri_launched_smoke_contract:REAL_LAUNCHED_GUI_PROBE_NOT_EXECUTED"
        in report["conditionalNotes"]
    )
    assert report["blockers"] == []


def test_macos_local_trial_gate_blocks_preview_fallback(tmp_path: Path, monkeypatch) -> None:
    def fake_run(command: list[str]) -> tuple[int, str]:
        if "assistant" in command and "doctor" in command:
            return 0, _payload("ready", previewFallbackAllowed=True)
        if "computer-use" in command:
            return 0, _payload("blocked", capabilityResolution={"public_live_claim_allowed": False})
        return 0, _payload("ready")

    monkeypatch.setattr(gate, "_run_command", fake_run)

    report = gate.run_macos_local_trial_gate(output_root=tmp_path)

    assert report["status"] == "blocked"
    assert "ASSISTANT_PREVIEW_FALLBACK_ALLOWED" in report["blockers"]


def test_macos_local_trial_gate_redacts_secret_like_tail(tmp_path: Path, monkeypatch) -> None:
    def fake_run(command: list[str]) -> tuple[int, str]:
        return 1, "api_key=sk-testsecret1234567890"

    monkeypatch.setattr(gate, "_run_command", fake_run)

    report = gate.run_macos_local_trial_gate(output_root=tmp_path)

    assert report["status"] == "blocked"
    assert "<redacted>" in report["checks"][0]["tail"][0]
    assert report["secretLeakScan"]["redactedFindings"] == [
        "SECRET_LIKE_OUTPUT_REDACTED:imperaos_version"
    ]
