from __future__ import annotations

import pytest

from imperaos.control_plane.models import AgentSpec, RuntimeKind
from imperaos.control_plane.registry import load_agent_spec


def _agent_spec_payload(*, runtime_kind: str) -> dict[str, object]:
    return {
        "version": "control-plane.agent/v1",
        "agent_id": "runtime-contract-agent",
        "display_name": "Runtime Contract Agent",
        "runtime_kind": runtime_kind,
        "owner": {"team": "platform", "contact": "owner"},
        "declared_actions": [],
    }


def test_runtime_kind_uses_imperaos_member_names_and_serialized_values() -> None:
    assert RuntimeKind.IMPERAOS_CORE.value == "imperaos_core"
    assert RuntimeKind.IMPERAOS_TEAM.value == "imperaos_team"


@pytest.mark.parametrize("suffix", ["core", "team"])
def test_agent_spec_rejects_former_product_runtime_kind_values(suffix: str) -> None:
    former_prefix = "bin" + "liquid"

    with pytest.raises(ValueError, match="runtime_kind"):
        AgentSpec.model_validate(
            _agent_spec_payload(runtime_kind=f"{former_prefix}_{suffix}"),
        )


def test_agent_spec_loads_example() -> None:
    spec = load_agent_spec("examples/control_plane/agent_governed_ops.yaml")

    assert spec.agent_id == "governed-ops"
    assert spec.policy_profile == "enterprise"
    assert spec.declared_actions[1].risk_class == "mutation"


def test_agent_spec_rejects_overlapping_surfaces() -> None:
    payload = {
        "version": "control-plane.agent/v1",
        "agent_id": "bad-agent",
        "display_name": "Bad Agent",
        "runtime_kind": "imperaos_core",
        "owner": {"team": "platform", "contact": "owner"},
        "allowed_surfaces": ["core_runtime"],
        "blocked_surfaces": ["core_runtime"],
        "declared_actions": [],
    }

    with pytest.raises(ValueError, match="overlap"):
        AgentSpec.model_validate(payload)


def test_agent_spec_rejects_unknown_field() -> None:
    payload = {
        "version": "control-plane.agent/v1",
        "agent_id": "bad-agent",
        "display_name": "Bad Agent",
        "runtime_kind": "imperaos_core",
        "owner": {"team": "platform", "contact": "owner"},
        "declared_actions": [],
        "unexpected": True,
    }

    with pytest.raises(ValueError, match="unexpected"):
        AgentSpec.model_validate(payload)
