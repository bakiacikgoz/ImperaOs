from __future__ import annotations

from pathlib import Path

from imperaos.artifacts.runtime import resolve_artifact_approval_store


def test_artifact_runtime_uses_the_configured_governance_approval_store(
    tmp_path: Path,
) -> None:
    configured = tmp_path / "configured-approvals.sqlite3"
    store = resolve_artifact_approval_store(
        "enterprise",
        env={"IMPERAOS_GOVERNANCE_APPROVAL_STORE_PATH": str(configured)},
    )
    assert store.path == configured
