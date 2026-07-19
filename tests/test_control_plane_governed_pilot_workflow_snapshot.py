from __future__ import annotations

from pathlib import Path

from imperaos.control_plane.pilot_workflow import (
    build_governed_pilot_workflow_snapshot,
    load_governed_pilot_workflow_spec,
    run_governed_pilot_workflow,
)
from imperaos.control_plane.snapshot import build_control_plane_snapshot

SPEC = Path("examples/pilot_workflows/enterprise_governed_memory_provider.yaml")


def test_governed_pilot_workflow_snapshot_reports_missing(tmp_path: Path) -> None:
    snapshot = build_governed_pilot_workflow_snapshot(artifact_root=tmp_path)

    assert snapshot.status == "missing"
    assert snapshot.enabled is False
    assert "GOVERNED_PILOT_WORKFLOW_NOT_RUN" in snapshot.blocking_reasons


def test_control_plane_snapshot_includes_governed_pilot_workflow(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    run_governed_pilot_workflow(
        load_governed_pilot_workflow_spec(SPEC),
        output_root=artifact_root / "governed-pilot-workflow",
    )

    snapshot = build_control_plane_snapshot(
        root_dir=tmp_path / "control-plane",
        evidence_root=artifact_root,
    )

    assert snapshot.governed_pilot_workflow.enabled is True
    assert snapshot.governed_pilot_workflow.status == "pass"
    assert snapshot.governed_pilot_workflow.verifier_status == "pass"
    payload = snapshot.model_dump(mode="json", by_alias=True)
    assert payload["governedPilotWorkflow"]["workflowId"] == (
        "enterprise-governed-memory-provider"
    )
