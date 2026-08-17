from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from imperaos.cli import app
from imperaos.control_plane.models import AlertSummary, ReportSummary
from imperaos.control_plane.reports import build_reports_alerts_logs_manifest
from imperaos.control_plane.snapshot import build_control_plane_snapshot

runner = CliRunner()


def test_reports_alerts_logs_manifest_writes_outputs(tmp_path: Path) -> None:
    snapshot = build_control_plane_snapshot(
        root_dir=tmp_path / "cp",
        profile="lite",
        evidence_root=tmp_path / "artifacts",
    )

    manifest = build_reports_alerts_logs_manifest(
        snapshot=snapshot,
        output_dir=tmp_path / "reports",
    )

    assert manifest.version == "control-plane.report-manifest/v1"
    assert manifest.reports
    assert manifest.logs_export_ref is not None
    assert Path(manifest.logs_export_ref).exists()
    assert (tmp_path / "reports" / "manifest.json").exists()


def test_reports_alerts_logs_cli_manifest(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "control-plane",
            "reports",
            "manifest",
            "--profile",
            "lite",
            "--root-dir",
            str(tmp_path / "cp"),
            "--evidence-root",
            str(tmp_path / "artifacts"),
            "--output-dir",
            str(tmp_path / "reports"),
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["version"] == "control-plane.report-manifest/v1"
    assert payload["logsExportRef"]


def test_reports_manifest_resolves_expected_blocked_boundary_alerts(tmp_path: Path) -> None:
    snapshot = build_control_plane_snapshot(
        root_dir=tmp_path / "cp",
        profile="lite",
        evidence_root=tmp_path / "artifacts",
    )
    snapshot.alerts = [
        _active_alert("claim-public-desktop-installer", "CLEAN_MACHINE_SMOKE_MISSING")
    ]

    manifest = build_reports_alerts_logs_manifest(
        snapshot=snapshot,
        output_dir=tmp_path / "reports",
    )

    assert manifest.status == "pass"
    assert manifest.alerts[0].severity == "info"
    assert manifest.alerts[0].state == "resolved"


def test_reports_manifest_resolves_superseded_qualification_gap(tmp_path: Path) -> None:
    snapshot = build_control_plane_snapshot(
        root_dir=tmp_path / "cp",
        profile="lite",
        evidence_root=tmp_path / "artifacts",
    )
    snapshot.alerts = [_active_alert("missing-qualification", "QUALIFICATION_MISSING")]
    snapshot.reports = [
        ReportSummary(
            report_id="qualification",
            kind="qualification",
            title="Qualification report",
            status="missing",
            path=None,
            generated_at_utc=None,
            blocking_reasons=["QUALIFICATION_MISSING"],
        ),
        ReportSummary(
            report_id="enterprise-hat-a",
            kind="qualification",
            title="Enterprise Hat A closure",
            status="ready",
            path=str(tmp_path / "enterprise_hat_a_closure.json"),
            generated_at_utc=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
            blocking_reasons=[],
        ),
    ]

    manifest = build_reports_alerts_logs_manifest(
        snapshot=snapshot,
        output_dir=tmp_path / "reports",
    )

    assert manifest.status == "pass"
    assert manifest.alerts[0].severity == "info"
    assert manifest.alerts[0].state == "resolved"


def _active_alert(alert_id: str, reason_code: str) -> AlertSummary:
    return AlertSummary(
        alert_id=alert_id,
        severity="error" if alert_id.startswith("claim-") else "warning",
        status="active",
        title="Active alert",
        reason_code=reason_code,
        recommended_action="Review evidence.",
    )
