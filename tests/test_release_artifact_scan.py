from __future__ import annotations

from pathlib import Path

from imperaos.control_plane.release_artifact_scan import scan_release_artifacts


def test_release_artifact_scan_blocks_secret_marker(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    root.mkdir()
    (root / "unsafe.json").write_text('{"token":"sk-test-secret"}\n', encoding="utf-8")

    report = scan_release_artifacts(artifact_root=root)

    assert report.status == "blocked"
    assert report.secret_marker_count == 1
    assert "RAW_OR_SECRET_MARKER_FOUND" in report.blockers
    assert "sk-test-secret" not in report.model_dump_json()


def test_release_artifact_scan_rejects_path_traversal(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    root.mkdir()

    report = scan_release_artifacts(artifact_root=root, include_paths=["../outside.json"])

    assert report.status == "blocked"
    assert "ARTIFACT_PATH_OUTSIDE_ROOT:../outside.json" in report.blockers


def test_release_artifact_scan_allows_hash_only_raw_false_fields(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    root.mkdir()
    (root / "provider.json").write_text(
        '{"rawPersistence":false,"rawPromptPersisted":false,"tokenCount":0}\n',
        encoding="utf-8",
    )

    report = scan_release_artifacts(artifact_root=root)

    assert report.status == "pass"


def test_release_artifact_scan_blocks_raw_true_fields(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    root.mkdir()
    (root / "unsafe.json").write_text('{"rawPromptPersisted":true}\n', encoding="utf-8")

    report = scan_release_artifacts(artifact_root=root)

    assert report.status == "blocked"
    assert report.raw_marker_count == 1


def test_release_artifact_scan_hashes_safe_files(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    root.mkdir()
    (root / "gate_result.json").write_text('{"status":"pass"}\n', encoding="utf-8")

    report = scan_release_artifacts(artifact_root=root)

    assert report.status == "pass"
    assert report.scanned_file_count == 1
    assert report.items[0].sha256.startswith("sha256:")
