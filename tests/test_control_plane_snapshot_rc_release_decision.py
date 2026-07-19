from __future__ import annotations

from pathlib import Path

from imperaos.release_decision.snapshot import build_rc_release_decision_snapshot


def test_control_plane_rc_release_decision_missing_is_not_available(tmp_path: Path) -> None:
    snapshot = build_rc_release_decision_snapshot(evidence_root=tmp_path)

    assert snapshot.status == "not_available"
    assert snapshot.signoff_status == "missing"
