from __future__ import annotations

from pathlib import Path

from imperaos.control_plane.models import ActionProposal
from imperaos.control_plane.policy_simulator import PolicySimulator
from imperaos.control_plane.registry import load_agent_spec
from imperaos.runtime.config import RuntimeConfig


def _config_with_policy(tmp_path: Path) -> RuntimeConfig:
    policy = tmp_path / "policy.toml"
    policy.write_text("[policy]\n", encoding="utf-8")
    config = RuntimeConfig.from_profile("lite")
    return config.model_copy(
        update={
            "governance": config.governance.model_copy(update={"policy_path": str(policy)})
        }
    )


def test_policy_simulator_maps_mutation_to_approval(tmp_path) -> None:
    spec = load_agent_spec("examples/control_plane/agent_governed_ops.yaml")
    result = PolicySimulator(config=_config_with_policy(tmp_path)).simulate_agent(spec)

    assert result.overall_status == "conditional"
    assert result.summary.allow == 1
    assert result.summary.require_approval == 1
    assert result.decisions[1].reason_code == "RISK_REQUIRES_APPROVAL"


def test_policy_simulator_denies_missing_policy(tmp_path) -> None:
    config = RuntimeConfig.from_profile("lite")
    config = config.model_copy(
        update={
            "governance": config.governance.model_copy(
                update={"policy_path": str(tmp_path / "missing.toml")}
            )
        }
    )
    spec = load_agent_spec("examples/control_plane/agent_governed_ops.yaml")

    result = PolicySimulator(config=config).simulate_agent(spec)

    assert result.overall_status == "blocked"
    assert "POLICY_UNAVAILABLE" in result.blocking_reasons


def test_policy_simulator_action_unknown_denied(tmp_path) -> None:
    proposal = ActionProposal.model_validate(
        {
            "version": "control-plane.action-proposal/v1",
            "correlation_id": "corr",
            "run_id": "run",
            "agent_id": "agent",
            "action_id": "unknown_action",
            "target_kind": "service",
            "risk_class": "unknown",
            "effect_summary": "unknown effect",
            "idempotency_key": "idem",
        }
    )

    decision = PolicySimulator(config=_config_with_policy(tmp_path)).simulate_action(proposal)

    assert decision.decision_action == "deny"
    assert decision.reason_code == "UNKNOWN_RISK_DENIED"
