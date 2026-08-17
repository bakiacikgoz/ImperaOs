from pathlib import Path

from imperaos.memory.runtime_bridge import RuntimeMemoryRequest
from imperaos.memory.runtime_policy_fixtures import build_memory_runtime_policy_fixture
from imperaos.memory.runtime_policy_snapshot import build_memory_policy_enforcement_snapshot


def test_control_plane_snapshot_includes_memory_policy_enforcement(tmp_path: Path) -> None:
    fixture = build_memory_runtime_policy_fixture(tmp_path, profile="enterprise")
    fixture.bridge.retrieve_context(
        RuntimeMemoryRequest(
            run_id="snapshot-policy",
            query="hash only policy evidence",
            actor_id="operator-main",
            requester_role="operator",
            principal_id="operator-main",
            workspace_id="workspace-main",
        )
    )

    snapshot = build_memory_policy_enforcement_snapshot(
        config=fixture.config,
        evidence_root=fixture.evidence_root,
    )
    payload = snapshot.model_dump(mode="json", by_alias=True)

    assert payload["enabled"] is True
    assert payload["readEventCount"] == 1
    assert payload["rawLeakCount"] == 0
