from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from imperaos.cli import app
from imperaos.control_plane.pilot_operations import (
    build_code_intelligence_summary,
    build_design_partner_beta_status,
    generate_pilot_operations_artifacts,
)

runner = CliRunner()


def test_pilot_operations_artifacts_are_local_redacted_bundle(tmp_path: Path) -> None:
    evidence_root = _pilot_artifacts(tmp_path)

    payload = generate_pilot_operations_artifacts(
        output_root=evidence_root / "pilot-ops",
        evidence_root=evidence_root,
    )

    assert payload["status"] == "conditional"
    assert payload["redaction"] == "local_only_no_pii_no_raw_screenshots"
    assert payload["acceptanceMetrics"]["externalAgentV11Passed"] == 2
    checklist = {item["itemId"]: item for item in payload["checklist"]}
    assert checklist["feedback-bundle"]["status"] == "ready"
    assert checklist["safety-claims"]["status"] == "ready"
    assert payload["blockers"] == []
    assert (evidence_root / "pilot-ops" / "PILOT_FEEDBACK.md").exists()
    assert (evidence_root / "pilot-ops" / "FIRST_RUN_CHECKLIST.md").exists()


def test_design_partner_beta_status_summarizes_pilot_ops_without_false_ready(
    tmp_path: Path,
) -> None:
    evidence_root = _pilot_artifacts(tmp_path)
    generate_pilot_operations_artifacts(
        output_root=evidence_root / "pilot-ops",
        evidence_root=evidence_root,
    )

    status = build_design_partner_beta_status(evidence_root=evidence_root)

    assert status.status == "conditional"
    assert status.code_intelligence.status == "conditional"
    assert status.pilot_operations.status == "conditional"
    assert "code-intelligence" in status.warnings
    assert "pilot-operations" in status.warnings
    assert "beta-pack" not in status.warnings
    assert status.blockers == []


def test_code_intelligence_ready_requires_pass_secret_scan_and_disabled_telemetry(
    tmp_path: Path,
) -> None:
    evidence_root = _pilot_artifacts(tmp_path, fallow_verdict="pass")

    status = build_code_intelligence_summary(evidence_root=evidence_root)

    assert status.status == "ready"
    assert status.verdict == "pass"
    assert status.boundary_violations == 0
    assert status.secret_scan_status == "pass"
    assert status.telemetry_disabled is True
    assert status.warnings == []


def test_code_intelligence_blocks_missing_secret_scan_or_telemetry(tmp_path: Path) -> None:
    evidence_root = _pilot_artifacts(tmp_path, fallow_verdict="pass")
    summary_path = evidence_root / "code-intelligence" / "fallow" / "summary.json"
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    payload.pop("secret_scan")
    payload["telemetry_disabled"] = False
    _write_json(summary_path, payload)

    status = build_code_intelligence_summary(evidence_root=evidence_root)

    assert status.status == "blocked"
    assert "FALLOW_SECRET_SCAN_FAILED" in status.blockers
    assert "FALLOW_TELEMETRY_NOT_DISABLED" in status.blockers


def test_pilot_first_run_cli_writes_feedback_bundle(tmp_path: Path) -> None:
    evidence_root = _pilot_artifacts(tmp_path)
    output_root = evidence_root / "pilot-ops"

    result = runner.invoke(
        app,
        [
            "pilot",
            "first-run",
            "--output-root",
            str(output_root),
            "--evidence-root",
            str(evidence_root),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["status"] == "conditional"
    assert (output_root / "pilot_feedback_bundle.json").exists()


def _pilot_artifacts(tmp_path: Path, *, fallow_verdict: str = "warn") -> Path:
    root = tmp_path / "artifacts"
    _write_json(
        root / "design-partner-pilot" / "manifest.json",
        {
            "status": "ready",
            "claimGuard": {
                "claims": [
                    {"claim_id": "public-desktop-installer", "status": "blocked"},
                    {"claim_id": "live-macos-computer-use", "status": "blocked"},
                ]
            },
        },
    )
    _write_json(
        root / "design-partner-pilot" / "pilot_metrics.json",
        {
            "status": "pass",
            "runCount": 3,
            "externalAgentRuns": 3,
            "claimGuard": {"allowed": 1, "blocked": 2, "conditional": 0},
            "policyDecisions": {"allow": 1, "deny": 1, "requireApproval": 1},
        },
    )
    _write_json(
        root / "external-agent-v1-1" / "results.json",
        {
            "status": "pass",
            "cases": [
                {"case": "read", "passed": True},
                {"case": "write", "passed": True},
            ],
        },
    )
    _write_json(
        root / "ci" / "node-action-inventory.json",
        {"status": "pass", "node20WarningPresent": True, "actions": []},
    )
    _write_json(
        root / "code-intelligence" / "fallow" / "summary.json",
        {
            "generated_at": "2026-06-04T12:00:00Z",
            "tool": "fallow",
            "tool_version": "2.88.3",
            "telemetry_disabled": True,
            "dead_code": {
                "total": 0 if fallow_verdict == "pass" else 1,
                "errors": 0,
                "warnings": 0 if fallow_verdict == "pass" else 1,
                "notes": [] if fallow_verdict == "pass" else ["unused=1"],
            },
            "duplication": {"total": 0, "errors": 0, "warnings": 0, "notes": []},
            "health": {"total": 0, "errors": 0, "warnings": 0, "notes": []},
            "boundaries": {"total": 0, "errors": 0, "warnings": 0, "notes": []},
            "secret_scan": {"status": "pass", "findings": []},
            "verdict": fallow_verdict,
            "blocking_reasons": [],
            "warnings": [] if fallow_verdict == "pass" else ["dead_code:1"],
        },
    )
    return root


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
