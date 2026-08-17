from __future__ import annotations

from pathlib import Path

from imperaos.control_plane.external_contracts import ExternalActionRequest
from imperaos.control_plane.external_gateway import ExternalAgentGateway
from imperaos.control_plane.registry import AgentRegistry, load_agent_spec
from imperaos.runtime.config import RuntimeConfig


def test_external_gateway_denies_unenrolled_external_agent(tmp_path: Path) -> None:
    root_dir = tmp_path / "cp"
    config = RuntimeConfig.from_profile("enterprise")
    config.governance.approval_store_path = str(root_dir / "approvals.sqlite")
    registry = AgentRegistry(root_dir=root_dir)
    registry.register(
        load_agent_spec("examples/control_plane/agent_external_gateway.yaml"),
        actor="test",
    )

    response = ExternalAgentGateway(
        config=config,
        registry=registry,
        root_dir=root_dir,
    ).submit_action(_request())

    assert response.status == "denied"
    assert response.reason_code == "AGENT_NOT_ENROLLED"
    assert response.run_id is None


def _request() -> ExternalActionRequest:
    return ExternalActionRequest.model_validate_json(
        Path("contracts/control_plane/fixtures/external_agent_read_only_request.json").read_text(
            encoding="utf-8"
        )
    )
