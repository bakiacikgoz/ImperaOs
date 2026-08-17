from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FAMILY_ONE = "bin" + "liquid"
FAMILY_TWO = "ae" + "gis"
CANONICAL_DOCUMENT_PATHS = (
    "docs/IMPERAOS_ENTERPRISE_THEME_SYSTEM_v1.md",
    "docs/IMPERAOS_V0.2X_KAPSAMLI_DURUM_RAPORU_2026-03-01.md",
)
COMPATIBILITY_DOCUMENTS = {
    "README.md",
    "docs/APPROVAL_EXECUTION_RUNBOOK.md",
    "docs/DESKTOP_IDENTITY_MIGRATION.md",
}


def _tracked_documents() -> tuple[str, ...]:
    result = subprocess.run(
        ["git", "ls-files", "--", "*.md", "*.txt"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return tuple(path for path in result.stdout.splitlines() if path)


def test_tracked_documentation_uses_only_imperaos_identity() -> None:
    tracked_documents = _tracked_documents()
    assert tracked_documents

    violations: list[str] = []
    former_families = (FAMILY_ONE.casefold(), FAMILY_TWO.casefold())
    for relative_path in tracked_documents:
        if relative_path in COMPATIBILITY_DOCUMENTS:
            continue
        path_identity = relative_path.casefold()
        content_identity = (REPO_ROOT / relative_path).read_text(
            encoding="utf-8-sig"
        ).casefold()
        for family in former_families:
            if family in path_identity:
                violations.append(f"path: {relative_path}")
            if family in content_identity:
                violations.append(f"content: {relative_path}")

    assert violations == [], "former documentation identities:\n" + "\n".join(
        violations
    )


def test_canonical_document_paths_and_readme_examples_exist() -> None:
    tracked_documents = set(_tracked_documents())
    assert set(CANONICAL_DOCUMENT_PATHS) <= tracked_documents

    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8-sig")
    assert "uv run imperaos" in readme
    assert ".imperaos" in readme
    assert "IMPERAOS_" in readme
