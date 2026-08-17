from __future__ import annotations

import json

import pytest

from imperaos.control_plane.errors import AgentAlreadyExistsWithDifferentSpec, RegistryCorrupted
from imperaos.control_plane.registry import AgentRegistry, load_agent_spec


def test_registry_register_list_get_disable(tmp_path) -> None:
    registry = AgentRegistry(root_dir=tmp_path)
    spec = load_agent_spec("examples/control_plane/agent_governed_ops.yaml")

    result = registry.register(spec, actor="test")
    same = registry.register(spec, actor="test")
    record = registry.get("governed-ops")
    disabled = registry.disable("governed-ops", reason="test", actor="test")

    assert result.status == "registered"
    assert same.status == "unchanged"
    assert [item.agent_id for item in registry.list_agents()] == ["governed-ops"]
    assert record.spec_hash.startswith("sha256:")
    assert disabled.status == "disabled"


def test_registry_duplicate_different_spec_conflicts(tmp_path) -> None:
    registry = AgentRegistry(root_dir=tmp_path)
    spec = load_agent_spec("examples/control_plane/agent_governed_ops.yaml")
    registry.register(spec, actor="test")
    changed = spec.model_copy(update={"display_name": "Different"})

    with pytest.raises(AgentAlreadyExistsWithDifferentSpec):
        registry.register(changed, actor="test")


def test_registry_corrupted_file_is_moved_aside(tmp_path) -> None:
    registry = AgentRegistry(root_dir=tmp_path)
    registry.registry_path.write_text("{bad", encoding="utf-8")

    with pytest.raises(RegistryCorrupted):
        registry.list_agents()

    assert not registry.registry_path.exists()
    assert list(tmp_path.glob("agents.corrupt.*.json"))


def test_registry_file_contains_no_raw_secret_field(tmp_path) -> None:
    registry = AgentRegistry(root_dir=tmp_path)
    spec = load_agent_spec("examples/control_plane/agent_governed_ops.yaml")
    registry.register(spec, actor="test")

    payload = json.loads(registry.registry_path.read_text(encoding="utf-8"))
    assert "secret" not in json.dumps(payload).lower()
