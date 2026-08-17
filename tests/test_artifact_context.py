from __future__ import annotations

from types import SimpleNamespace

import pytest

from imperaos.artifacts.content import CodeContentV2, DocumentContentV1, FormContentV1
from imperaos.artifacts.context import (
    ArtifactContextPurpose,
    ArtifactContextRequest,
    CodeArtifactSelection,
    DocumentArtifactSelection,
    build_artifact_context_pack,
    get_artifact_context,
)
from imperaos.artifacts.errors import ArtifactDomainError, ArtifactErrorCode
from imperaos.artifacts.models import (
    ArtifactDataClass,
    ArtifactKind,
    OperationContext,
    PrincipalType,
)


def _read_result(content: object, *, kind: ArtifactKind) -> SimpleNamespace:
    return SimpleNamespace(
        artifact=SimpleNamespace(
            artifact_id="artifact-1",
            workspace_id="workspace-1",
            kind=kind,
            title="Context fixture",
            status=SimpleNamespace(value="active"),
            schema_version=content.schema_version,
            data_class=ArtifactDataClass.CONFIDENTIAL,
        ),
        revision=SimpleNamespace(
            revision_id="revision-1",
            revision_number=1,
            content_sha256="a" * 64,
        ),
        content=content,
    )


def test_context_without_selection_is_metadata_only() -> None:
    result = _read_result(
        DocumentContentV1(
            language="en",
            blocks=[{"id": "block-1", "type": "paragraph", "content": "private text"}],
        ),
        kind=ArtifactKind.DOCUMENT,
    )

    pack = build_artifact_context_pack(
        result,
        ArtifactContextRequest(
            artifact_id="artifact-1",
            revision_id="revision-1",
            purpose=ArtifactContextPurpose.EXPLAIN,
        ),
    )

    assert pack.selection is None
    assert pack.revision_number == 1
    assert pack.projection == {
        "dataClass": "confidential",
        "kind": "document",
        "schemaVersion": 1,
        "status": "active",
        "title": "Context fixture",
    }
    assert "private text" not in pack.canonical_projection
    assert pack.projection_size_bytes <= 32 * 1024
    assert pack.estimated_tokens <= 8_192


def test_document_context_projects_only_selected_blocks() -> None:
    result = _read_result(
        DocumentContentV1(
            language="en",
            blocks=[
                {"id": "block-1", "type": "paragraph", "content": "include"},
                {"id": "block-2", "type": "paragraph", "content": "exclude"},
            ],
        ),
        kind=ArtifactKind.DOCUMENT,
    )

    pack = build_artifact_context_pack(
        result,
        ArtifactContextRequest(
            artifact_id="artifact-1",
            revision_id="revision-1",
            purpose="summarize",
            selection=DocumentArtifactSelection(block_ids=("block-1",)),
        ),
    )

    assert pack.projection == {
        "blocks": [{"content": "include", "id": "block-1", "type": "paragraph"}],
        "language": "en",
    }
    assert "exclude" not in pack.canonical_projection


def test_form_context_projects_and_merges_only_nested_selected_fields() -> None:
    result = _read_result(
        FormContentV1(
            json_schema={
                "type": "object",
                "properties": {
                    "profile": {
                        "type": "object",
                        "title": "Profile",
                        "properties": {
                            "name": {"type": "string", "title": "Name"},
                            "email": {"type": "string", "format": "email"},
                            "fixed": {"type": "string", "default": "exclude"},
                        },
                        "required": ["name", "email", "fixed"],
                        "additionalProperties": False,
                    },
                    "outside": {"type": "string", "default": "exclude"},
                },
                "additionalProperties": False,
            }
        ),
        kind=ArtifactKind.FORM,
    )

    pack = build_artifact_context_pack(
        result,
        ArtifactContextRequest.model_validate(
            {
                "artifactId": "artifact-1",
                "revisionId": "revision-1",
                "purpose": "edit",
                "selection": {
                    "kind": "form",
                    "fieldPaths": ["/profile/name", "/profile/email"],
                },
            }
        ),
    )

    assert pack.projection == {
        "fields": {
            "profile": {
                "type": "object",
                "title": "Profile",
                "properties": {
                    "name": {"type": "string", "title": "Name"},
                    "email": {"type": "string", "format": "email"},
                },
                "required": ["name", "email"],
                "additionalProperties": False,
            }
        }
    }
    assert "fixed" not in pack.canonical_projection
    assert "outside" not in pack.canonical_projection


@pytest.mark.parametrize("field_path", ("/profile/missing", "/outside/name"))
def test_form_context_rejects_unknown_or_non_object_nested_paths(field_path: str) -> None:
    result = _read_result(
        FormContentV1(
            json_schema={
                "type": "object",
                "properties": {
                    "profile": {
                        "type": "object",
                        "properties": {"name": {"type": "string"}},
                    },
                    "outside": {"type": "string"},
                },
            }
        ),
        kind=ArtifactKind.FORM,
    )

    with pytest.raises(ArtifactDomainError) as caught:
        build_artifact_context_pack(
            result,
            ArtifactContextRequest.model_validate(
                {
                    "artifactId": "artifact-1",
                    "revisionId": "revision-1",
                    "purpose": "edit",
                    "selection": {"kind": "form", "fieldPaths": [field_path]},
                }
            ),
        )

    assert caught.value.code is ArtifactErrorCode.ARTIFACT_SCHEMA_INVALID


@pytest.mark.parametrize(
    "secret, fragment",
    (
        ("ghp_abcdefghijklmnopqrstuvwxyz1234567890", "ghp_"),
        ("eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signature123456", "eyJhbGci"),
        ("-----BEGIN PRIVATE KEY-----\nabc123\n-----END PRIVATE KEY-----", "PRIVATE KEY"),
        ("AKIAABCDEFGHIJKLMNOP", "AKIA"),
        ("https://service-user:service-password@example.com/private", "service-password"),
    ),
)
def test_selected_context_redacts_common_credential_families(
    secret: str,
    fragment: str,
) -> None:
    result = _read_result(
        DocumentContentV1.model_construct(
            kind="document",
            schema_version=1,
            language="en",
            page_mode="document",
            blocks=[{"id": "block-1", "type": "paragraph", "content": secret}],
        ),
        kind=ArtifactKind.DOCUMENT,
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

    assert pack.redaction_count >= 1
    assert "[REDACTED]" in pack.canonical_projection
    assert fragment not in pack.canonical_projection


def test_selected_context_redacts_structured_aws_secret_key() -> None:
    result = _read_result(
        DocumentContentV1(
            language="en",
            blocks=[
                {
                    "id": "block-1",
                    "type": "paragraph",
                    "aws_secret_access_key": "very-secret-value",
                }
            ],
        ),
        kind=ArtifactKind.DOCUMENT,
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
    assert "very-secret-value" not in pack.canonical_projection
    assert pack.redaction_count >= 1


def test_code_context_is_coordinate_bounded_and_truncates_to_budget() -> None:
    content = CodeContentV2(
        filename="main.py",
        language="python",
        text=("x" * 1_000 + "\n") * 80,
    )
    pack = build_artifact_context_pack(
        _read_result(content, kind=ArtifactKind.CODE),
        ArtifactContextRequest(
            artifact_id="artifact-1",
            revision_id="revision-1",
            purpose="transform",
            selection=CodeArtifactSelection(
                start_line_number=1,
                start_column=1,
                end_line_number=80,
                end_column=1_001,
            ),
        ),
    )

    assert pack.truncated is True
    assert pack.projection_size_bytes <= 32 * 1024
    assert pack.estimated_tokens <= 8_192
    assert pack.projection["filename"] == "main.py"
    assert len(pack.projection["text"]) < len(content.text)


def test_context_rejects_selection_for_a_different_artifact_kind() -> None:
    result = _read_result(
        DocumentContentV1(language="en", blocks=[]),
        kind=ArtifactKind.DOCUMENT,
    )

    with pytest.raises(ArtifactDomainError) as caught:
        build_artifact_context_pack(
            result,
            ArtifactContextRequest(
                artifact_id="artifact-1",
                revision_id="revision-1",
                purpose="edit",
                selection=CodeArtifactSelection(
                    start_line_number=1,
                    start_column=1,
                    end_line_number=1,
                    end_column=1,
                ),
            ),
        )

    assert caught.value.code is ArtifactErrorCode.ARTIFACT_SCHEMA_INVALID


def test_context_is_loaded_through_the_policy_authorized_service_read() -> None:
    result = _read_result(
        DocumentContentV1(language="en", blocks=[]),
        kind=ArtifactKind.DOCUMENT,
    )
    calls: list[tuple[object, object]] = []

    class Service:
        def get(self, query: object, context: object) -> object:
            calls.append((query, context))
            return result

    operation_context = OperationContext(
        workspace_id="workspace-1",
        principal_type=PrincipalType.USER,
        principal_id="user-1",
        roles=("artifact_viewer",),
        request_id="request-1",
    )
    request = ArtifactContextRequest(
        artifact_id="artifact-1",
        revision_id="revision-1",
        purpose="explain",
    )

    pack = get_artifact_context(Service(), request, operation_context)

    assert pack.artifact_id == "artifact-1"
    assert len(calls) == 1
    query, observed_context = calls[0]
    assert query.artifact_id == "artifact-1"
    assert query.revision_id == "revision-1"
    assert observed_context is operation_context
