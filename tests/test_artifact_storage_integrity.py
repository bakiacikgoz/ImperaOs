from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from artifact_store_support import make_artifact_pair

from imperaos.artifacts.errors import ArtifactDomainError, ArtifactErrorCode
from imperaos.artifacts.models import ArtifactStatus
from imperaos.artifacts.store import ArtifactStore


def test_hash_tamper_quarantines_revision_and_marks_artifact_corrupt(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "artifact-root")
    artifact, revision = make_artifact_pair(b"trusted")
    store.create_artifact(artifact, revision, b"trusted")
    path = store.filesystem.resolve_relative(revision.content_relpath)
    path.write_bytes(b"tampered")

    with pytest.raises(ArtifactDomainError) as caught:
        store.get_revision("workspace-1", "artifact-1", "revision-1")

    assert caught.value.code is ArtifactErrorCode.ARTIFACT_HASH_MISMATCH
    assert store.get_artifact("workspace-1", "artifact-1").status is ArtifactStatus.CORRUPT
    assert not path.exists()
    assert any(item.is_file() for item in store.filesystem.quarantine_root.rglob("*"))


def test_crash_after_content_write_is_reconciled_to_quarantine(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = ArtifactStore(tmp_path / "artifact-root")
    artifact, revision = make_artifact_pair(b"orphan")

    def simulate_crash(*args: object, **kwargs: object) -> None:
        raise RuntimeError("simulated process crash")

    monkeypatch.setattr(store, "_commit_create", simulate_crash)
    with pytest.raises(RuntimeError, match="simulated process crash"):
        store.create_artifact(artifact, revision, b"orphan")

    recovered = ArtifactStore(tmp_path / "artifact-root")
    report = recovered.reconcile_storage()

    assert report.pending_journals == 1
    assert report.quarantined_files == 1
    assert not recovered.filesystem.resolve_relative(revision.content_relpath).exists()
    assert any(item.is_file() for item in recovered.filesystem.quarantine_root.rglob("*"))


def test_quarantined_write_retry_rearms_exact_reservation_and_commits_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "artifact-root"
    crashed = ArtifactStore(root)
    artifact, revision = make_artifact_pair(b"retry-after-crash")

    def simulate_crash(*args: object, **kwargs: object) -> None:
        raise RuntimeError("simulated process crash")

    monkeypatch.setattr(crashed, "_commit_create", simulate_crash)
    with pytest.raises(RuntimeError, match="simulated process crash"):
        crashed.create_artifact(artifact, revision, b"retry-after-crash")
    (crashed.filesystem.tmp_root / "stale.tmp").write_bytes(b"stale")

    recovered = ArtifactStore(root)
    report = recovered.reconcile_storage()
    mismatched_payload = b"different-after-crash"
    mismatched_revision = revision.model_copy(
        update={
            "content_sha256": hashlib.sha256(mismatched_payload).hexdigest(),
            "content_size_bytes": len(mismatched_payload),
        }
    )
    with pytest.raises(ArtifactDomainError) as mismatch:
        recovered.create_artifact(artifact, mismatched_revision, mismatched_payload)
    assert mismatch.value.code is ArtifactErrorCode.ARTIFACT_REVISION_CONFLICT
    with recovered._connect() as connection:
        quarantined_state = connection.execute(
            "SELECT state FROM artifact_write_journal WHERE revision_id = ?",
            (revision.revision_id,),
        ).fetchone()[0]
    assert quarantined_state == "quarantined"
    retried = recovered.create_artifact(artifact, revision, b"retry-after-crash")
    replay = recovered.create_artifact(artifact, revision, b"retry-after-crash")

    assert report.pending_journals == 1
    assert report.quarantined_files == 1
    assert report.removed_temp_files == 1
    assert retried.disposition == "created"
    assert replay.disposition == "idempotent_replay"
    assert recovered.get_revision(
        artifact.workspace_id,
        artifact.artifact_id,
        revision.revision_id,
    ).content == b"retry-after-crash"
    with recovered._connect() as connection:
        state = connection.execute(
            "SELECT state FROM artifact_write_journal WHERE revision_id = ?",
            (revision.revision_id,),
        ).fetchone()[0]
    assert state == "committed"
