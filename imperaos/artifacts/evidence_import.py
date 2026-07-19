from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Protocol

from pydantic import Field, JsonValue, model_validator

from imperaos.artifacts.errors import ArtifactDomainError, ArtifactErrorCode
from imperaos.artifacts.models import (
    ArtifactDataClass,
    ArtifactKind,
    ArtifactModel,
    BoundedId,
    OperationContext,
    Sha256,
    canonical_json,
)


class EvidenceArtifactSource(ArtifactModel):
    evidence_id: BoundedId
    workspace_id: BoundedId
    source_run_id: BoundedId | None = None
    kind: ArtifactKind = Field(strict=False)
    schema_version: int = Field(ge=1, le=1000)
    title: str = Field(min_length=1, max_length=200)
    data_class: ArtifactDataClass = Field(strict=False)
    content: dict[str, JsonValue]
    content_sha256: Sha256

    @model_validator(mode="after")
    def verify_content_hash(self) -> EvidenceArtifactSource:
        observed = hashlib.sha256(canonical_json(self.content).encode("utf-8")).hexdigest()
        if observed != self.content_sha256:
            raise ValueError("evidence source content hash mismatch")
        return self


class ArtifactEvidenceResolver(Protocol):
    def resolve(
        self, context: OperationContext, evidence_id: str
    ) -> EvidenceArtifactSource: ...


class DenyArtifactEvidenceResolver:
    def resolve(
        self, context: OperationContext, evidence_id: str
    ) -> EvidenceArtifactSource:
        del context, evidence_id
        raise ArtifactDomainError(
            ArtifactErrorCode.ARTIFACT_NOT_FOUND,
            "verified evidence source does not exist",
        )


class InMemoryArtifactEvidenceResolver:
    """Test/integration authority that returns defensive copies of verified sources."""

    def __init__(self, *sources: EvidenceArtifactSource) -> None:
        self._sources = {
            (source.workspace_id, source.evidence_id): canonical_json(source)
            for source in sources
        }

    def resolve(
        self, context: OperationContext, evidence_id: str
    ) -> EvidenceArtifactSource:
        payload = self._sources.get((context.workspace_id, evidence_id))
        if payload is None:
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_NOT_FOUND,
                "verified evidence source does not exist",
            )
        return EvidenceArtifactSource.model_validate(json.loads(payload))


class FileArtifactEvidenceResolver:
    """Read immutable, workspace-scoped evidence manifests without exposing paths."""

    _MAX_MANIFEST_BYTES = 25 * 1024 * 1024

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()

    def resolve(
        self, context: OperationContext, evidence_id: str
    ) -> EvidenceArtifactSource:
        candidate = self.root / context.workspace_id / f"{evidence_id}.json"
        probe = candidate
        while probe != self.root:
            if probe.is_symlink():
                raise ArtifactDomainError(
                    ArtifactErrorCode.ARTIFACT_PERMISSION_DENIED,
                    "evidence source path is not trusted",
                )
            probe = probe.parent
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(self.root)
        except (FileNotFoundError, OSError, ValueError) as exc:
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_NOT_FOUND,
                "verified evidence source does not exist",
            ) from exc
        try:
            flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            descriptor = os.open(resolved, flags)
            with os.fdopen(descriptor, "rb") as stream:
                stat = os.fstat(descriptor)
                if stat.st_size > self._MAX_MANIFEST_BYTES:
                    raise ArtifactDomainError(
                        ArtifactErrorCode.ARTIFACT_PAYLOAD_TOO_LARGE,
                        "evidence source exceeds the bounded manifest size",
                    )
                payload = stream.read(self._MAX_MANIFEST_BYTES + 1)
            source = EvidenceArtifactSource.model_validate_json(payload)
        except ArtifactDomainError:
            raise
        except (OSError, ValueError) as exc:
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_STORAGE_CORRUPT,
                "verified evidence source is invalid",
            ) from exc
        if source.workspace_id != context.workspace_id or source.evidence_id != evidence_id:
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_NOT_FOUND,
                "evidence source does not exist",
            )
        return source
