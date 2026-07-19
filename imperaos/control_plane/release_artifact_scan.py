from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import Field

from imperaos.control_plane.storage import file_sha256
from imperaos.memory.models import StrictModel

SCAN_RE = re.compile(
    r"(sk-[A-Za-z0-9_-]+|ghp_[A-Za-z0-9_]+|xoxb-[A-Za-z0-9-]+|"
    r"api[_-]?key\s*[:=]\s*['\"][^'\"]+|password\s*[:=]\s*['\"][^'\"]+|"
    r"private_key|BEGIN RAW|['\"]?rawPromptPersisted['\"]?\s*[:=]\s*true|"
    r"['\"]?rawResponsePersisted['\"]?\s*[:=]\s*true|"
    r"['\"]?rawScreenshotPersisted['\"]?\s*[:=]\s*true)",
    re.I,
)


class ArtifactScanItem(StrictModel):
    path: str
    sha256: str
    status: Literal["pass", "blocked", "skipped"] = "pass"
    reason_code: str | None = Field(default=None, alias="reasonCode")


class ArtifactScanReport(StrictModel):
    schema_version: Literal["control-plane.release-artifact-scan/v1"] = Field(
        default="control-plane.release-artifact-scan/v1",
        alias="schemaVersion",
    )
    generated_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        alias="generatedAtUtc",
    )
    status: Literal["pass", "blocked"] = "pass"
    artifact_root: str | None = Field(default=None, alias="artifactRoot")
    scanned_file_count: int = Field(default=0, alias="scannedFileCount")
    skipped_file_count: int = Field(default=0, alias="skippedFileCount")
    secret_marker_count: int = Field(default=0, alias="secretMarkerCount")
    raw_marker_count: int = Field(default=0, alias="rawMarkerCount")
    items: list[ArtifactScanItem] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def scan_release_artifacts(
    *,
    artifact_root: Path,
    include_paths: list[str] | None = None,
) -> ArtifactScanReport:
    root = Path(artifact_root).resolve()
    blockers: list[str] = []
    warnings: list[str] = []
    items: list[ArtifactScanItem] = []
    secret_count = 0
    raw_count = 0
    skipped = 0
    if not root.exists():
        return ArtifactScanReport(
            status="blocked",
            artifactRoot=str(artifact_root),
            blockers=["ARTIFACT_ROOT_MISSING"],
        )

    paths = (
        [_resolve_in_root(root, item) for item in include_paths]
        if include_paths
        else _files(root)
    )
    for original, path in paths:
        if path is None:
            blockers.append(f"ARTIFACT_PATH_OUTSIDE_ROOT:{original}")
            continue
        if path.is_dir():
            continue
        rel = str(path.relative_to(root)).replace("\\", "/")
        try:
            data = path.read_bytes()
        except OSError:
            warnings.append(f"ARTIFACT_UNREADABLE:{rel}")
            continue
        digest = f"sha256:{file_sha256(path)}"
        if _is_probably_binary(data):
            skipped += 1
            items.append(
                ArtifactScanItem(
                    path=rel,
                    sha256=digest,
                    status="skipped",
                    reasonCode="BINARY_SKIP",
                )
            )
            continue
        text = data.decode("utf-8", errors="ignore")
        match = SCAN_RE.search(text)
        if match:
            marker = match.group(0).lower()
            if "raw" in marker:
                raw_count += 1
            else:
                secret_count += 1
            items.append(
                ArtifactScanItem(
                    path=rel,
                    sha256=digest,
                    status="blocked",
                    reasonCode="RAW_OR_SECRET_MARKER_FOUND",
                )
            )
            blockers.append("RAW_OR_SECRET_MARKER_FOUND")
            continue
        items.append(ArtifactScanItem(path=rel, sha256=digest))

    return ArtifactScanReport(
        status="blocked" if blockers else "pass",
        artifactRoot=str(artifact_root),
        scannedFileCount=sum(1 for item in items if item.status != "skipped"),
        skippedFileCount=skipped,
        secretMarkerCount=secret_count,
        rawMarkerCount=raw_count,
        items=items,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
    )


def _resolve_in_root(root: Path, value: str) -> tuple[str, Path | None]:
    candidate = (root / value).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return value, None
    return value, candidate


def _files(root: Path) -> list[tuple[str, Path]]:
    return [
        (str(path.relative_to(root)).replace("\\", "/"), path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    ]


def _is_probably_binary(data: bytes) -> bool:
    return b"\x00" in data[:4096]
