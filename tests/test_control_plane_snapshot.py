from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from typer.testing import CliRunner

from imperaos.cli import app
from imperaos.control_plane.models import ControlPlaneSnapshot
from imperaos.control_plane.snapshot import classify_data_source

runner = CliRunner()


def test_data_source_classification_modes() -> None:
    now = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)

    preview = classify_data_source(
        runtime_mode="browser",
        bridge_mode="preview",
        used_fixture=True,
        cli_available=True,
        generated_at=now,
        now=now,
    )
    assert preview.mode == "preview_fixture"
    assert preview.is_mock is True
    assert preview.is_silent_fallback is False

    live_fallback = classify_data_source(
        runtime_mode="tauri",
        bridge_mode="tauri",
        used_fixture=True,
        cli_available=True,
        generated_at=now,
        now=now,
    )
    assert live_fallback.mode == "preview_fixture"
    assert live_fallback.is_silent_fallback is True

    stale = classify_data_source(
        runtime_mode="cli",
        bridge_mode="cli",
        used_fixture=False,
        cli_available=True,
        generated_at=now - timedelta(minutes=10),
        now=now,
    )
    assert stale.mode == "stale_cache"
    assert stale.freshness == "stale"

    error = classify_data_source(
        runtime_mode="cli",
        bridge_mode="cli",
        used_fixture=False,
        cli_available=False,
        generated_at=None,
        now=now,
    )
    assert error.mode == "error"
    assert error.freshness == "unknown"


def test_control_plane_snapshot_cli_contract(tmp_path: Path) -> None:
    root = tmp_path / "cp"
    spec = Path("examples/control_plane/agent_governed_ops.yaml").resolve()

    register = runner.invoke(
        app,
        [
            "control-plane",
            "agent",
            "register",
            "--spec",
            str(spec),
            "--profile",
            "lite",
            "--root-dir",
            str(root),
            "--json",
        ],
    )
    assert register.exit_code == 0

    submit = runner.invoke(
        app,
        [
            "control-plane",
            "run",
            "submit",
            "--agent-id",
            "governed-ops",
            "--once",
            "inspect queue",
            "--profile",
            "lite",
            "--root-dir",
            str(root),
            "--json",
        ],
    )
    assert submit.exit_code == 0

    snapshot = runner.invoke(
        app,
        [
            "control-plane",
            "snapshot",
            "--profile",
            "lite",
            "--root-dir",
            str(root),
            "--evidence-root",
            str(tmp_path / "artifacts"),
            "--json",
        ],
    )
    assert snapshot.exit_code == 0
    payload = json.loads(snapshot.stdout)
    parsed = ControlPlaneSnapshot.model_validate(payload)

    assert parsed.contract_version == "control-plane.snapshot/v1"
    assert parsed.data_source.mode == "cli_live"
    assert parsed.data_source.is_mock is False
    assert parsed.data_source.is_silent_fallback is False
    assert parsed.agents[0].agent_id == "governed-ops"
    assert parsed.agents[0].agent_type == "internal"
    assert parsed.agents[0].policy_pack_id == "active-runtime-policy"
    assert parsed.agents[0].last_evidence_status == "missing"
    assert parsed.runs[0].status == "approval_pending"
    assert parsed.approvals
    assert parsed.evidence_packs == []
    assert parsed.policy_packs[0].pack_id == "active-runtime-policy"
    assert {surface.surface_id for surface in parsed.execution_surfaces} == {
        "core-runtime",
        "team-runtime",
        "computer-use",
        "public-desktop-installer",
    }
    assert parsed.system.health.status == "partial"
    assert "metrics_snapshot" in parsed.system.health.missing_signals
    assert "qualification_report" in parsed.partial_reasons
    assert parsed.design_partner_rc.schema_version == "control-plane.design-partner-rc/v1"
    assert parsed.design_partner_rc.status == "conditional"
    assert parsed.design_partner_rc.blockers == []
    assert "evidence-index" in parsed.design_partner_rc.warnings
    assert parsed.pilot_launch.schema_version == "control-plane.pilot-launch-readiness/v1"
    assert parsed.pilot_launch.status in {"conditional", "blocked"}
    assert parsed.pilot_launch.install_rehearsal.status == "missing"
    assert parsed.operations
    assert {operation.operation_id for operation in parsed.operations} >= {
        "install.rehearsal",
        "security.review",
    }
    assert {operation.category for operation in parsed.operations} >= {
        "identity",
        "qualification",
        "security",
        "keys",
        "support",
        "backup",
        "restore",
        "migration",
    }
    assert parsed.admin.users


def test_operator_panel_preview_snapshot_fixture_is_contract_valid() -> None:
    fixture = Path("contracts/operator_panel/fixtures/control_plane_snapshot_preview.json")
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    parsed = ControlPlaneSnapshot.model_validate(payload)

    assert parsed.data_source.mode == "preview_fixture"
    assert parsed.data_source.is_mock is True
    assert parsed.data_source.is_silent_fallback is False
    assert parsed.system.health.status == "partial"
    assert parsed.design_partner_rc.status == "conditional"
    assert "preview-source" in parsed.design_partner_rc.warnings
    assert parsed.pilot_launch.status == "conditional"
    assert parsed.pilot_launch.evidence_corpus.status == "ready"
    assert parsed.pilot_launch.admin_proposals
    assert {operation.category for operation in parsed.operations} >= {
        "identity",
        "qualification",
        "security",
        "keys",
        "support",
        "backup",
        "restore",
        "migration",
    }
