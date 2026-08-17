"""Shared, repository-relative runtime state paths."""

from __future__ import annotations

import ntpath
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Final

DEFAULT_STATE_ROOT: Final[Path] = Path(".imperaos")


def _validated_segments(parts: tuple[str, ...]) -> tuple[str, ...]:
    segments: list[str] = []
    for part in parts:
        if "\0" in part:
            raise ValueError("runtime paths must not contain NUL characters")
        if (
            PurePosixPath(part).is_absolute()
            or PureWindowsPath(part).is_absolute()
            or bool(ntpath.splitdrive(part)[0])
        ):
            raise ValueError(f"runtime path must be repository-relative: {part!r}")

        normalized = part.replace("\\", "/")
        part_segments = normalized.split("/")
        if ".." in part_segments:
            raise ValueError(f"runtime path traversal is not allowed: {part!r}")
        if any(segment == "" for segment in part_segments):
            raise ValueError(f"runtime path contains an empty segment: {part!r}")
        segments.extend(part_segments)
    return tuple(segments)


def state_path(*parts: str) -> str:
    """Return a platform-independent repo-relative runtime path."""

    segments = _validated_segments(parts)
    root = DEFAULT_STATE_ROOT.as_posix()
    return "/".join((root, *segments)) if segments else root


def enterprise_state_path(*parts: str) -> str:
    """Return a path beneath ``.imperaos/enterprise``."""

    return state_path("enterprise", *_validated_segments(parts))


CONTROL_PLANE_STATE_ROOT: Final[str] = state_path("control-plane")
ENTERPRISE_STATE_ROOT: Final[str] = enterprise_state_path()
TEAM_ARTIFACT_ROOT: Final[str] = state_path("team", "jobs")
MEMORY_DB_PATH: Final[str] = state_path("memory.sqlite3")
MEMORY_TURBOVEC_ROOT: Final[str] = state_path("memory-turbovec")
TRACE_STATE_ROOT: Final[str] = state_path("traces")
ROUTER_DATASET_PATH: Final[str] = state_path("research", "router_dataset.jsonl")
