from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ADR_ROOT = REPO_ROOT / "docs/adr"
REQUIRED_ADRS = {
    "ADR_ARTIFACT_001_STORAGE.md": ("SQLite", "fsync", "orphan reconciliation"),
    "ADR_ARTIFACT_002_STDIO_RPC.md": ("stdio", "length-prefixed", "restart"),
    "ADR_ARTIFACT_003_UI_RUNTIME.md": ("ExternalStoreRuntime", "Tauri", "canonical"),
    "ADR_ARTIFACT_004_EDITOR_LICENSES.md": ("fail-closed", "Handsontable", "tldraw"),
    "ADR_ARTIFACT_005_DYNAMIC_FORM_VALIDATION.md": ("unsafe-eval", "ValidatorType", "backend"),
    "ADR_ARTIFACT_006_EVIDENCE_VS_WORKSPACE_ARTIFACT.md": (
        "immutable",
        "copy",
        "sourceEvidenceRef",
    ),
}


def test_artifact_architecture_decisions_are_complete_and_traceable() -> None:
    for filename, required_terms in REQUIRED_ADRS.items():
        content = (ADR_ROOT / filename).read_text(encoding="utf-8")
        assert "- Status: Accepted" in content
        assert "- Owner: MAIN / Artifact Workspace" in content
        assert "- Last verified: 2026-07-16" in content
        assert "## Decision" in content
        assert "## Consequences" in content
        for term in required_terms:
            assert term in content
