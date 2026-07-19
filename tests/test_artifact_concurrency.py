from __future__ import annotations

from pathlib import Path

import pytest
from artifact_store_support import make_artifact_pair

from imperaos.artifacts.errors import ArtifactDomainError, ArtifactErrorCode
from imperaos.artifacts.store import ArtifactStore


def test_store_replays_same_idempotency_key_and_rejects_payload_mismatch(
    tmp_path: Path,
) -> None:
    store = ArtifactStore(tmp_path / "artifact-root")
    artifact_v1, revision_v1 = make_artifact_pair(b"one")
    store.create_artifact(artifact_v1, revision_v1, b"one")
    artifact_v2, revision_v2 = make_artifact_pair(
        b"two",
        revision_number=2,
        parent_revision_id="revision-1",
        idempotency_key="retry-key",
    )
    first = store.append_revision(
        artifact_v2,
        revision_v2,
        b"two",
        expected_revision_number=1,
    )
    replay = store.append_revision(
        artifact_v2,
        revision_v2,
        b"two",
        expected_revision_number=1,
    )
    _, conflicting_revision = make_artifact_pair(
        b"different",
        revision_number=3,
        revision_id="revision-conflict",
        parent_revision_id="revision-2",
        idempotency_key="retry-key",
    )

    with pytest.raises(ArtifactDomainError) as caught:
        store.append_revision(
            artifact_v2,
            conflicting_revision,
            b"different",
            expected_revision_number=2,
        )

    assert first.created is True
    assert replay.created is False
    assert replay.disposition == "idempotent_replay"
    assert caught.value.code is ArtifactErrorCode.IDEMPOTENCY_KEY_REUSE_MISMATCH


def test_store_rejects_stale_expected_revision_without_writing_file(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "artifact-root")
    artifact_v1, revision_v1 = make_artifact_pair(b"one")
    store.create_artifact(artifact_v1, revision_v1, b"one")
    artifact_v2, revision_v2 = make_artifact_pair(
        b"two",
        revision_number=2,
        parent_revision_id="revision-1",
    )

    with pytest.raises(ArtifactDomainError) as caught:
        store.append_revision(
            artifact_v2,
            revision_v2,
            b"two",
            expected_revision_number=7,
        )

    assert caught.value.code is ArtifactErrorCode.ARTIFACT_REVISION_CONFLICT
    assert not store.filesystem.resolve_relative(revision_v2.content_relpath).exists()
