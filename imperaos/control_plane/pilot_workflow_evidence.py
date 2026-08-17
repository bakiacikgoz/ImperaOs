from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from imperaos.control_plane.provider_governance import stable_hash_payload

FORBIDDEN_EVIDENCE_KEYS = {
    "prompt",
    "response",
    "raw",
    "raw_input",
    "raw_output",
    "memory_content",
    "secret",
    "token",
    "api_key",
    "apikey",
    "password",
    "private_key",
}

FORBIDDEN_RAW_MARKERS = (
    "BEGIN RAW",
    "RAW_PROMPT",
    "RAW_RESPONSE",
    "RAW_MEMORY",
    "sk-",
    "api_key=",
    "password=",
)


def sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def safe_hash_payload(payload: Any) -> str:
    return stable_hash_payload(payload)


def assert_hash_only_payload(payload: Any) -> None:
    leaks = find_raw_leaks(payload, include_keys=True)
    if leaks:
        raise ValueError(
            "hash-only evidence payload contains forbidden raw fields: " + ",".join(leaks)
        )


def find_raw_leaks(payload: Any, *, include_keys: bool = False) -> list[str]:
    leaks: list[str] = []

    def walk(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                normalized = str(key).replace("-", "_").lower()
                next_path = f"{path}.{key}" if path else str(key)
                if include_keys and normalized in FORBIDDEN_EVIDENCE_KEYS:
                    leaks.append(next_path)
                walk(item, next_path)
            return
        if isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{path}[{index}]")
            return
        if isinstance(value, str):
            lower = value.lower()
            if any(marker.lower() in lower for marker in FORBIDDEN_RAW_MARKERS):
                leaks.append(path or "$")

    walk(payload, "")
    return sorted(set(leaks))


class PilotWorkflowEvidenceWriter:
    def __init__(self, run_root: str | Path) -> None:
        self.run_root = Path(run_root)
        self.run_root.mkdir(parents=True, exist_ok=True)

    def write_json(
        self,
        relative_path: str,
        payload: Any,
        *,
        enforce_hash_only: bool = True,
    ) -> str:
        if enforce_hash_only:
            assert_hash_only_payload(payload)
        path = self.run_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
        tmp.replace(path)
        return str(path)

    def write_text(self, relative_path: str, body: str) -> str:
        path = self.run_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(body, encoding="utf-8")
        tmp.replace(path)
        return str(path)

    def write_manifest(self, refs: list[str]) -> str:
        items = [
            {
                "path": ref,
                "sha256": sha256_file(Path(ref)),
                "required": True,
            }
            for ref in sorted(set(refs))
            if Path(ref).exists()
        ]
        return self.write_json(
            "evidence_manifest.json",
            {
                "schemaVersion": "control-plane.governed-pilot-workflow-evidence-manifest/v1",
                "evidenceMode": "hash_only",
                "rawPersistence": False,
                "items": items,
            },
        )


def mirror_latest(run_root: Path, latest_root: Path) -> None:
    if latest_root.exists():
        shutil.rmtree(latest_root)
    latest_root.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(run_root, latest_root, ignore=_ignore_sqlite_transients)


def _ignore_sqlite_transients(_directory: str, names: list[str]) -> set[str]:
    return {
        name
        for name in names
        if name.endswith(("-shm", "-wal", "-journal"))
        or name.endswith((".sqlite3-shm", ".sqlite3-wal", ".sqlite3-journal"))
    }
