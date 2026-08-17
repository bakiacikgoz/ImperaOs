from __future__ import annotations

from pathlib import Path

from imperaos.control_plane.agent_registry_v2 import build_agent_registry_v2
from imperaos.control_plane.registry import AgentRegistry, load_agent_spec


def test_agent_registry_v2_maps_internal_and_external_agents(tmp_path: Path) -> None:
    registry = AgentRegistry(root_dir=tmp_path)
    registry.register(
        load_agent_spec("examples/control_plane/agent_governed_ops.yaml"),
        actor="test",
    )
    registry.register(
        load_agent_spec("examples/control_plane/agent_external_gateway.yaml"),
        actor="test",
    )

    snapshot = build_agent_registry_v2(registry)
    by_id = {agent.agent_id: agent for agent in snapshot.agents}

    assert snapshot.version == "control-plane.agent-registry/v2"
    assert by_id["governed-ops"].agent_type == "internal"
    assert by_id["governed-ops"].policy_pack_id == "active-runtime-policy"
    assert by_id["external-agent"].agent_type == "external_stdio"
    assert by_id["external-agent"].policy_pack_id == "enterprise_default"
    assert by_id["external-agent"].risk_profile == "guarded"
    assert by_id["external-agent"].last_evidence_status == "missing"
