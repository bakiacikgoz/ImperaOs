from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GIT = shutil.which("git")

CANONICAL_SURFACES = {
    "imperaos/core/orchestrator.py": (
        "You are ImperaOS assistant in product mode.",
        "You are ImperaOS response synthesizer.",
    ),
    "imperaos/computer_use/adapters/browser_adapter.py": (
        '"User-Agent": "ImperaOS/real-acceptance"',
    ),
    "imperaos/computer_use/runtime.py": (
        "Run ImperaOS computer-use on a macOS pilot machine.",
    ),
    "imperaos/computer_use/vision_runtime/qualification.py": (
        "I understand ImperaOS will control my macOS desktop",
        "<title>ImperaOS Local Fixture</title>",
    ),
    "apps/operator-panel/src/routeCapabilityMatrix.ts": (
        "imperaos control-plane agent register",
        "imperaos operator snapshot",
    ),
    "apps/operator-panel/src/components/control-plane/AgentRegistryView.tsx": (
        "imperaos control-plane agent register",
    ),
    "contracts/control_plane/fixtures/pilot_ops_drill_pass.json": (
        "imperaos config resolve --profile enterprise",
    ),
    "contracts/operator_panel/fixtures/operator_panel_preview.json": (
        "./support/imperaos-support.zip",
    ),
    "tests/test_enterprise_workspace_remote_pr_ci_gate.py": (
        "https://github.com/bakiacikgoz/ImperaOS/pull/42",
    ),
    "tests/test_windows_release_gate.py": (
        "imperaos-0.4.1-py3-none-any.whl",
    ),
}


def _former(*parts: str) -> str:
    return "".join(parts)


def _tracked_paths() -> list[Path]:
    assert GIT is not None, "git is required for the final identity test"
    result = subprocess.run(
        [GIT, "-C", str(REPO_ROOT), "ls-files", "-z"],
        check=True,
        capture_output=True,
    )
    return [REPO_ROOT / item.decode("utf-8") for item in result.stdout.split(b"\0") if item]


def test_tracked_text_and_paths_do_not_publish_former_product_families() -> None:
    forbidden = (_former("bin", "liquid"), _former("ae", "gis"))
    findings: list[str] = []

    for path in _tracked_paths():
        relative = path.relative_to(REPO_ROOT).as_posix()
        if relative.startswith("binliquid/") or relative in {
            "README.md",
            "pyproject.toml",
            "imperaos/migration/legacy_state.py",
            "imperaos/cli.py",
            "tests/test_imperaos_entrypoints.py",
            "tests/test_legacy_state_migration.py",
            "tests/test_distribution_wheel.py",
            "tests/test_console_entrypoint_unicode_path.py",
            "tests/test_final_identity_surfaces.py",
            "docs/DESKTOP_IDENTITY_MIGRATION.md",
        }:
            continue
        normalized_path = relative.casefold()
        for token in forbidden:
            if token in normalized_path:
                findings.append(f"path:{relative}:{token}")

        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        normalized_text = text.casefold()
        for token in forbidden:
            if token in normalized_text:
                findings.append(f"content:{relative}:{token}")

    assert findings == []


def test_canonical_runtime_fixture_command_url_and_archive_surfaces() -> None:
    missing: list[str] = []

    for relative, expected_fragments in CANONICAL_SURFACES.items():
        source = (REPO_ROOT / relative).read_text(encoding="utf-8")
        for fragment in expected_fragments:
            if fragment not in source:
                missing.append(f"{relative}: {fragment}")

    assert missing == []


def test_canonical_state_directory_is_the_only_product_state_ignore() -> None:
    ignored = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    former_state_root = f".{_former('bin', 'liquid')}/"

    assert ".imperaos/" in ignored
    assert former_state_root not in ignored
