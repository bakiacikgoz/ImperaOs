from __future__ import annotations

import os
import subprocess
from pathlib import Path


def find_matches(
    query: str,
    root_dir: str | Path = ".",
    max_matches: int = 8,
    max_columns: int = 240,
) -> list[dict[str, str | int]]:
    root = Path(root_dir)
    if not query.strip() or not root.exists():
        return []

    cmd = [
        "rg",
        "-n",
        "--no-heading",
        "--color",
        "never",
        "--max-count",
        str(max_matches),
        "--max-columns",
        str(max_columns),
        query,
        str(root),
        "-g",
        "!*.sqlite3",
        "-g",
        "!.git/*",
        "-g",
        "!.venv/*",
    ]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except OSError:
        return _find_matches_python(
            query=query,
            root=root,
            max_matches=max_matches,
            max_columns=max_columns,
        )

    if proc.returncode not in (0, 1):
        return []

    results: list[dict[str, str | int]] = []
    for line in proc.stdout.splitlines():
        parts = line.rsplit(":", 2)
        if len(parts) != 3:
            continue
        path, line_no, text = parts
        results.append({"path": path, "line": int(line_no), "text": text.strip()})
        if len(results) >= max_matches:
            break

    results.sort(key=lambda item: (str(item["path"]), int(item["line"])))
    return results


def _find_matches_python(
    *,
    query: str,
    root: Path,
    max_matches: int,
    max_columns: int,
) -> list[dict[str, str | int]]:
    ignored_parts = {".git", ".venv", "node_modules", "__pycache__"}
    results: list[dict[str, str | int]] = []
    needle = query.lower()
    for path in root.rglob("*"):
        if len(results) >= max_matches:
            break
        if not path.is_file():
            continue
        if path.name.endswith(".sqlite3") or any(part in ignored_parts for part in path.parts):
            continue
        try:
            with path.open("r", encoding="utf-8", errors="ignore") as file_obj:
                for line_no, line in enumerate(file_obj, start=1):
                    if needle not in line.lower():
                        continue
                    text = line.strip()
                    if len(text) > max_columns:
                        text = text[:max_columns]
                    results.append({"path": os.fspath(path), "line": line_no, "text": text})
                    if len(results) >= max_matches:
                        break
        except OSError:
            continue

    results.sort(key=lambda item: (str(item["path"]), int(item["line"])))
    return results
