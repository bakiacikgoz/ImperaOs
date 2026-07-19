from __future__ import annotations

import json
from pathlib import Path

from imperaos.memory.semantic.models import SemanticIndexManifest


def manifest_path(index_root: str | Path, workspace_id: str) -> Path:
    return Path(index_root) / _safe_workspace(workspace_id) / "manifest.json"


def records_path(index_root: str | Path, workspace_id: str) -> Path:
    return Path(index_root) / _safe_workspace(workspace_id) / "records.json"


def write_manifest(path: str | Path, manifest: SemanticIndexManifest) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            manifest.model_dump(mode="json", by_alias=True),
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def read_manifest(path: str | Path) -> SemanticIndexManifest | None:
    target = Path(path)
    if not target.exists():
        return None
    return SemanticIndexManifest.model_validate_json(target.read_text(encoding="utf-8"))


def _safe_workspace(workspace_id: str) -> str:
    return "".join(char if char.isalnum() or char in "._-" else "_" for char in workspace_id)
