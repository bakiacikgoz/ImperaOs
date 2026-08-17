from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from imperaos.cli import app
from imperaos.control_plane.pilot_pack import generate_design_partner_pilot_pack
from imperaos.control_plane.qualification_closure import (
    generate_enterprise_hat_a_closure,
    write_pilot_qualification_fixture,
)
from imperaos.runtime.config import RuntimeConfig

runner = CliRunner()
REPO_ROOT = Path(__file__).resolve().parents[1]


def test_pilot_pack_ready_with_required_artifacts(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    _prepare_enterprise_fixture(tmp_path)
    config = RuntimeConfig.from_profile("enterprise")
    _write_required_artifacts(tmp_path, config=config)

    manifest = generate_design_partner_pilot_pack(
        output_root=tmp_path / "artifacts" / "design-partner-pilot",
        config=config,
    )

    assert manifest["status"] == "ready"
    assert (tmp_path / "artifacts" / "design-partner-pilot" / "manifest.json").exists()
    assert (
        tmp_path / "artifacts" / "design-partner-pilot" / "PILOT_LAUNCH_REPORT.md"
    ).exists()


def test_pilot_pack_blocks_without_enterprise_hat_a(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    _write_minimal_non_hat_a_artifacts(tmp_path)

    manifest = generate_design_partner_pilot_pack(
        output_root=tmp_path / "artifacts" / "design-partner-pilot",
        config=RuntimeConfig.from_profile("lite"),
    )

    assert manifest["status"] == "blocked"
    assert "ENTERPRISE_HAT_A_NOT_READY" in manifest["blockingReasons"]


def test_pilot_pack_cli(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    _prepare_enterprise_fixture(tmp_path)
    config = RuntimeConfig.from_profile("enterprise")
    _write_required_artifacts(tmp_path, config=config)

    result = runner.invoke(
        app,
        [
            "control-plane",
            "pilot",
            "pack",
            "--profile",
            "enterprise",
            "--output-root",
            str(tmp_path / "artifacts" / "design-partner-pilot"),
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout)["status"] == "ready"


def _prepare_enterprise_fixture(root: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/prepare_enterprise_fixture.py"),
            "--root",
            str(root),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def _write_required_artifacts(root: Path, *, config: RuntimeConfig) -> None:
    report = write_pilot_qualification_fixture(
        output_root=root / "qualification",
        config=config,
        now=datetime.now(UTC),
    )
    generate_enterprise_hat_a_closure(
        profile="enterprise",
        output_root=root / "artifacts" / "enterprise-hat-a",
        qualification_root=report.parent,
        config=config,
    )
    _write_minimal_non_hat_a_artifacts(root)


def _write_minimal_non_hat_a_artifacts(root: Path) -> None:
    _write_json(root / "artifacts" / "install-rehearsal" / "report.json", {"status": "pass"})
    _write_json(
        root / "artifacts" / "design-partner-pilot" / "external-agent-pilot-report.json",
        {"status": "pass", "cases": [{"policyDecision": "allow"}]},
    )
    _write_json(
        root / "artifacts" / "design-partner-pilot" / "governance-admin-report.json",
        {"status": "pass", "appliedCount": 1, "pendingApprovalCount": 0},
    )
    _write_json(
        root / "artifacts" / "evidence-corpus" / "corpus_report.json",
        {"status": "pass", "cases": [{"actualStatus": "pass"}]},
    )
    security_root = root / "artifacts" / "security-review"
    _write_json(security_root / "security_review_pack.json", {"status": "pass"})
    (security_root / "SECURITY_REVIEW_SUMMARY.md").write_text(
        "# Security Review\n",
        encoding="utf-8",
    )


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
