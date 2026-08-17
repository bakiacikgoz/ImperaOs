from __future__ import annotations

from pathlib import Path

from imperaos.control_plane.snapshot import build_control_plane_snapshot
from imperaos.release.gate_plan import build_release_gate_plan
from imperaos.release.gate_runner import run_release_gate_plan


def test_control_plane_snapshot_exposes_rc_gate_evidence(tmp_path: Path) -> None:
    output_root = tmp_path / "artifacts" / "release-gates" / "mainline-rc"
    plan = build_release_gate_plan(
        target="mainline-rc",
        profile="enterprise",
        mode="rc-focused",
        platform="windows",
        repo_root=tmp_path,
        output_root=output_root,
    )
    run_release_gate_plan(plan=plan, repo_root=tmp_path, output_root=output_root)

    snapshot = build_control_plane_snapshot(
        root_dir=tmp_path / ".imperaos" / "control-plane",
        evidence_root=tmp_path / "artifacts",
        profile="enterprise",
    )

    assert snapshot.rc_gate_evidence.status == "ready"
    assert snapshot.rc_gate_evidence.ready_for_rc_freeze is True
    assert snapshot.rc_gate_evidence.make_required is False
