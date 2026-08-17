from __future__ import annotations

import errno
import hashlib
import os
import unicodedata
import uuid
from dataclasses import dataclass
from pathlib import Path

from imperaos.artifacts.errors import ArtifactDomainError, ArtifactErrorCode

_DISK_FULL_ERRNOS = {errno.ENOSPC}
if hasattr(errno, "EDQUOT"):
    _DISK_FULL_ERRNOS.add(errno.EDQUOT)

_LOCKED_ERRNOS = {errno.EACCES, errno.EAGAIN, errno.EBUSY, errno.EPERM}
_LAYOUT_DIRECTORIES = ("metadata", "content", "assets", "tmp", "quarantine", "backups")


@dataclass(frozen=True, slots=True)
class StoredArtifactFile:
    relative_path: str
    sha256: str
    size_bytes: int


class GuardedArtifactFilesystem:
    """Filesystem boundary for immutable artifact content and assets."""

    def __init__(self, root: str | Path) -> None:
        configured_root = Path(root).expanduser()
        configured_root.mkdir(parents=True, exist_ok=True)
        self.root = configured_root.resolve(strict=True)
        if not self.root.is_dir():
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_STORAGE_CORRUPT,
                "artifact storage root is not a directory",
            )
        for name in _LAYOUT_DIRECTORIES:
            directory = self.root / name
            if directory.exists() or directory.is_symlink():
                self._assert_below_root(directory)
            directory.mkdir(parents=False, exist_ok=True)
            self._assert_below_root(directory)

        self.metadata_root = self.root / "metadata"
        self.content_root = self.root / "content"
        self.assets_root = self.root / "assets"
        self.tmp_root = self.root / "tmp"
        self.quarantine_root = self.root / "quarantine"
        self.backups_root = self.root / "backups"

    def resolve_relative(self, relative_path: str | Path) -> Path:
        normalized = self._normalize_relative(relative_path)
        candidate = self.root.joinpath(*normalized.split("/"))
        resolved = candidate.resolve(strict=False)
        self._assert_below_root(resolved)
        return resolved

    def atomic_write_bytes(
        self,
        relative_path: str | Path,
        payload: bytes,
        *,
        expected_sha256: str | None = None,
    ) -> StoredArtifactFile:
        target = self.resolve_relative(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target = self.resolve_relative(relative_path)
        temp_path = self.tmp_root / f"{uuid.uuid4().hex}.tmp"
        digest = hashlib.sha256(payload).hexdigest()

        try:
            with temp_path.open("xb") as file_obj:
                file_obj.write(payload)
                file_obj.flush()
                os.fsync(file_obj.fileno())

            if expected_sha256 is not None and digest != expected_sha256:
                quarantine_path = self._quarantine_path(temp_path, "hash-mismatch")
                raise ArtifactDomainError(
                    ArtifactErrorCode.ARTIFACT_HASH_MISMATCH,
                    "artifact content hash does not match the expected digest",
                    details={
                        "expectedSha256": expected_sha256,
                        "actualSha256": digest,
                        "quarantineRelpath": quarantine_path.relative_to(self.root).as_posix(),
                    },
                )

            os.replace(temp_path, target)
            self._fsync_directory(target.parent)
        except ArtifactDomainError:
            raise
        except OSError as exc:
            self._raise_classified_os_error(exc)
        finally:
            temp_path.unlink(missing_ok=True)

        return StoredArtifactFile(
            relative_path=target.relative_to(self.root).as_posix(),
            sha256=digest,
            size_bytes=len(payload),
        )

    def read_bytes(
        self,
        relative_path: str | Path,
        *,
        expected_sha256: str | None = None,
    ) -> bytes:
        path = self.resolve_relative(relative_path)
        try:
            payload = path.read_bytes()
        except OSError as exc:
            self._raise_classified_os_error(exc)

        if expected_sha256 is not None:
            actual_sha256 = hashlib.sha256(payload).hexdigest()
            if actual_sha256 != expected_sha256:
                quarantine_path = self._quarantine_path(path, "hash-mismatch")
                raise ArtifactDomainError(
                    ArtifactErrorCode.ARTIFACT_HASH_MISMATCH,
                    "stored artifact content failed hash verification",
                    details={
                        "expectedSha256": expected_sha256,
                        "actualSha256": actual_sha256,
                        "quarantineRelpath": quarantine_path.relative_to(self.root).as_posix(),
                    },
                )
        return payload

    def quarantine(self, relative_path: str | Path, *, reason: str) -> str:
        source = self.resolve_relative(relative_path)
        destination = self._quarantine_path(source, reason)
        return destination.relative_to(self.root).as_posix()

    def _quarantine_path(self, source: Path, reason: str) -> Path:
        self._assert_below_root(source)
        normalized_reason = "".join(
            character if character.isalnum() or character in {"-", "_"} else "-"
            for character in unicodedata.normalize("NFC", reason)
        ).strip("-")
        if not normalized_reason:
            normalized_reason = "unspecified"
        destination_dir = self.quarantine_root / normalized_reason
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = destination_dir / f"{uuid.uuid4().hex}-{source.name}"
        try:
            os.replace(source, destination)
            self._fsync_directory(destination_dir)
        except OSError as exc:
            self._raise_classified_os_error(exc)
        return destination

    def _assert_below_root(self, candidate: Path) -> None:
        try:
            candidate.resolve(strict=False).relative_to(self.root)
        except ValueError as exc:
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_WORKSPACE_MISMATCH,
                "artifact path escapes the configured storage root",
                details={"classification": "path_escape"},
            ) from exc

    @staticmethod
    def _normalize_relative(relative_path: str | Path) -> str:
        raw = unicodedata.normalize("NFC", str(relative_path)).replace("\\", "/")
        parts = raw.split("/")
        if (
            not raw
            or raw.startswith(("/", "~"))
            or ":" in raw
            or "\x00" in raw
            or any(part in {"", ".", ".."} for part in parts)
        ):
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_WORKSPACE_MISMATCH,
                "artifact path must be an unambiguous relative path",
                details={"classification": "unsafe_relative_path"},
            )
        return "/".join(parts)

    @staticmethod
    def _fsync_directory(directory: Path) -> None:
        if os.name == "nt":
            return
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        descriptor = os.open(directory, flags)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @staticmethod
    def _raise_classified_os_error(exc: OSError) -> None:
        if exc.errno in _DISK_FULL_ERRNOS:
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_QUOTA_EXCEEDED,
                "artifact storage has insufficient free space",
                retryable=False,
                details={"classification": "disk_full", "errno": exc.errno},
            ) from exc
        if exc.errno in _LOCKED_ERRNOS:
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_STORAGE_LOCKED,
                "artifact storage is temporarily locked",
                retryable=True,
                details={"classification": "storage_locked", "errno": exc.errno},
            ) from exc
        raise ArtifactDomainError(
            ArtifactErrorCode.ARTIFACT_STORAGE_CORRUPT,
            "artifact storage operation failed",
            details={"classification": "io_error", "errno": exc.errno},
        ) from exc
