from __future__ import annotations

from pathlib import Path

from imperaos.control_plane.snapshot import build_control_plane_snapshot


def test_control_plane_snapshot_includes_enterprise_workspace_surface(tmp_path: Path) -> None:
    snapshot = build_control_plane_snapshot(
        root_dir=tmp_path / "cp",
        evidence_root=tmp_path / "artifacts",
        profile="lite",
    )
    payload = snapshot.model_dump(mode="json", by_alias=True)

    assert "enterpriseWorkspace" in payload
    assert payload["enterpriseWorkspace"]["rawSecretsExposed"] is False
    assert payload["enterpriseWorkspace"]["networkListenerEnabled"] is False
    assert payload["enterpriseWorkspace"]["status"] in {"setup_required", "disabled"}
