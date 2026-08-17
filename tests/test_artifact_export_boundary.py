from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TAURI_ROOT = REPO_ROOT / "apps/operator-panel/src-tauri"
BRIDGE = TAURI_ROOT / "src/bridge.rs"
BOUNDARY = TAURI_ROOT / "src/artifact_export.rs"
LIB = TAURI_ROOT / "src/lib.rs"
CAPABILITY = TAURI_ROOT / "capabilities/default.json"


def _rust_struct(source: str, name: str) -> str:
    return source.split(f"pub struct {name}", 1)[1].split("}", 1)[0]


def test_renderer_never_supplies_or_receives_an_export_path() -> None:
    bridge = BRIDGE.read_text(encoding="utf-8")
    boundary = BOUNDARY.read_text(encoding="utf-8")

    for name in (
        "ArtifactExportBeginRequest",
        "ArtifactExportBeginResult",
        "ArtifactExportCommitRequest",
        "ArtifactExportCancelRequest",
    ):
        assert "path" not in _rust_struct(bridge, name).lower()
    assert "path" not in _rust_struct(boundary, "IssuedExportTicket").lower()
    assert ".blocking_save_file()" in bridge
    assert "selection.into_path()" in bridge


def test_export_boundary_is_registered_with_minimum_native_capability() -> None:
    lib = LIB.read_text(encoding="utf-8")
    capability = CAPABILITY.read_text(encoding="utf-8")

    assert ".manage(artifact_export::ArtifactExportState::new(" in lib
    assert "bridge::artifact_export_journal_root()" in lib
    assert ".plugin(tauri_plugin_dialog::init())" in lib
    assert '"dialog:allow-save"' in capability


def test_ticket_boundary_is_bounded_bound_single_use_and_atomic() -> None:
    boundary = BOUNDARY.read_text(encoding="utf-8")

    assert "DEFAULT_MAX_EXPORT_BYTES" in boundary
    assert "MAX_TICKET_TTL" in boundary
    assert "record.binding.same_actor(binding)" in boundary
    assert "pub async fn binding_for_ticket" in boundary
    assert ".remove(ticket)" in boundary
    assert "create_new(true)" in boundary
    assert "temp.sync_all()" in boundary
    assert "MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH" in boundary
    assert "Sha256::digest(&bytes)" in boundary
