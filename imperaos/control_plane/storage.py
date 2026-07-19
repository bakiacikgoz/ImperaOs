from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from imperaos.control_plane.errors import PathOutsideRoot, RegistryCorrupted
from imperaos.runtime.paths import CONTROL_PLANE_STATE_ROOT


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=_json_default,
    )


def canonical_json_hash(value: Any, *, prefixed: bool = True) -> str:
    digest = hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
    return f"sha256:{digest}" if prefixed else digest


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ControlPlaneStore:
    def __init__(self, root_dir: str | Path = CONTROL_PLANE_STATE_ROOT):
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def path(self, *parts: str) -> Path:
        candidate = (self.root_dir.joinpath(*parts)).resolve()
        root = self.root_dir.resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise PathOutsideRoot(
                "PATH_OUTSIDE_CONTROL_PLANE_ROOT",
                f"path escapes control-plane root: {candidate}",
            ) from exc
        return candidate

    def read_json(self, relative_path: str, *, default: Any = None) -> Any:
        path = self.path(relative_path)
        if not path.exists():
            return default
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            backup = path.with_name(
                f"{path.stem}.corrupt.{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}{path.suffix}"
            )
            path.replace(backup)
            raise RegistryCorrupted(
                "CONTROL_PLANE_STATE_CORRUPTED",
                f"invalid JSON moved to {backup}",
            ) from exc

    def write_json_atomic(self, relative_path: str, payload: Any) -> Path:
        path = self.path(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        serialized = json.dumps(
            payload,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
            default=_json_default,
        )
        with tmp.open("w", encoding="utf-8") as file_obj:
            file_obj.write(serialized)
            file_obj.write("\n")
            file_obj.flush()
            os.fsync(file_obj.fileno())
        tmp.replace(path)
        return path


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)
