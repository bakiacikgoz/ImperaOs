from pathlib import Path

from imperaos.memory.runtime_bridge import RuntimeMemoryRequest
from imperaos.memory.runtime_policy_fixtures import build_memory_runtime_policy_fixture


def test_policy_gateway_allows_authorized_read_and_writes_hash_only_evidence(
    tmp_path: Path,
) -> None:
    fixture = build_memory_runtime_policy_fixture(tmp_path, profile="enterprise")
    pack = fixture.bridge.retrieve_context(
        RuntimeMemoryRequest(
            run_id="run-policy-read",
            query="hash only policy evidence",
            actor_id="operator-main",
            requester_role="operator",
            principal_id="operator-main",
            workspace_id="workspace-main",
        )
    )

    assert pack.status == "pass"
    assert pack.evidence_ref is not None
    evidence = Path(pack.evidence_ref).read_text(encoding="utf-8")
    assert "hash only policy evidence" not in evidence
    assert '"rawContentIncluded": false' in evidence


def test_policy_gateway_strict_fail_closed_on_unknown_principal(tmp_path: Path) -> None:
    fixture = build_memory_runtime_policy_fixture(tmp_path, profile="enterprise")
    pack = fixture.bridge.retrieve_context(
        RuntimeMemoryRequest(
            run_id="run-policy-denied",
            query="provider governance",
            actor_id="missing-operator",
            requester_role="operator",
            workspace_id="workspace-main",
        )
    )

    assert pack.status == "error"
    assert pack.degraded_reason == "MEMORY_WORKSPACE_MEMBERSHIP_DENIED"


def test_policy_gateway_denies_secret_post_run_write(tmp_path: Path) -> None:
    fixture = build_memory_runtime_policy_fixture(tmp_path, profile="enterprise")
    result = fixture.bridge.propose_post_run_write(
        run_id="run-secret-write",
        actor_id="operator-main",
        role="operator",
        user_input="remember this",
        assistant_output="api_key = sk-testsecret123456789",
    )

    assert result.status == "denied"
    assert "MEMORY_RUNTIME_WRITE_SECRET_DENIED" in result.blocking_reasons
    assert result.raw_content_included is False
