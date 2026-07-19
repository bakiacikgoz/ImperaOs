from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from imperaos.artifacts.commands import (
    BeginArtifactExportCommand,
    CreateArtifactCommand,
    GetArtifactAssetQuery,
    ImportArtifactAssetCommand,
    MutateArtifactCommand,
)
from imperaos.artifacts.errors import ArtifactDomainError, ArtifactErrorCode
from imperaos.artifacts.models import (
    ArtifactDataClass,
    ArtifactKind,
    ArtifactMutationType,
    OperationContext,
    PrincipalType,
)
from imperaos.artifacts.service import ArtifactService

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _context(workspace_id: str = "workspace-1") -> OperationContext:
    return OperationContext(
        workspace_id=workspace_id,
        principal_type=PrincipalType.USER,
        principal_id="user-1",
        roles=("artifact_editor",),
        request_id=f"request-{workspace_id}",
    )


def _command(
    *, key: str = "asset-key", payload: bytes = PNG, file_name: str = "image.png"
) -> ImportArtifactAssetCommand:
    return ImportArtifactAssetCommand(
        file_name=file_name,
        declared_media_type="image/png",
        content_base64=base64.b64encode(payload).decode("ascii"),
        data_class=ArtifactDataClass.INTERNAL,
        idempotency_key=key,
    )


def test_asset_import_is_policy_checked_idempotent_and_readable(tmp_path: Path) -> None:
    service = ArtifactService(tmp_path / "artifact-root")

    created = service.import_asset(_command(), _context())
    replay = service.import_asset(_command(), _context())
    read = service.get_asset(GetArtifactAssetQuery(asset_id=created.asset.asset_id), _context())

    assert created.disposition == "created"
    assert replay.disposition == "idempotent_replay"
    assert replay.asset == created.asset
    assert base64.b64decode(read.content_base64) == PNG
    assert read.asset.width == 1
    assert read.asset.height == 1


def test_asset_import_rejects_idempotency_payload_reuse_and_cross_workspace_read(
    tmp_path: Path,
) -> None:
    service = ArtifactService(tmp_path / "artifact-root")
    created = service.import_asset(_command(), _context())

    with pytest.raises(ArtifactDomainError) as reused:
        service.import_asset(_command(payload=PNG + b"x"), _context())
    with pytest.raises(ArtifactDomainError) as cross_workspace:
        service.get_asset(
            GetArtifactAssetQuery(asset_id=created.asset.asset_id),
            _context("workspace-2"),
        )

    assert reused.value.code is ArtifactErrorCode.IDEMPOTENCY_KEY_REUSE_MISMATCH
    assert cross_workspace.value.code is ArtifactErrorCode.ARTIFACT_NOT_FOUND


def test_asset_replay_reservation_rejects_conflict_before_asset_side_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = ArtifactService(tmp_path / "artifact-root")
    service.import_asset(_command(key="racing-key"), _context())
    called = False

    def unexpected_import(*args: object, **kwargs: object) -> object:
        nonlocal called
        del args, kwargs
        called = True
        raise AssertionError("conflicting request reached asset storage")

    monkeypatch.setattr(service.assets, "import_bytes", unexpected_import)

    with pytest.raises(ArtifactDomainError) as raced:
        service.import_asset(
            _command(key="racing-key", file_name="different.png"),
            _context(),
        )

    assert raced.value.code is ArtifactErrorCode.IDEMPOTENCY_KEY_REUSE_MISMATCH
    assert called is False


def test_expired_asset_import_reservation_is_reclaimed(tmp_path: Path) -> None:
    service = ArtifactService(tmp_path / "artifact-root")
    command = _command(key="crashed-import")
    request_hash = service._request_hash(command)
    assert service._reserve_asset_replay("workspace-1", "crashed-import", request_hash) is None
    with service.store._connect() as connection:
        connection.execute(
            """
            UPDATE artifact_operation_dedup SET expires_at_utc = ?
            WHERE workspace_id = ? AND idempotency_key = ?
            """,
            (
                (datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
                "workspace-1",
                "crashed-import",
            ),
        )
        connection.commit()

    imported = service.import_asset(command, _context())

    assert imported.disposition == "created"


def _slides(asset_ids: list[str]) -> dict[str, object]:
    elements = (
        [
            {
                "id": "image-1",
                "type": "image",
                "x": 1,
                "y": 1,
                "width": 2,
                "height": 2,
                "assetId": asset_ids[0],
                "altText": "Governed image",
            }
        ]
        if asset_ids
        else []
    )
    return {
        "kind": "slides",
        "schemaVersion": 2,
        "theme": {
            "name": "ImperaOS",
            "backgroundColor": "FFFFFF",
            "foregroundColor": "172033",
            "accentColor": "6E57FF",
        },
        "slides": [{"id": "slide-1", "elements": elements}],
        "assetIds": asset_ids,
    }


def test_attached_asset_class_promotes_artifact_and_governs_export(tmp_path: Path) -> None:
    service = ArtifactService(tmp_path / "artifact-root")
    context = _context()
    asset = service.import_asset(
        _command(key="regulated-asset").model_copy(
            update={"data_class": ArtifactDataClass.REGULATED}
        ),
        context,
    ).asset
    created_with_asset = service.create(
        CreateArtifactCommand(
            artifact_id="slides-with-asset",
            kind=ArtifactKind.SLIDES,
            title="Governed slides with asset",
            data_class=ArtifactDataClass.PUBLIC,
            content=_slides([asset.asset_id]),
            idempotency_key="slides-create-with-asset",
        ),
        context,
    )
    created = service.create(
        CreateArtifactCommand(
            artifact_id="slides-1",
            kind=ArtifactKind.SLIDES,
            title="Governed slides",
            data_class=ArtifactDataClass.PUBLIC,
            content=_slides([]),
            idempotency_key="slides-create",
        ),
        context,
    )
    mutated = service.mutate(
        MutateArtifactCommand(
            artifact_id=created.artifact.artifact_id,
            expected_revision_number=1,
            mutation_type=ArtifactMutationType.REPLACE_CONTENT,
            content=_slides([asset.asset_id]),
            idempotency_key="slides-attach",
        ),
        context,
    )

    assert created_with_asset.artifact.data_class is ArtifactDataClass.REGULATED
    assert mutated.artifact.data_class is ArtifactDataClass.REGULATED
    with pytest.raises(ArtifactDomainError) as export_denied:
        service.begin_export(
            BeginArtifactExportCommand(
                artifact_id=mutated.artifact.artifact_id,
                revision_id=mutated.revision.revision_id,
                format="pptx",
                idempotency_key="slides-export",
            ),
            context,
        )
    assert export_denied.value.code is ArtifactErrorCode.ARTIFACT_PERMISSION_DENIED
