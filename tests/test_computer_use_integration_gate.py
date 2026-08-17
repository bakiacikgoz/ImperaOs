from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[1]
GATE_PATH = REPO_ROOT / "scripts" / "evaluate_computer_use_integration_gate.py"


def _load_gate() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "evaluate_computer_use_integration_gate",
        GATE_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_computer_use_integration_gate_current_path_is_merge_ready() -> None:
    gate = _load_gate()
    report = gate.evaluate_integration_gate(
        repo=REPO_ROOT,
        profile="balanced",
        path_check_mode="current-only",
    )

    assert report["status"] == "pass"
    assert report["merge_ready"] is True
    assert report["checks"]["console_entrypoints"] is True
    assert report["checks"]["operator_contract"] is True
    assert report["checks"]["security_invariants"] is True
    assert report["defaults"]["checks"]["vision_enabled"]["value"] is False
    assert report["defaults"]["checks"]["raw_screenshot_max_count"]["value"] == 0
    assert report["release_status"]["public_live_claims"] == "blocked"
    assert "live_macos_qualification_missing" in report["release_status"]["live_blockers"]
    assert report["platform_gates"]["live_macos_qualification_blocks_foundation_merge"] is False


def test_computer_use_integration_gate_markdown_contains_stop_go_fields() -> None:
    gate = _load_gate()
    report = gate.evaluate_integration_gate(
        repo=REPO_ROOT,
        profile="balanced",
        path_check_mode="current-only",
    )
    markdown = gate.render_markdown(report)

    assert "# Computer-Use Integration Gate" in markdown
    assert "Merge ready" in markdown
    assert "Public live claims" in markdown
    assert "live_macos_qualification_missing" in markdown


def test_copy_repo_excludes_legacy_and_current_state_roots(tmp_path: Path) -> None:
    gate = _load_gate()
    legacy_state_root = "." + "bin" + "liquid"
    current_state_root = ".imperaos"
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    (source / "keep.txt").write_text("keep", encoding="utf-8")
    for state_root in (legacy_state_root, current_state_root):
        state_dir = source / state_root
        state_dir.mkdir()
        (state_dir / "sentinel.txt").write_text("state", encoding="utf-8")

    gate._copy_repo(source, destination)

    assert (destination / "keep.txt").read_text(encoding="utf-8") == "keep"
    assert not (destination / legacy_state_root).exists()
    assert not (destination / current_state_root).exists()
