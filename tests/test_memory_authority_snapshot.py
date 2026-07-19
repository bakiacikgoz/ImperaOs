from imperaos.control_plane.snapshot import build_control_plane_snapshot


def test_control_plane_snapshot_includes_memory_authority() -> None:
    snapshot = build_control_plane_snapshot(profile="balanced")

    assert snapshot.memory_authority.status == "disabled"
    payload = snapshot.model_dump(mode="json", by_alias=True)
    assert payload["memoryAuthority"]["rawContentExposed"] is False
    assert payload["memoryAuthority"]["networkListenerEnabled"] is False
