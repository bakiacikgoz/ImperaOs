from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from imperaos.cli import app
from imperaos.control_plane.security_review import (
    _claim_consistency,
    generate_security_review_pack,
    scan_no_secrets,
)
from imperaos.runtime.config import RuntimeConfig

runner = CliRunner()


def test_no_secret_scan_blocks_fake_secret(tmp_path: Path) -> None:
    (tmp_path / "unsafe.txt").write_text("api_key = abcdefghijklmnop", encoding="utf-8")

    result = scan_no_secrets(tmp_path)

    assert result["status"] == "fail"
    assert result["findings"][0]["ruleId"] == "ASSIGNMENT_API_KEY"


def test_no_secret_scan_allows_redacted_fixture(tmp_path: Path) -> None:
    (tmp_path / "safe.txt").write_text("api_key = ***REDACTED***", encoding="utf-8")

    result = scan_no_secrets(tmp_path)

    assert result["status"] == "pass"


def test_claim_contradiction_blocks_security_review() -> None:
    result = _claim_consistency(
        {
            "claims": [
                {"claim_id": "public-desktop-installer", "status": "allowed"},
                {"claim_id": "live-macos-computer-use", "status": "blocked"},
                {"claim_id": "live-windows-computer-use", "status": "blocked"},
                {"claim_id": "live-linux-computer-use", "status": "blocked"},
            ]
        }
    )

    assert result["status"] == "blocked"
    assert "PUBLIC_DESKTOP_FALSE_READY" in result["blockingReasons"]


def test_security_review_pack_generates_artifacts(tmp_path: Path) -> None:
    pack = generate_security_review_pack(
        output_root=tmp_path / "security-review",
        config=RuntimeConfig.from_profile("lite"),
        evidence_root=tmp_path / "missing-evidence",
    )

    assert pack["status"] == "pass"
    assert (tmp_path / "security-review" / "SECURITY_REVIEW_SUMMARY.md").exists()
    assert (tmp_path / "security-review" / "no_secret_scan.json").exists()


def test_security_review_cli(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "control-plane",
            "security",
            "review",
            "--profile",
            "lite",
            "--output-root",
            str(tmp_path / "security-review"),
            "--evidence-root",
            str(tmp_path / "missing-evidence"),
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout)["status"] == "pass"
