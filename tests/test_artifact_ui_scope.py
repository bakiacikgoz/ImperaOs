from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_artifact_workspace_styles_are_scoped_and_bridge_existing_tokens() -> None:
    css = (
        REPO_ROOT
        / "apps/operator-panel/src/artifact-workspace/artifact-workspace.css"
    ).read_text(encoding="utf-8")

    assert ".artifact-workspace {" in css
    assert "--aw-background: var(--surface-panel);" in css
    assert "--aw-destructive: var(--color-error);" in css
    assert ":root" not in css
    assert "body {" not in css
    assert "unsafe" not in css
