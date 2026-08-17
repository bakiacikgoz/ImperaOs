import json
from pathlib import Path

from imperaos.memory.runtime_policy import AgentMemoryRuntimePolicyDecision


def test_runtime_policy_decision_fixture_validates() -> None:
    payload = json.loads(
        Path("contracts/memory/fixtures/runtime_policy_decision_pass.json").read_text(
            encoding="utf-8"
        )
    )
    decision = AgentMemoryRuntimePolicyDecision.model_validate(payload)

    assert decision.raw_content_included is False
    assert decision.action == "allow"
    assert decision.semantic_runtime_mode == "enforced"
