from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
from pathlib import Path
from uuid import uuid4


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest(root: Path) -> dict:
    files = {
        p.relative_to(root).as_posix(): _hash(p) for p in sorted(root.rglob("*")) if p.is_file()
    }
    return {
        "schemaVersion": "imperaos.legacy-state-migration/v1",
        "fileCount": len(files),
        "files": files,
    }


def _copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.suffix.lower() in {".db", ".sqlite", ".sqlite3"}:
        with sqlite3.connect(source) as src, sqlite3.connect(destination) as dst:
            src.backup(dst)
        return
    shutil.copy2(source, destination)


def migrate_legacy_state(
    source: str | Path, destination: str | Path, *, copy: bool = False, verify: bool = False
) -> dict:
    source_path = Path(source).resolve()
    destination_path = Path(destination).resolve()
    if not source_path.is_dir():
        return {"status": "blocked", "reasonCode": "LEGACY_STATE_SOURCE_NOT_FOUND"}
    if destination_path.exists():
        return {"status": "blocked", "reasonCode": "LEGACY_STATE_DESTINATION_CONFLICT"}
    source_manifest = _manifest(source_path)
    if not copy:
        return {
            "status": "dry_run",
            "source": str(source_path),
            "destination": str(destination_path),
            "manifest": source_manifest,
        }
    temporary = destination_path.with_name(f".{destination_path.name}.migration-{uuid4().hex}")
    try:
        for item in source_path.rglob("*"):
            if item.is_file():
                _copy_file(item, temporary / item.relative_to(source_path))
        copied_manifest = _manifest(temporary)
        if verify and copied_manifest["files"] != source_manifest["files"]:
            raise ValueError("LEGACY_STATE_VERIFICATION_FAILED")
        (temporary / "migration-manifest.json").write_text(
            json.dumps(source_manifest, indent=2) + "\n", encoding="utf-8"
        )
        os.replace(temporary, destination_path)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    return {
        "status": "copied",
        "source": str(source_path),
        "destination": str(destination_path),
        "manifest": source_manifest,
        "sourcePreserved": source_path.exists(),
    }
