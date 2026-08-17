from imperaos.control_plane.snapshot import build_control_plane_snapshot


def test_control_plane_snapshot_contains_memory_semantic_index() -> None:
    snapshot = build_control_plane_snapshot(profile="balanced")
    payload = snapshot.model_dump(mode="json", by_alias=True)

    assert payload["memorySemanticIndex"]["enabled"] is False
    assert payload["memorySemanticIndex"]["rawPersistence"] is False
