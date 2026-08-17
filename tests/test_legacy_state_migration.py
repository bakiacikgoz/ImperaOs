from pathlib import Path

from imperaos.migration.legacy_state import migrate_legacy_state


def test_legacy_state_copy_is_verified_non_destructive_and_conflict_safe(tmp_path: Path) -> None:
    source = tmp_path / ".binliquid"
    source.mkdir()
    (source / "state.json").write_text('{"ok":true}', encoding="utf-8")
    destination = tmp_path / ".imperaos"
    dry_run = migrate_legacy_state(source, destination)
    assert dry_run["status"] == "dry_run"
    assert not destination.exists()
    copied = migrate_legacy_state(source, destination, copy=True, verify=True)
    assert copied["status"] == "copied"
    assert source.exists()
    assert (destination / "state.json").read_bytes() == (source / "state.json").read_bytes()
    assert (
        migrate_legacy_state(source, destination, copy=True)["reasonCode"]
        == "LEGACY_STATE_DESTINATION_CONFLICT"
    )
