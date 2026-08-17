from __future__ import annotations

from pathlib import Path

REQUIRED_GUIDES = (
    "ARTIFACT_WORKSPACE_ARCHITECTURE.md",
    "ARTIFACT_WORKSPACE_OPERATOR_GUIDE.md",
    "ARTIFACT_WORKSPACE_SECURITY_BOUNDARY.md",
    "ARTIFACT_WORKSPACE_PRIVACY_MODEL.md",
    "ARTIFACT_WORKSPACE_DATA_MODEL.md",
    "ARTIFACT_WORKSPACE_EXPORT_GUIDE.md",
    "ARTIFACT_WORKSPACE_LICENSE_GUIDE.md",
    "ARTIFACT_WORKSPACE_RECOVERY_RUNBOOK.md",
    "ARTIFACT_WORKSPACE_RELEASE_GATE.md",
    "AI_ASSISTANT_ARTIFACT_TOOL_CONTRACT.md",
)


def test_phase_24_operations_guides_are_published_without_placeholders() -> None:
    docs = Path(__file__).resolve().parents[1] / "docs"
    for name in REQUIRED_GUIDES:
        text = (docs / name).read_text(encoding="utf-8")
        assert len(text) >= 800, name
        assert "TODO" not in text
        assert "TBD" not in text


def test_release_and_recovery_guides_define_fail_closed_controls() -> None:
    docs = Path(__file__).resolve().parents[1] / "docs"
    release = (docs / "ARTIFACT_WORKSPACE_RELEASE_GATE.md").read_text(
        encoding="utf-8"
    )
    recovery = (docs / "ARTIFACT_WORKSPACE_RECOVERY_RUNBOOK.md").read_text(
        encoding="utf-8"
    )
    licenses = (docs / "ARTIFACT_WORKSPACE_LICENSE_GUIDE.md").read_text(
        encoding="utf-8"
    )
    assert "artifact_workspace.enabled" in release
    assert "run_artifact_workspace_release_gate.py" in release
    assert "NO_SHIP_REGISTER.md" in release
    assert "forward-fix" in recovery
    assert "permanent delete" in recovery
    assert "ARTIFACT_LICENSE_UNAVAILABLE" in licenses
    assert "renderer" in licenses.lower()
