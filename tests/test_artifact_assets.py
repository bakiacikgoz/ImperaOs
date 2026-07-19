from __future__ import annotations

import base64
from pathlib import Path

import pytest

from imperaos.artifacts.assets import ArtifactAssetStore
from imperaos.artifacts.errors import ArtifactDomainError, ArtifactErrorCode
from imperaos.artifacts.models import ArtifactDataClass

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)
JPEG = b"\xff\xd8\xff\xe0" + b"j" * 16
GIF = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==")


def test_assets_validate_magic_store_by_hash_and_deduplicate_per_workspace(
    tmp_path: Path,
) -> None:
    store = ArtifactAssetStore(tmp_path / "artifact-root")

    first = store.import_bytes(
        "workspace-1",
        PNG,
        declared_media_type="image/png",
        original_name="görsel.png",
        data_class=ArtifactDataClass.INTERNAL,
        created_by_id="user-1",
    )
    duplicate = store.import_bytes(
        "workspace-1",
        PNG,
        declared_media_type="image/png",
        original_name="copy.png",
        data_class=ArtifactDataClass.INTERNAL,
        created_by_id="user-1",
    )

    assert first.deduplicated is False
    assert duplicate.deduplicated is True
    assert duplicate.descriptor == first.descriptor
    assert first.descriptor.relative_path.startswith("assets/workspace-1/sha256/")
    assert store.get_bytes("workspace-1", first.descriptor.asset_id) == PNG
    assert store.workspace_usage_bytes("workspace-1") == len(PNG)


def test_asset_dedup_promotes_classification_and_never_downgrades(tmp_path: Path) -> None:
    store = ArtifactAssetStore(tmp_path / "artifact-root")
    first = store.import_bytes(
        "workspace-1",
        PNG,
        declared_media_type="image/png",
        data_class=ArtifactDataClass.INTERNAL,
        created_by_id="user-1",
    )
    promoted = store.import_bytes(
        "workspace-1",
        PNG,
        declared_media_type="image/png",
        data_class=ArtifactDataClass.CONFIDENTIAL,
        created_by_id="user-2",
    )
    lower_request = store.import_bytes(
        "workspace-1",
        PNG,
        declared_media_type="image/png",
        data_class=ArtifactDataClass.PUBLIC,
        created_by_id="user-3",
    )

    assert promoted.descriptor.asset_id == first.descriptor.asset_id
    assert promoted.descriptor.data_class is ArtifactDataClass.CONFIDENTIAL
    assert lower_request.descriptor.data_class is ArtifactDataClass.CONFIDENTIAL
    assert store.get_descriptor(
        "workspace-1",
        first.descriptor.asset_id,
    ).data_class is ArtifactDataClass.CONFIDENTIAL


def test_assets_reject_declared_mime_mismatch_and_unknown_magic(tmp_path: Path) -> None:
    store = ArtifactAssetStore(tmp_path / "artifact-root")

    with pytest.raises(ArtifactDomainError) as mismatch:
        store.import_bytes(
            "workspace-1",
            JPEG,
            declared_media_type="image/png",
            data_class=ArtifactDataClass.INTERNAL,
            created_by_id="user-1",
        )
    with pytest.raises(ArtifactDomainError) as unknown:
        store.import_bytes(
            "workspace-1",
            b"not-an-allowlisted-asset",
            declared_media_type="application/octet-stream",
            data_class=ArtifactDataClass.INTERNAL,
            created_by_id="user-1",
        )

    assert mismatch.value.code is ArtifactErrorCode.ARTIFACT_ASSET_TYPE_UNSUPPORTED
    assert unknown.value.code is ArtifactErrorCode.ARTIFACT_ASSET_TYPE_UNSUPPORTED


@pytest.mark.parametrize(
    "payload",
    [
        b"\x89PNG\r\n\x1a\n" + b"not-a-real-png",
        PNG[:-8],
        PNG + b"<script>polyglot</script>",
    ],
)
def test_assets_reject_truncated_and_polyglot_images(
    tmp_path: Path,
    payload: bytes,
) -> None:
    store = ArtifactAssetStore(tmp_path / "artifact-root")

    with pytest.raises(ArtifactDomainError) as caught:
        store.import_bytes(
            "workspace-1",
            payload,
            declared_media_type="image/png",
            data_class=ArtifactDataClass.INTERNAL,
            created_by_id="user-1",
        )

    assert caught.value.code is ArtifactErrorCode.ARTIFACT_ASSET_TYPE_UNSUPPORTED
    assert caught.value.details == {"classification": "image_structure_invalid"}


def test_workspace_asset_quota_cannot_exceed_the_governed_hard_cap(tmp_path: Path) -> None:
    store = ArtifactAssetStore(
        tmp_path / "artifact-root",
        workspace_quota_bytes=4 * 1024 * 1024 * 1024,
    )

    assert store.workspace_quota_bytes == 2 * 1024 * 1024 * 1024


def test_assets_enforce_individual_and_workspace_quotas(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = ArtifactAssetStore(
        tmp_path / "artifact-root",
        max_asset_bytes=100,
        workspace_quota_bytes=len(PNG) + len(GIF) - 1,
    )
    store.import_bytes(
        "workspace-1",
        PNG,
        declared_media_type="image/png",
        data_class=ArtifactDataClass.INTERNAL,
        created_by_id="user-1",
    )
    monkeypatch.setattr(store, "workspace_usage_bytes", lambda _workspace_id: 0)

    with pytest.raises(ArtifactDomainError) as workspace_quota:
        store.import_bytes(
            "workspace-1",
            GIF,
            declared_media_type="image/gif",
            data_class=ArtifactDataClass.INTERNAL,
            created_by_id="user-1",
        )
    with pytest.raises(ArtifactDomainError) as item_limit:
        store.import_bytes(
            "workspace-2",
            PNG + b"x" * 40,
            declared_media_type="image/png",
            data_class=ArtifactDataClass.INTERNAL,
            created_by_id="user-1",
        )

    assert workspace_quota.value.code is ArtifactErrorCode.ARTIFACT_QUOTA_EXCEEDED
    assert item_limit.value.code is ArtifactErrorCode.ARTIFACT_CONTENT_TOO_LARGE
    assert sum(1 for item in store.filesystem.assets_root.rglob("*") if item.is_file()) == 1


def test_asset_lookup_is_workspace_scoped(tmp_path: Path) -> None:
    store = ArtifactAssetStore(tmp_path / "artifact-root")
    imported = store.import_bytes(
        "workspace-1",
        PNG,
        declared_media_type="image/png",
        data_class=ArtifactDataClass.INTERNAL,
        created_by_id="user-1",
    )

    with pytest.raises(ArtifactDomainError) as caught:
        store.get_bytes("workspace-2", imported.descriptor.asset_id)

    assert caught.value.code is ArtifactErrorCode.ARTIFACT_NOT_FOUND


def test_svg_is_quarantined_and_remote_fetch_is_fail_closed(tmp_path: Path) -> None:
    store = ArtifactAssetStore(tmp_path / "artifact-root")
    unsafe_svg = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'

    with pytest.raises(ArtifactDomainError) as svg_error:
        store.import_bytes(
            "workspace-1",
            unsafe_svg,
            declared_media_type="image/svg+xml",
            data_class=ArtifactDataClass.INTERNAL,
            created_by_id="user-1",
        )
    with pytest.raises(ArtifactDomainError) as remote_error:
        store.import_remote_url("workspace-1", "https://example.invalid/image.png")

    assert svg_error.value.code is ArtifactErrorCode.ARTIFACT_ASSET_UNSAFE
    assert remote_error.value.code is ArtifactErrorCode.ARTIFACT_ASSET_UNSAFE
    assert any(item.is_file() for item in store.filesystem.quarantine_root.rglob("*"))
    assert store.workspace_usage_bytes("workspace-1") == 0
