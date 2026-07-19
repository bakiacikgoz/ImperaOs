from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from imperaos.artifacts.commands import ImportEvidenceArtifactCommand
from imperaos.artifacts.errors import ArtifactDomainError, ArtifactErrorCode
from imperaos.artifacts.evidence_import import (
    EvidenceArtifactSource,
    FileArtifactEvidenceResolver,
    InMemoryArtifactEvidenceResolver,
)
from imperaos.artifacts.models import (
    ArtifactDataClass,
    ArtifactKind,
    OperationContext,
    PrincipalType,
    canonical_json,
)
from imperaos.artifacts.service import ArtifactService


def _context(workspace_id: str = "workspace-1") -> OperationContext:
    return OperationContext(
        workspace_id=workspace_id,
        principal_type=PrincipalType.USER,
        principal_id="user-1",
        roles=("artifact_editor",),
        request_id=f"request-{workspace_id}",
    )


def _source() -> EvidenceArtifactSource:
    content = {
        "kind": "document",
        "schemaVersion": 1,
        "language": "en",
        "blocks": [{"id": "block-1", "type": "paragraph", "text": "Verified evidence"}],
    }
    return EvidenceArtifactSource(
        evidence_id="evidence-1",
        workspace_id="workspace-1",
        source_run_id="run-1",
        kind=ArtifactKind.DOCUMENT,
        schema_version=1,
        title="Verified report",
        data_class=ArtifactDataClass.CONFIDENTIAL,
        content=content,
        content_sha256=hashlib.sha256(canonical_json(content).encode()).hexdigest(),
    )


def _command(source: EvidenceArtifactSource, *, expected_sha256: str | None = None):
    return ImportEvidenceArtifactCommand(
        evidence_id=source.evidence_id,
        expected_sha256=expected_sha256 or source.content_sha256,
        title="Editable evidence copy",
        idempotency_key="evidence-copy-1",
    )


def test_evidence_copy_verifies_hash_inherits_classification_and_preserves_source(
    tmp_path: Path,
) -> None:
    source = _source()
    source_snapshot = source.model_dump_json(by_alias=True)
    service = ArtifactService(
        tmp_path / "artifact-root",
        evidence_resolver=InMemoryArtifactEvidenceResolver(source),
    )

    created = service.import_evidence(_command(source), _context())
    replay = service.import_evidence(_command(source), _context())

    assert created.created is True
    assert replay.created is False
    assert replay.disposition == "idempotent_replay"
    assert created.artifact.data_class is ArtifactDataClass.CONFIDENTIAL
    assert created.artifact.created_by_type is PrincipalType.IMPORT
    assert created.revision.mutation_type.value == "import_evidence"
    assert created.revision.content_sha256 == source.content_sha256
    stored = service.store.get_revision(
        "workspace-1", created.artifact.artifact_id, created.revision.revision_id
    )
    assert stored.content == canonical_json(source.content).encode("utf-8")
    assert created.artifact.metadata == {
        "sourceEvidenceId": "evidence-1",
        "sourceEvidenceSha256": source.content_sha256,
        "sourceRunId": "run-1",
    }
    with service.store._connect() as connection:
        link = connection.execute(
            "SELECT link_type, target_id FROM artifact_links WHERE artifact_id = ?",
            (created.artifact.artifact_id,),
        ).fetchone()
    assert dict(link) == {"link_type": "source_evidence", "target_id": "evidence-1"}
    assert source.model_dump_json(by_alias=True) == source_snapshot


def test_file_evidence_resolver_is_workspace_bound_and_receives_actor_context(
    tmp_path: Path,
) -> None:
    source = _source()
    evidence_root = tmp_path / "immutable-evidence"
    workspace_root = evidence_root / source.workspace_id
    workspace_root.mkdir(parents=True)
    (workspace_root / f"{source.evidence_id}.json").write_text(
        json.dumps(source.model_dump(mode="json", by_alias=True)),
        encoding="utf-8",
    )
    resolver = FileArtifactEvidenceResolver(evidence_root)

    loaded = resolver.resolve(_context(), source.evidence_id)

    assert loaded == source
    with pytest.raises(ArtifactDomainError) as cross_workspace:
        resolver.resolve(_context("workspace-2"), source.evidence_id)
    assert cross_workspace.value.code is ArtifactErrorCode.ARTIFACT_NOT_FOUND


def test_evidence_copy_rejects_hash_and_workspace_mismatch_without_artifact(
    tmp_path: Path,
) -> None:
    source = _source()
    service = ArtifactService(
        tmp_path / "artifact-root",
        evidence_resolver=InMemoryArtifactEvidenceResolver(source),
    )

    with pytest.raises(ArtifactDomainError) as wrong_hash:
        service.import_evidence(_command(source, expected_sha256="0" * 64), _context())
    with pytest.raises(ArtifactDomainError) as wrong_workspace:
        service.import_evidence(_command(source), _context("workspace-2"))

    assert wrong_hash.value.code is ArtifactErrorCode.ARTIFACT_STORAGE_CORRUPT
    assert wrong_workspace.value.code is ArtifactErrorCode.ARTIFACT_NOT_FOUND
    with service.store._connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0] == 0


def test_assistant_cannot_bypass_proposal_boundary_with_evidence_import(
    tmp_path: Path,
) -> None:
    source = _source()
    service = ArtifactService(
        tmp_path / "artifact-root",
        evidence_resolver=InMemoryArtifactEvidenceResolver(source),
    )
    assistant = OperationContext(
        workspace_id="workspace-1",
        principal_type=PrincipalType.ASSISTANT,
        principal_id="assistant-1",
        roles=("artifact_editor",),
        request_id="request-assistant",
    )

    with pytest.raises(ArtifactDomainError) as caught:
        service.import_evidence(_command(source), assistant)

    assert caught.value.code is ArtifactErrorCode.ARTIFACT_PERMISSION_DENIED
    with service.store._connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0] == 0
