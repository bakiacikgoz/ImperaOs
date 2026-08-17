from pathlib import Path

import pytest

from imperaos.artifacts.commands import CreateArtifactCommand, PatchArtifactSlideCommand
from imperaos.artifacts.errors import ArtifactDomainError, ArtifactErrorCode
from imperaos.artifacts.models import (
    ArtifactDataClass,
    ArtifactKind,
    ArtifactMutationType,
    OperationContext,
    PrincipalType,
)
from imperaos.artifacts.service import ArtifactService


def _context() -> OperationContext:
    return OperationContext(
        workspace_id="workspace-1",
        principal_type=PrincipalType.USER,
        principal_id="user-1",
        roles=("artifact_editor",),
        request_id="slides-patch-request",
    )


def _slides() -> dict[str, object]:
    return {
        "kind": "slides",
        "schemaVersion": 2,
        "theme": {
            "name": "ImperaOS",
            "backgroundColor": "FFFFFF",
            "foregroundColor": "172033",
            "accentColor": "6E57FF",
        },
        "slides": [{"id": "slide-1", "title": "Before", "elements": []}],
        "assetIds": [],
    }


def test_slide_patch_is_atomic_idempotent_and_records_dedicated_mutation(tmp_path: Path) -> None:
    service = ArtifactService(tmp_path / "artifact-root")
    service.create(
        CreateArtifactCommand(
            artifact_id="slides-1",
            kind=ArtifactKind.SLIDES,
            title="Deck",
            data_class=ArtifactDataClass.INTERNAL,
            content=_slides(),
            idempotency_key="slides-create",
        ),
        _context(),
    )
    command = PatchArtifactSlideCommand.model_validate(
        {
            "artifactId": "slides-1",
            "expectedRevisionNumber": 1,
            "slideId": "slide-1",
            "operations": [
                {"op": "set_title", "title": "After"},
                {
                    "op": "upsert_element",
                    "element": {
                        "id": "text-1",
                        "type": "text",
                        "x": 1,
                        "y": 1,
                        "width": 3,
                        "height": 1,
                        "text": "Governed",
                    },
                },
            ],
            "idempotencyKey": "slides-patch-1",
        }
    )

    result = service.patch_artifact_slide(command, _context())
    replay = service.patch_artifact_slide(command, _context())

    assert result.revision.mutation_type is ArtifactMutationType.SLIDE_PATCH
    assert result.artifact.current_revision_number == 2
    assert replay.disposition == "idempotent_replay"
    loaded = service.store.get_revision("workspace-1", "slides-1", result.revision.revision_id)
    assert b'"title":"After"' in loaded.content
    assert b'"id":"text-1"' in loaded.content


def test_slide_patch_error_before_mutate_records_one_error_observation(
    tmp_path: Path,
) -> None:
    service = ArtifactService(tmp_path / "artifact-root")
    service.create(
        CreateArtifactCommand(
            artifact_id="slides-1",
            kind=ArtifactKind.SLIDES,
            title="Deck",
            data_class=ArtifactDataClass.INTERNAL,
            content=_slides(),
            idempotency_key="slides-create",
        ),
        _context(),
    )
    command = PatchArtifactSlideCommand.model_validate(
        {
            "artifactId": "slides-1",
            "expectedRevisionNumber": 1,
            "slideId": "missing-slide",
            "operations": [{"op": "set_title", "title": "After"}],
            "idempotencyKey": "slides-patch-missing",
        }
    )

    with pytest.raises(ArtifactDomainError) as caught:
        service.patch_artifact_slide(command, _context())

    assert caught.value.code is ArtifactErrorCode.ARTIFACT_SCHEMA_INVALID
    mutation_series = [
        item
        for item in service.operations.series_snapshot()
        if item["name"] == "imperaos_artifact_mutation_total"
        and item["labels"] == {"kind": "slides", "actor": "user", "result": "error"}
    ]
    assert mutation_series == [
        {
            "name": "imperaos_artifact_mutation_total",
            "labels": {"kind": "slides", "actor": "user", "result": "error"},
            "value": 1,
        }
    ]
