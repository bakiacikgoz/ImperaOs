from __future__ import annotations

import re
from pathlib import Path

from imperaos.control_plane.storage import file_sha256
from imperaos.release_decision.models import EvidenceKind, EvidenceRef

ALLOWED_SUFFIXES = {".json", ".md", ".txt", ".yaml", ".yml"}
RAW_OR_SECRET_RE = re.compile(
    r"BEGIN PRIVATE KEY|sk-[A-Za-z0-9]|TOKEN=|PASSWORD=|PFX|raw_prompt|raw_response|raw_screenshot",
    re.IGNORECASE,
)


def normalize_relative_path(path: Path, *, repo_root: Path) -> str:
    resolved = path.resolve()
    root = repo_root.resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError("evidence path must stay within repo root") from exc
    normalized = relative.as_posix()
    if ".." in normalized.split("/"):
        raise ValueError("evidence path must not traverse parents")
    return normalized


def scan_file(path: Path) -> list[str]:
    if path.suffix.lower() not in ALLOWED_SUFFIXES:
        return [f"UNSUPPORTED_ARTIFACT_EXTENSION:{path.suffix.lower() or 'none'}"]
    text = path.read_text(encoding="utf-8", errors="replace")
    findings = sorted(set(match.group(0) for match in RAW_OR_SECRET_RE.finditer(text)))
    return [f"RAW_OR_SECRET_MARKER:{item}" for item in findings]


def load_evidence_ref(path: Path, *, kind: EvidenceKind, repo_root: Path) -> EvidenceRef:
    if not path.exists():
        raise FileNotFoundError(path)
    normalized = normalize_relative_path(path, repo_root=repo_root)
    return EvidenceRef(
        artifactId=Path(normalized).stem.replace("_", "-").lower(),
        path=normalized,
        sha256=file_sha256(path),
        kind=kind,
    )
