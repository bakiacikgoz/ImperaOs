from __future__ import annotations

import hashlib
import sqlite3
import struct
import zlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from imperaos.artifacts.errors import ArtifactDomainError, ArtifactErrorCode
from imperaos.artifacts.filesystem import GuardedArtifactFilesystem
from imperaos.artifacts.migrations import (
    DEFAULT_BUSY_TIMEOUT_MS,
    connect_artifact_metadata,
    migrate_artifact_metadata,
)
from imperaos.artifacts.models import (
    ArtifactAssetDescriptor,
    ArtifactDataClass,
    can_transition_data_class,
)

DEFAULT_MAX_ASSET_BYTES = 20 * 1024 * 1024
DEFAULT_WORKSPACE_ASSET_QUOTA_BYTES = 2 * 1024 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class AssetImportResult:
    descriptor: ArtifactAssetDescriptor
    deduplicated: bool


class ArtifactAssetStore:
    def __init__(
        self,
        root: str | Path,
        *,
        max_asset_bytes: int = DEFAULT_MAX_ASSET_BYTES,
        workspace_quota_bytes: int = DEFAULT_WORKSPACE_ASSET_QUOTA_BYTES,
        busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
    ) -> None:
        if max_asset_bytes < 1 or workspace_quota_bytes < 1:
            raise ValueError("asset limits must be positive")
        self.filesystem = GuardedArtifactFilesystem(root)
        self.database_path = self.filesystem.metadata_root / "artifacts.sqlite3"
        self.max_asset_bytes = min(max_asset_bytes, DEFAULT_MAX_ASSET_BYTES)
        self.workspace_quota_bytes = min(
            workspace_quota_bytes,
            DEFAULT_WORKSPACE_ASSET_QUOTA_BYTES,
        )
        self.busy_timeout_ms = busy_timeout_ms
        migrate_artifact_metadata(
            self.database_path,
            busy_timeout_ms=self.busy_timeout_ms,
        )

    def import_bytes(
        self,
        workspace_id: str,
        payload: bytes,
        *,
        declared_media_type: str,
        data_class: ArtifactDataClass,
        created_by_id: str,
        original_name: str | None = None,
        width: int | None = None,
        height: int | None = None,
    ) -> AssetImportResult:
        if not payload:
            self._raise_type_unsupported("empty_payload")
        if len(payload) > self.max_asset_bytes:
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_CONTENT_TOO_LARGE,
                "asset exceeds the per-file size limit",
                details={
                    "limitBytes": self.max_asset_bytes,
                    "actualBytes": len(payload),
                },
            )

        detected_media_type = _detect_media_type(payload)
        digest = hashlib.sha256(payload).hexdigest()
        if detected_media_type == "image/svg+xml":
            quarantine_relpath = self._quarantine_svg(payload, digest)
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_ASSET_UNSAFE,
                "SVG assets require a separate sanitizer and remain quarantined",
                details={
                    "classification": "svg_quarantined",
                    "quarantineRelpath": quarantine_relpath,
                },
            )
        if detected_media_type is None:
            self._raise_type_unsupported("magic_bytes_unknown")
        if declared_media_type != detected_media_type:
            self._raise_type_unsupported("declared_mime_mismatch")
        try:
            detected_width, detected_height = _validate_raster_structure(
                payload,
                detected_media_type,
            )
        except ValueError:
            self._raise_type_unsupported("image_structure_invalid")
        if width is not None and width != detected_width:
            self._raise_type_unsupported("image_dimensions_mismatch")
        if height is not None and height != detected_height:
            self._raise_type_unsupported("image_dimensions_mismatch")
        width = detected_width
        height = detected_height

        existing = self._find_by_hash(workspace_id, digest)
        if existing is not None:
            self.filesystem.read_bytes(
                existing.relative_path,
                expected_sha256=existing.sha256,
            )
            return AssetImportResult(
                self._promote_data_class(existing, data_class),
                True,
            )

        current_usage = self.workspace_usage_bytes(workspace_id)
        if current_usage + len(payload) > self.workspace_quota_bytes:
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_QUOTA_EXCEEDED,
                "workspace asset quota would be exceeded",
                details={
                    "limitBytes": self.workspace_quota_bytes,
                    "currentBytes": current_usage,
                    "requestedBytes": len(payload),
                },
            )

        relative_path = f"assets/{workspace_id}/sha256/{digest[:2]}/{digest}"
        asset_id = "asset-" + hashlib.sha256(f"{workspace_id}:{digest}".encode()).hexdigest()[:32]
        try:
            descriptor = ArtifactAssetDescriptor(
                asset_id=asset_id,
                workspace_id=workspace_id,
                sha256=digest,
                media_type=detected_media_type,
                size_bytes=len(payload),
                relative_path=relative_path,
                width=width,
                height=height,
                original_name=original_name,
                data_class=data_class,
                created_by_id=created_by_id,
                created_at_utc=datetime.now(UTC),
            )
        except ValidationError as exc:
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_SCHEMA_INVALID,
                "asset metadata is invalid",
            ) from exc

        target = self.filesystem.resolve_relative(relative_path)
        if target.exists():
            self.filesystem.read_bytes(relative_path, expected_sha256=digest)
        else:
            self.filesystem.atomic_write_bytes(
                relative_path,
                payload,
                expected_sha256=digest,
            )
        try:
            return self._insert_or_get_deduplicated(descriptor)
        except ArtifactDomainError as exc:
            if (
                exc.code is ArtifactErrorCode.ARTIFACT_QUOTA_EXCEEDED
                and self._find_by_hash(workspace_id, digest) is None
                and target.exists()
            ):
                self.filesystem.quarantine(relative_path, reason="asset-quota-rejected")
            raise

    def import_remote_url(self, workspace_id: str, url: str) -> None:
        del workspace_id, url
        raise ArtifactDomainError(
            ArtifactErrorCode.ARTIFACT_ASSET_UNSAFE,
            "remote asset fetch is disabled",
            details={"classification": "remote_fetch_denied"},
        )

    def get_descriptor(self, workspace_id: str, asset_id: str) -> ArtifactAssetDescriptor:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM artifact_assets WHERE asset_id = ? AND workspace_id = ?",
                (asset_id, workspace_id),
            ).fetchone()
        if row is None:
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_NOT_FOUND,
                "artifact asset does not exist",
            )
        return _asset_from_row(row)

    def get_bytes(self, workspace_id: str, asset_id: str) -> bytes:
        descriptor = self.get_descriptor(workspace_id, asset_id)
        return self.filesystem.read_bytes(
            descriptor.relative_path,
            expected_sha256=descriptor.sha256,
        )

    def workspace_usage_bytes(self, workspace_id: str) -> int:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT COALESCE(SUM(size_bytes), 0)
                FROM artifact_assets WHERE workspace_id = ?
                """,
                (workspace_id,),
            ).fetchone()
        return int(row[0])

    def _find_by_hash(
        self,
        workspace_id: str,
        digest: str,
    ) -> ArtifactAssetDescriptor | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM artifact_assets
                WHERE workspace_id = ? AND sha256 = ?
                """,
                (workspace_id, digest),
            ).fetchone()
        return None if row is None else _asset_from_row(row)

    def _insert_or_get_deduplicated(
        self,
        descriptor: ArtifactAssetDescriptor,
    ) -> AssetImportResult:
        with self._connect() as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                existing_row = connection.execute(
                    """
                    SELECT * FROM artifact_assets
                    WHERE workspace_id = ? AND sha256 = ?
                    """,
                    (descriptor.workspace_id, descriptor.sha256),
                ).fetchone()
                if existing_row is not None:
                    existing = _asset_from_row(existing_row)
                    promoted = existing
                    if (
                        existing.data_class is not descriptor.data_class
                        and can_transition_data_class(
                            existing.data_class,
                            descriptor.data_class,
                        )
                    ):
                        connection.execute(
                            "UPDATE artifact_assets SET data_class = ? WHERE asset_id = ?",
                            (descriptor.data_class.value, existing.asset_id),
                        )
                        promoted = existing.model_copy(
                            update={"data_class": descriptor.data_class}
                        )
                    connection.commit()
                    return AssetImportResult(promoted, True)
                usage_row = connection.execute(
                    """
                    SELECT COALESCE(SUM(size_bytes), 0)
                    FROM artifact_assets WHERE workspace_id = ?
                    """,
                    (descriptor.workspace_id,),
                ).fetchone()
                current_usage = int(usage_row[0])
                if current_usage + descriptor.size_bytes > self.workspace_quota_bytes:
                    raise ArtifactDomainError(
                        ArtifactErrorCode.ARTIFACT_QUOTA_EXCEEDED,
                        "workspace asset quota would be exceeded",
                        details={
                            "limitBytes": self.workspace_quota_bytes,
                            "currentBytes": current_usage,
                            "requestedBytes": descriptor.size_bytes,
                        },
                    )
                connection.execute(
                    """
                    INSERT INTO artifact_assets (
                        asset_id, workspace_id, sha256, media_type, size_bytes,
                        relative_path, width, height, original_name, data_class,
                        created_by_id, created_at_utc
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        descriptor.asset_id,
                        descriptor.workspace_id,
                        descriptor.sha256,
                        descriptor.media_type,
                        descriptor.size_bytes,
                        descriptor.relative_path,
                        descriptor.width,
                        descriptor.height,
                        descriptor.original_name,
                        descriptor.data_class.value,
                        descriptor.created_by_id,
                        descriptor.created_at_utc.isoformat(),
                    ),
                )
                connection.commit()
                return AssetImportResult(descriptor, False)
            except ArtifactDomainError:
                connection.rollback()
                raise
            except sqlite3.IntegrityError:
                connection.rollback()
        existing = self._find_by_hash(descriptor.workspace_id, descriptor.sha256)
        if existing is None:
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_STORAGE_CORRUPT,
                "asset metadata could not be committed",
            )
        return AssetImportResult(
            self._promote_data_class(existing, descriptor.data_class),
            True,
        )

    def _promote_data_class(
        self,
        descriptor: ArtifactAssetDescriptor,
        requested: ArtifactDataClass,
    ) -> ArtifactAssetDescriptor:
        if descriptor.data_class is requested or not can_transition_data_class(
            descriptor.data_class,
            requested,
        ):
            return descriptor
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM artifact_assets WHERE asset_id = ? AND workspace_id = ?",
                (descriptor.asset_id, descriptor.workspace_id),
            ).fetchone()
            if row is None:
                connection.rollback()
                raise ArtifactDomainError(
                    ArtifactErrorCode.ARTIFACT_STORAGE_CORRUPT,
                    "deduplicated asset metadata disappeared",
                )
            current = _asset_from_row(row)
            if current.data_class is not requested and can_transition_data_class(
                current.data_class,
                requested,
            ):
                connection.execute(
                    "UPDATE artifact_assets SET data_class = ? WHERE asset_id = ?",
                    (requested.value, current.asset_id),
                )
                current = current.model_copy(update={"data_class": requested})
            connection.commit()
            return current

    def _quarantine_svg(self, payload: bytes, digest: str) -> str:
        relative_path = f"quarantine/unsafe-svg/{digest}.svg"
        target = self.filesystem.resolve_relative(relative_path)
        if target.exists():
            self.filesystem.read_bytes(relative_path, expected_sha256=digest)
        else:
            self.filesystem.atomic_write_bytes(
                relative_path,
                payload,
                expected_sha256=digest,
            )
        return relative_path

    def _connect(self) -> sqlite3.Connection:
        return connect_artifact_metadata(
            self.database_path,
            busy_timeout_ms=self.busy_timeout_ms,
        )

    @staticmethod
    def _raise_type_unsupported(classification: str) -> None:
        raise ArtifactDomainError(
            ArtifactErrorCode.ARTIFACT_ASSET_TYPE_UNSUPPORTED,
            "asset media type is not supported or does not match its content",
            details={"classification": classification},
        )


def _detect_media_type(payload: bytes) -> str | None:
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if payload.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if payload.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(payload) >= 12 and payload.startswith(b"RIFF") and payload[8:12] == b"WEBP":
        return "image/webp"
    normalized = payload[:4096].lstrip(b"\xef\xbb\xbf\x00\t\r\n ").lower()
    if normalized.startswith(b"<svg") or (
        normalized.startswith(b"<?xml") and b"<svg" in normalized
    ):
        return "image/svg+xml"
    return None


def _validate_raster_structure(payload: bytes, media_type: str) -> tuple[int, int]:
    validators = {
        "image/png": _validate_png,
        "image/jpeg": _validate_jpeg,
        "image/gif": _validate_gif,
        "image/webp": _validate_webp,
    }
    validator = validators.get(media_type)
    if validator is None:
        raise ValueError("unsupported raster media type")
    return validator(payload)


def _validate_png(payload: bytes) -> tuple[int, int]:
    if not payload.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("invalid PNG signature")
    offset = 8
    dimensions: tuple[int, int] | None = None
    saw_idat = False
    while offset < len(payload):
        if offset + 12 > len(payload):
            raise ValueError("truncated PNG chunk")
        length = struct.unpack(">I", payload[offset : offset + 4])[0]
        chunk_type = payload[offset + 4 : offset + 8]
        end = offset + 12 + length
        if end > len(payload):
            raise ValueError("truncated PNG payload")
        data = payload[offset + 8 : offset + 8 + length]
        expected_crc = struct.unpack(">I", payload[offset + 8 + length : end])[0]
        if zlib.crc32(chunk_type + data) & 0xFFFFFFFF != expected_crc:
            raise ValueError("invalid PNG CRC")
        if dimensions is None:
            if chunk_type != b"IHDR" or length != 13:
                raise ValueError("PNG must start with IHDR")
            width, height = struct.unpack(">II", data[:8])
            if width < 1 or height < 1:
                raise ValueError("invalid PNG dimensions")
            dimensions = (width, height)
        elif chunk_type == b"IHDR":
            raise ValueError("duplicate PNG IHDR")
        if chunk_type == b"IDAT":
            saw_idat = True
        if chunk_type == b"IEND":
            if length != 0 or not saw_idat or end != len(payload):
                raise ValueError("invalid PNG end")
            return dimensions
        offset = end
    raise ValueError("PNG is missing IEND")


def _validate_gif(payload: bytes) -> tuple[int, int]:
    if len(payload) < 14 or payload[:6] not in {b"GIF87a", b"GIF89a"}:
        raise ValueError("invalid GIF header")
    width, height = struct.unpack("<HH", payload[6:10])
    if width < 1 or height < 1:
        raise ValueError("invalid GIF dimensions")
    packed = payload[10]
    offset = 13 + (3 * (2 ** ((packed & 0x07) + 1)) if packed & 0x80 else 0)
    saw_image = False

    def skip_subblocks(start: int) -> int:
        cursor = start
        while cursor < len(payload):
            size = payload[cursor]
            cursor += 1
            if size == 0:
                return cursor
            cursor += size
            if cursor > len(payload):
                break
        raise ValueError("truncated GIF data blocks")

    while offset < len(payload):
        marker = payload[offset]
        offset += 1
        if marker == 0x3B:
            if not saw_image or offset != len(payload):
                raise ValueError("invalid GIF trailer")
            return width, height
        if marker == 0x21:
            if offset >= len(payload):
                raise ValueError("truncated GIF extension")
            offset = skip_subblocks(offset + 1)
            continue
        if marker != 0x2C or offset + 9 > len(payload):
            raise ValueError("invalid GIF block")
        descriptor = payload[offset : offset + 9]
        offset += 9
        local_packed = descriptor[8]
        if local_packed & 0x80:
            offset += 3 * (2 ** ((local_packed & 0x07) + 1))
        if offset >= len(payload):
            raise ValueError("truncated GIF image")
        offset = skip_subblocks(offset + 1)
        saw_image = True
    raise ValueError("GIF is missing trailer")


def _validate_jpeg(payload: bytes) -> tuple[int, int]:
    if len(payload) < 4 or not payload.startswith(b"\xff\xd8"):
        raise ValueError("invalid JPEG header")
    offset = 2
    dimensions: tuple[int, int] | None = None
    while offset < len(payload):
        if payload[offset] != 0xFF:
            raise ValueError("invalid JPEG marker")
        while offset < len(payload) and payload[offset] == 0xFF:
            offset += 1
        if offset >= len(payload):
            raise ValueError("truncated JPEG marker")
        marker = payload[offset]
        offset += 1
        if marker == 0xD9:
            if dimensions is None or offset != len(payload):
                raise ValueError("invalid JPEG end")
            return dimensions
        if marker in {0x01, *range(0xD0, 0xD8)}:
            continue
        if offset + 2 > len(payload):
            raise ValueError("truncated JPEG segment")
        length = struct.unpack(">H", payload[offset : offset + 2])[0]
        if length < 2 or offset + length > len(payload):
            raise ValueError("invalid JPEG segment length")
        data = payload[offset + 2 : offset + length]
        if marker in {0xC0, 0xC1, 0xC2}:
            if len(data) < 5:
                raise ValueError("truncated JPEG dimensions")
            height, width = struct.unpack(">HH", data[1:5])
            if width < 1 or height < 1:
                raise ValueError("invalid JPEG dimensions")
            dimensions = (width, height)
        offset += length
        if marker == 0xDA:
            while offset + 1 < len(payload):
                if payload[offset] != 0xFF:
                    offset += 1
                    continue
                next_byte = payload[offset + 1]
                if next_byte in {0x00, *range(0xD0, 0xD8)}:
                    offset += 2
                    continue
                break
    raise ValueError("JPEG is missing EOI")


def _validate_webp(payload: bytes) -> tuple[int, int]:
    if len(payload) < 20 or payload[:4] != b"RIFF" or payload[8:12] != b"WEBP":
        raise ValueError("invalid WebP header")
    if struct.unpack("<I", payload[4:8])[0] + 8 != len(payload):
        raise ValueError("invalid WebP RIFF size")
    offset = 12
    dimensions: tuple[int, int] | None = None
    while offset + 8 <= len(payload):
        chunk_type = payload[offset : offset + 4]
        length = struct.unpack("<I", payload[offset + 4 : offset + 8])[0]
        start = offset + 8
        end = start + length
        padded_end = end + (length & 1)
        if padded_end > len(payload):
            raise ValueError("truncated WebP chunk")
        data = payload[start:end]
        if chunk_type == b"VP8X" and len(data) >= 10:
            width = int.from_bytes(data[4:7], "little") + 1
            height = int.from_bytes(data[7:10], "little") + 1
            dimensions = (width, height)
        elif chunk_type == b"VP8 " and len(data) >= 10 and data[3:6] == b"\x9d\x01\x2a":
            dimensions = (
                struct.unpack("<H", data[6:8])[0] & 0x3FFF,
                struct.unpack("<H", data[8:10])[0] & 0x3FFF,
            )
        elif chunk_type == b"VP8L" and len(data) >= 5 and data[0] == 0x2F:
            bits = int.from_bytes(data[1:5], "little")
            dimensions = ((bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1)
        offset = padded_end
    if offset != len(payload) or dimensions is None or min(dimensions) < 1:
        raise ValueError("invalid WebP image data")
    return dimensions


def _asset_from_row(row: sqlite3.Row) -> ArtifactAssetDescriptor:
    return ArtifactAssetDescriptor(
        asset_id=row["asset_id"],
        workspace_id=row["workspace_id"],
        sha256=row["sha256"],
        media_type=row["media_type"],
        size_bytes=row["size_bytes"],
        relative_path=row["relative_path"],
        width=row["width"],
        height=row["height"],
        original_name=row["original_name"],
        data_class=row["data_class"],
        created_by_id=row["created_by_id"],
        created_at_utc=datetime.fromisoformat(row["created_at_utc"]),
    )
