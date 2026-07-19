from imperaos.control_plane.snapshot import build_control_plane_snapshot


def test_control_plane_snapshot_contains_memory_runtime_and_sync() -> None:
    snapshot = build_control_plane_snapshot(profile="balanced")
    payload = snapshot.model_dump(mode="json", by_alias=True)

    assert payload["memoryRuntime"]["enabled"] is False
    assert payload["memorySync"]["enabled"] is False
