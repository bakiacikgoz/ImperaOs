from pathlib import Path

from imperaos.control_plane.snapshot import build_control_plane_snapshot


def test_control_plane_snapshot_includes_memory_governance(tmp_path: Path) -> None:
    snapshot = build_control_plane_snapshot(
        root_dir=tmp_path / "control-plane",
        evidence_root=tmp_path / "artifacts",
        profile="balanced",
    )
    payload = snapshot.model_dump(mode="json", by_alias=True)

    assert payload["memoryGovernance"]["contractVersion"] == "memory.authority-snapshot/v1"
    assert payload["memoryGovernance"]["enabled"] is False
    assert payload["memoryGovernance"]["privacy"]["rawPromptPersistence"] is False
