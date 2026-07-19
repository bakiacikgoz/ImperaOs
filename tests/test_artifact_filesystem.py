from __future__ import annotations

import errno
import hashlib
from pathlib import Path

import pytest

from imperaos.artifacts.errors import ArtifactDomainError, ArtifactErrorCode
from imperaos.artifacts.filesystem import GuardedArtifactFilesystem


def test_filesystem_scaffolds_layout_and_normalizes_unicode_paths(tmp_path: Path) -> None:
    storage = GuardedArtifactFilesystem(tmp_path / "artifact-root")
    payload = "güvenli içerik".encode()

    stored = storage.atomic_write_bytes(
        "content/workspace/artifact/revisions/cafe\u0301.json",
        payload,
    )

    assert {path.name for path in storage.root.iterdir()} == {
        "assets",
        "backups",
        "content",
        "metadata",
        "quarantine",
        "tmp",
    }
    assert stored.relative_path == "content/workspace/artifact/revisions/café.json"
    assert stored.sha256 == hashlib.sha256(payload).hexdigest()
    assert storage.read_bytes(stored.relative_path, expected_sha256=stored.sha256) == payload
    assert not list(storage.tmp_root.iterdir())


@pytest.mark.parametrize(
    "relative_path",
    [
        "../escape.json",
        "/absolute.json",
        "C:\\absolute.json",
        "content//empty.json",
        "content/./dot.json",
        "content/../escape.json",
        "content/unsafe\x00.json",
    ],
)
def test_filesystem_rejects_non_relative_or_ambiguous_paths(
    tmp_path: Path,
    relative_path: str,
) -> None:
    storage = GuardedArtifactFilesystem(tmp_path / "artifact-root")

    with pytest.raises(ArtifactDomainError) as caught:
        storage.resolve_relative(relative_path)

    assert caught.value.code is ArtifactErrorCode.ARTIFACT_WORKSPACE_MISMATCH


def test_filesystem_blocks_symlink_escape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = GuardedArtifactFilesystem(tmp_path / "artifact-root")
    outside = tmp_path / "outside"
    outside.mkdir()
    link = storage.content_root / "escape"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        escaped_candidate = link / "revision.json"
        real_resolve = Path.resolve

        def resolve_as_escaped(path: Path, *args: object, **kwargs: object) -> Path:
            if path == escaped_candidate:
                return outside / "revision.json"
            return real_resolve(path, *args, **kwargs)

        monkeypatch.setattr(Path, "resolve", resolve_as_escaped)

    with pytest.raises(ArtifactDomainError) as caught:
        storage.resolve_relative("content/escape/revision.json")

    assert caught.value.code is ArtifactErrorCode.ARTIFACT_WORKSPACE_MISMATCH
    assert not (outside / "revision.json").exists()


def test_hash_mismatch_is_quarantined_without_publishing_target(tmp_path: Path) -> None:
    storage = GuardedArtifactFilesystem(tmp_path / "artifact-root")

    with pytest.raises(ArtifactDomainError) as caught:
        storage.atomic_write_bytes(
            "content/workspace/artifact/revisions/0001.json",
            b"actual",
            expected_sha256="0" * 64,
        )

    assert caught.value.code is ArtifactErrorCode.ARTIFACT_HASH_MISMATCH
    assert not storage.resolve_relative(
        "content/workspace/artifact/revisions/0001.json"
    ).exists()
    quarantined = list(storage.quarantine_root.rglob("*"))
    assert any(path.is_file() for path in quarantined)
    assert not list(storage.tmp_root.iterdir())


def test_disk_full_is_classified_and_temp_file_is_cleaned(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = GuardedArtifactFilesystem(tmp_path / "artifact-root")
    real_open = Path.open

    def raise_disk_full(path: Path, *args: object, **kwargs: object):
        if path.parent == storage.tmp_root:
            raise OSError(errno.ENOSPC, "simulated disk full")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", raise_disk_full)

    with pytest.raises(ArtifactDomainError) as caught:
        storage.atomic_write_bytes(
            "content/workspace/artifact/revisions/0001.json",
            b"payload",
        )

    assert caught.value.code is ArtifactErrorCode.ARTIFACT_QUOTA_EXCEEDED
    assert caught.value.details["classification"] == "disk_full"
    assert not storage.resolve_relative(
        "content/workspace/artifact/revisions/0001.json"
    ).exists()
    assert not list(storage.tmp_root.iterdir())
