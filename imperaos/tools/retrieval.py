from __future__ import annotations

from pathlib import Path

ALLOWED_EXTENSIONS = {
    ".md",
    ".txt",
    ".py",
    ".toml",
    ".json",
    ".yaml",
    ".yml",
    ".rst",
}

EXCLUDED_PATH_PARTS = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache"}


def retrieve_top_chunks(
    query: str,
    root_dir: str | Path = ".",
    *,
    max_files: int = 80,
    max_chunks: int = 6,
    chunk_lines: int = 30,
    overlap_lines: int = 6,
) -> list[dict[str, str | int | float]]:
    root = Path(root_dir)
    if not root.exists() or not query.strip():
        return []

    tokens = [token for token in _tokenize(query) if len(token) > 1]
    if not tokens:
        return []

    candidates: list[dict[str, str | int | float]] = []
    file_count = 0
    for path in sorted(root.rglob("*")):
        if file_count >= max_files:
            break
        if not path.is_file() or path.suffix.lower() not in ALLOWED_EXTENSIONS:
            continue
        if any(part in EXCLUDED_PATH_PARTS for part in path.parts):
            continue

        file_count += 1
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue

        for chunk in _iter_chunks(lines=lines, size=chunk_lines, overlap=overlap_lines):
            score = _score_text(chunk["text"], tokens)
            if score <= 0.0:
                continue

            candidates.append(
                {
                    "path": str(path),
                    "line_start": chunk["line_start"],
                    "line_end": chunk["line_end"],
                    "score": score,
                    "text": chunk["text"],
                }
            )

    candidates.sort(
        key=lambda item: (
            -float(item["score"]),
            str(item["path"]),
            int(item["line_start"]),
        )
    )
    return candidates[:max_chunks]


def _iter_chunks(lines: list[str], size: int, overlap: int) -> list[dict[str, str | int]]:
    if not lines:
        return []
    step = max(1, size - overlap)
    result: list[dict[str, str | int]] = []
    for start in range(0, len(lines), step):
        end = min(len(lines), start + size)
        text = "\n".join(lines[start:end]).strip()
        if not text:
            continue
        result.append({"line_start": start + 1, "line_end": end, "text": text})
        if end >= len(lines):
            break
    return result


def _tokenize(text: str) -> list[str]:
    clean = (
        text.lower()
        .replace("\n", " ")
        .replace(".", " ")
        .replace(",", " ")
        .replace(":", " ")
        .replace(";", " ")
        .replace("(", " ")
        .replace(")", " ")
    )
    return [token.strip() for token in clean.split() if token.strip()]


def _score_text(text: str, tokens: list[str]) -> float:
    lower_text = text.lower()
    hits = sum(1 for token in tokens if token in lower_text)
    if hits == 0:
        return 0.0

    coverage = hits / max(len(tokens), 1)
    length_penalty = min(len(text) / 2500.0, 1.0)
    return round((coverage * 0.85) + ((1.0 - length_penalty) * 0.15), 4)
