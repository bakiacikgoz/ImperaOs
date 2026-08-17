from __future__ import annotations

from types import SimpleNamespace

from imperaos.artifacts.content import DocumentContentV1
from imperaos.artifacts.context import (
    ArtifactContextRequest,
    DocumentArtifactSelection,
    build_artifact_context_pack,
)
from imperaos.artifacts.models import ArtifactDataClass, ArtifactKind


def test_context_pack_redacts_secret_shaped_keys_and_values() -> None:
    content = DocumentContentV1(
        language="en",
        blocks=[
            {
                "id": "block-1",
                "type": "paragraph",
                "apiKey": "sk-live-not-for-context",
                "content": "Authorization: Bearer opaque-secret-value",
            }
        ],
    )
    result = SimpleNamespace(
        artifact=SimpleNamespace(
            artifact_id="artifact-1",
            workspace_id="workspace-1",
            kind=ArtifactKind.DOCUMENT,
            title="Secrets",
            status=SimpleNamespace(value="active"),
            schema_version=1,
            data_class=ArtifactDataClass.REGULATED,
        ),
        revision=SimpleNamespace(
            revision_id="revision-1",
            revision_number=1,
            content_sha256="b" * 64,
        ),
        content=content,
    )

    pack = build_artifact_context_pack(
        result,
        ArtifactContextRequest(
            artifact_id="artifact-1",
            revision_id="revision-1",
            purpose="explain",
            selection=DocumentArtifactSelection(block_ids=("block-1",)),
        ),
    )

    assert pack.redaction_count == 2
    assert "sk-live" not in pack.canonical_projection
    assert "opaque-secret-value" not in pack.canonical_projection
    assert pack.projection["blocks"][0]["apiKey"] == "[REDACTED]"
    assert pack.projection["blocks"][0]["content"] == "[REDACTED]"
