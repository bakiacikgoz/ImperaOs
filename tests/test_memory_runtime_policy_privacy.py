import json
from pathlib import Path

from imperaos.memory.runtime_bridge import RuntimeMemoryRequest
from imperaos.memory.runtime_policy_fixtures import build_memory_runtime_policy_fixture


def test_memory_runtime_policy_evidence_never_contains_raw_query_or_secret(tmp_path: Path) -> None:
    fixture = build_memory_runtime_policy_fixture(tmp_path, profile="enterprise")
    fixture.bridge.retrieve_context(
        RuntimeMemoryRequest(
            run_id="privacy-read",
            query="private raw query that must not appear",
            actor_id="operator-main",
            requester_role="operator",
            principal_id="operator-main",
            workspace_id="workspace-main",
        )
    )
    fixture.bridge.propose_post_run_write(
        run_id="privacy-write",
        actor_id="operator-main",
        role="operator",
        user_input="please store",
        assistant_output="token = sk-testsecret123456789",
    )

    for path in (fixture.evidence_root / "memory-runtime-policy" / "events").glob("*.json"):
        text = path.read_text(encoding="utf-8")
        payload = json.loads(text)
        assert payload["rawContentIncluded"] is False
        assert "private raw query that must not appear" not in text
        assert "sk-testsecret" not in text
        assert "token = " not in text
