from __future__ import annotations

from imperaos.control_plane.snapshot import build_control_plane_snapshot


def test_control_plane_snapshot_exposes_missing_mainline_rc_freeze(tmp_path) -> None:
    snapshot = build_control_plane_snapshot(
        root_dir=tmp_path / "control-plane",
        evidence_root=tmp_path / "artifacts",
    )
    payload = snapshot.model_dump(mode="json", by_alias=True)

    assert payload["mainlineRcFreeze"]["status"] == "missing"
    assert "MAINLINE_RC_FREEZE_MISSING" in payload["mainlineRcFreeze"]["warnings"]
