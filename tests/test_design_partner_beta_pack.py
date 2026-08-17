from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from imperaos.cli import app
from imperaos.control_plane.beta_pack import generate_design_partner_beta_pack
from imperaos.runtime.config import RuntimeConfig

runner = CliRunner()


def test_design_partner_beta_pack_collects_required_artifacts(tmp_path: Path) -> None:
    evidence_root = _beta_artifacts(tmp_path)

    manifest = generate_design_partner_beta_pack(
        output_root=evidence_root / "design-partner-beta",
        evidence_root=evidence_root,
        config=RuntimeConfig.from_profile("enterprise"),
    )

    assert manifest["status"] == "conditional"
    assert manifest["copiedArtifacts"]["design-partner-pilot"] is True
    assert manifest["copiedArtifacts"]["code-intelligence/fallow"] is True
    assert manifest["copiedArtifacts"]["external-agent-v1-1"] is True
    assert manifest["noSecretScan"]["status"] == "pass"
    assert "code-intelligence" in manifest["warnings"]
    assert manifest["blockers"] == []
    assert (evidence_root / "design-partner-beta" / "BETA_OPERATIONS_REPORT.md").exists()
    assert (evidence_root / "design-partner-beta" / "control-plane-snapshot.json").exists()


def test_design_partner_beta_pack_blocks_false_ready_safety_claim(tmp_path: Path) -> None:
    evidence_root = _beta_artifacts(tmp_path, public_desktop_status="allowed")

    manifest = generate_design_partner_beta_pack(
        output_root=evidence_root / "design-partner-beta",
        evidence_root=evidence_root,
        config=RuntimeConfig.from_profile("enterprise"),
    )

    assert manifest["status"] == "blocked"
    assert "safety-claims" in manifest["blockers"]


def test_design_partner_beta_pack_is_ready_on_first_run_without_existing_manifest(
    tmp_path: Path,
) -> None:
    evidence_root = _beta_artifacts(tmp_path, fallow_verdict="pass")
    assert not (evidence_root / "design-partner-beta" / "manifest.json").exists()

    manifest = generate_design_partner_beta_pack(
        output_root=evidence_root / "design-partner-beta",
        evidence_root=evidence_root,
        config=RuntimeConfig.from_profile("enterprise"),
    )

    assert manifest["status"] == "ready"
    assert manifest["warnings"] == []
    assert manifest["blockers"] == []
    assert manifest["codeIntelligence"]["status"] == "ready"
    assert manifest["pilotOperations"]["status"] == "ready"
    assert manifest["designPartnerBeta"]["status"] == "ready"
    assert manifest["designPartnerBeta"]["warnings"] == []


def test_design_partner_beta_pack_cli(tmp_path: Path) -> None:
    evidence_root = _beta_artifacts(tmp_path)

    result = runner.invoke(
        app,
        [
            "pilot",
            "beta-pack",
            "--evidence-root",
            str(evidence_root),
            "--output-root",
            str(evidence_root / "design-partner-beta"),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert json.loads(result.stdout)["status"] == "conditional"


def _beta_artifacts(
    tmp_path: Path,
    *,
    public_desktop_status: str = "blocked",
    fallow_verdict: str = "warn",
) -> Path:
    root = tmp_path / "artifacts"
    _write_json(
        root / "design-partner-pilot" / "manifest.json",
        {
            "status": "ready",
            "claimGuard": {
                "claims": [
                    {
                        "claim_id": "enterprise-self-hosted-agent-control-plane",
                        "status": "allowed",
                    },
                    {"claim_id": "public-desktop-installer", "status": public_desktop_status},
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
    (root / "design-partner-pilot" / "PILOT_LAUNCH_REPORT.md").write_text(
        "# Pilot\n",
        encoding="utf-8",
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
    _write_json(
        root / "ci" / "node-action-inventory.json",
        {"status": "pass", "node20WarningPresent": True, "actions": []},
    )
    _write_json(root / "security-review" / "security_review_pack.json", {"status": "pass"})
    (root / "security-review" / "SECURITY_REVIEW_SUMMARY.md").write_text(
        "# Security Review\n",
        encoding="utf-8",
    )
    return root


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
