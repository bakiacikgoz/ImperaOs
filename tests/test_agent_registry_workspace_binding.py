from __future__ import annotations

from pathlib import Path

from imperaos.control_plane.agent_registry_v2 import build_agent_registry_v2
from imperaos.control_plane.registry import AgentRegistry, load_agent_spec


def test_agent_registry_v2_exposes_enterprise_workspace_binding(tmp_path: Path) -> None:
    registry = AgentRegistry(root_dir=tmp_path)
    registry.register(
        load_agent_spec("examples/control_plane/agent_external_gateway.yaml"),
        actor="test",
    )
    record = registry.get("external-agent")
    registry.update_record(
        record.model_copy(
            update={
                "spec": record.spec.model_copy(
                    update={
                        "metadata": {
                            **record.spec.metadata,
                            "workspace_id": "pilot-workspace",
                            "principal_id": "principal-agent",
                            "device_id": "device-host-01",
                            "enrollment_id": "enr-test",
                            "enrollment_status": "active",
                        }
                    }
                )
            }
        )
    )

    item = build_agent_registry_v2(registry).agents[0]

    assert item.workspace_id == "pilot-workspace"
    assert item.principal_id == "principal-agent"
    assert item.device_id == "device-host-01"
    assert item.enrollment_id == "enr-test"
    assert item.enrollment_status == "active"
    assert item.workspace_binding_status == "bound"
