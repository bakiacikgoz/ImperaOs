from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from imperaos.control_plane.design_partner_rc import evaluate_design_partner_rc_audit


def _manifest(
    *,
    status: str = "conditional",
    warnings: list[str] | None = None,
    blockers: list[str] | None = None,
) -> dict[str, object]:
    return {
        "status": status,
        "designPartnerRcStatus": status,
        "warnings": warnings or [],
        "blockers": blockers or [],
    }


def test_expected_conditionals_are_audit_pass_but_strict_conditional() -> None:
    result = evaluate_design_partner_rc_audit(
        _manifest(warnings=["provider-governance", "artifact:evidence_index.json"]),
        expected_conditionals={"provider-governance", "artifact:evidence_index.json"},
    )

    assert result.strict_status == "conditional"
    assert result.audit_status == "pass"
    assert result.expected_conditionals == (
        "artifact:evidence_index.json",
        "provider-governance",
    )
    assert result.unexpected_warnings == ()
    assert result.blockers == ()


def test_unexpected_warning_blocks_audit_gate() -> None:
    result = evaluate_design_partner_rc_audit(
        _manifest(warnings=["provider-governance", "active-alerts"]),
        expected_conditionals={"provider-governance"},
    )

    assert result.audit_status == "blocked"
    assert result.unexpected_warnings == ("active-alerts",)


def test_blocker_blocks_audit_gate() -> None:
    result = evaluate_design_partner_rc_audit(
        _manifest(status="blocked", blockers=["computer-use-boundary"]),
        expected_conditionals={"provider-governance"},
    )

    assert result.strict_status == "blocked"
    assert result.audit_status == "blocked"
    assert result.blockers == ("computer-use-boundary",)


def test_rc_audit_gate_script_writes_machine_readable_result(tmp_path: Path) -> None:
    output = tmp_path / "audit.json"

    proc = subprocess.run(
        [
            sys.executable,
            "scripts/run_design_partner_rc_audit_gate.py",
            "--profile",
            "enterprise",
            "--allow-expected-conditionals",
            "--output",
            str(output),
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, proc.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["auditStatus"] == "pass"
    assert payload["exitMode"] == "blocker_only"
    assert payload["blockers"] == []
    assert "provider-governance" in payload["expectedConditionals"]
