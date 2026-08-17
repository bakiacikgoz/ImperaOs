from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from imperaos.cli import app
from imperaos.control_plane.agent_enrollment import EnrolledAgent
from imperaos.control_plane.enterprise_workspace import (
    EnterpriseDevice,
    EnterprisePrincipal,
    hash_identity_ref,
    utc_now,
)
from imperaos.control_plane.enterprise_workspace_store import EnterpriseWorkspaceStore
from imperaos.control_plane.external_contracts import (
    ExternalAgentActionV11,
    ExternalAgentRequestV11,
)
from imperaos.control_plane.external_gateway import ExternalAgentGateway
from imperaos.control_plane.registry import AgentRegistry, load_agent_spec
from imperaos.runtime.config import RuntimeConfig

runner = CliRunner()
REPO_ROOT = Path(__file__).resolve().parents[1]


def test_external_gateway_v1_1_accepts_read_only_and_replays_idempotently(
    tmp_path: Path,
) -> None:
    gateway = _gateway(tmp_path)
    request = _request("read-only", kind="read", risk_hint="read_only")

    response = gateway.submit_action_v1_1(request)
    replayed = gateway.submit_action_v1_1(request)

    assert response.status == "accepted"
    assert response.policy_decision == "allow"
    assert response.replay_status == "recorded"
    assert response.idempotency_status == "created"
    assert replayed.status == response.status
    assert replayed.run_id == response.run_id
    assert replayed.replay_status == "replayed"
    assert replayed.idempotency_status == "replayed"
    runs = list((tmp_path / "cp" / "runs").glob("*.json"))
    assert len(runs) == 1

    verified = gateway.replay_v1_1(
        request_id=request.request_id,
        expected_request_hash=response.request_hash,
    )
    assert verified["status"] == "verified"
    mismatch = gateway.replay_v1_1(
        request_id=request.request_id,
        expected_request_hash="sha256:000",
    )
    assert mismatch["status"] == "mismatch"


def test_external_gateway_v1_1_rejects_idempotency_conflict(tmp_path: Path) -> None:
    gateway = _gateway(tmp_path)
    first = _request("dup", kind="read", risk_hint="read_only", idempotency_key="same-key")
    second = _request(
        "dup-changed",
        kind="read",
        risk_hint="read_only",
        idempotency_key="same-key",
    )

    accepted = gateway.submit_action_v1_1(first)
    conflict = gateway.submit_action_v1_1(second)

    assert accepted.status == "accepted"
    assert conflict.status == "invalid_request"
    assert conflict.reason_code == "EXTERNAL_AGENT_DUPLICATE_REQUEST"
    assert conflict.replay_status == "mismatch"
    assert conflict.idempotency_status == "conflict"


def test_external_gateway_v1_1_requires_approval_for_external_write(
    tmp_path: Path,
) -> None:
    response = _gateway(tmp_path).submit_action_v1_1(
        _request("write", kind="external_write", risk_hint="external_write")
    )

    assert response.status == "blocked_pending_approval"
    assert response.policy_decision == "require_approval"
    assert response.approval_id is not None


def test_external_gateway_v1_1_denies_destructive_and_unknown_risk(
    tmp_path: Path,
) -> None:
    gateway = _gateway(tmp_path)

    destructive = gateway.submit_action_v1_1(
        _request("delete", kind="destructive", risk_hint="destructive")
    )
    unknown = gateway.submit_action_v1_1(
        _request("unknown", kind="unknown", risk_hint="unknown")
    )

    assert destructive.status == "denied"
    assert destructive.reason_code == "RISK_DENIED"
    assert unknown.status == "denied"
    assert unknown.reason_code == "UNKNOWN_RISK_DENIED"


def test_external_gateway_v1_1_contract_rejects_sensitive_metadata() -> None:
    with pytest.raises(ValueError):
        _request(
            "unsafe",
            kind="read",
            risk_hint="read_only",
            metadata={"api_key": "redacted"},
        )


def test_external_gateway_v1_1_cli_submit_and_replay(tmp_path: Path) -> None:
    root_dir = tmp_path / "cp"
    registry = AgentRegistry(root_dir=root_dir)
    registry.register(
        load_agent_spec(REPO_ROOT / "examples/control_plane/agent_external_gateway.yaml"),
        actor="test",
    )
    _bind_enrollment(registry=registry, root_dir=root_dir)
    request_path = REPO_ROOT / "examples/external_agents/v1_1/read_only_inspector.json"

    submit = runner.invoke(
        app,
        [
            "control-plane",
            "gateway",
            "submit-v1-1",
            "--profile",
            "enterprise",
            "--root-dir",
            str(root_dir),
            "--input",
            str(request_path),
            "--json",
        ],
    )

    assert submit.exit_code == 0, submit.stdout
    payload = json.loads(submit.stdout)
    assert payload["status"] == "accepted"

    replay = runner.invoke(
        app,
        [
            "control-plane",
            "gateway",
            "replay-v1-1",
            "--profile",
            "enterprise",
            "--root-dir",
            str(root_dir),
            "--request-id",
            payload["requestId"],
            "--expected-request-hash",
            payload["requestHash"],
            "--json",
        ],
    )

    assert replay.exit_code == 0, replay.stdout
    assert json.loads(replay.stdout)["status"] == "verified"


def _gateway(tmp_path: Path) -> ExternalAgentGateway:
    root_dir = tmp_path / "cp"
    config = RuntimeConfig.from_profile("enterprise")
    config.governance.approval_store_path = str(root_dir / "approvals.sqlite3")
    registry = AgentRegistry(root_dir=root_dir)
    registry.register(
        load_agent_spec(REPO_ROOT / "examples/control_plane/agent_external_gateway.yaml"),
        actor="test",
    )
    _bind_enrollment(registry=registry, root_dir=root_dir)
    return ExternalAgentGateway(config=config, registry=registry, root_dir=root_dir)


def _request(
    key: str,
    *,
    kind: str,
    risk_hint: str,
    idempotency_key: str | None = None,
    metadata: dict[str, str] | None = None,
) -> ExternalAgentRequestV11:
    return ExternalAgentRequestV11(
        requestId=f"v1-1-{key}",
        agentId="external-agent",
        workflowId=f"design-partner-beta.{key}",
        intent=f"Run {key} pilot gateway scenario.",
        actions=[
            ExternalAgentActionV11(
                actionId=f"scenario.{key}",
                kind=kind,
                targetRef=f"pilot:{key}",
                effect=f"{kind} pilot scenario",
            )
        ],
        idempotencyKey=idempotency_key or f"v1-1-{key}",
        requestedBy="pilot-operator",
        riskHint=risk_hint,
        metadata=metadata or {"scenario": key},
    )


def _bind_enrollment(*, registry: AgentRegistry, root_dir: Path) -> None:
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
    store = EnterpriseWorkspaceStore(root_dir)
    store.write_principal(
        EnterprisePrincipal(
            principalId="principal-agent",
            principalType="external_agent",
            displayName="External Agent",
            status="active",
            externalSubjectRefHash=hash_identity_ref("external-agent"),
            issuerHash=hash_identity_ref("test"),
            createdAtUtc=utc_now(),
        )
    )
    store.write_device(
        EnterpriseDevice(
            deviceId="device-host-01",
            workspaceId="pilot-workspace",
            principalId="principal-agent",
            displayName="Ops Host",
            platform="linux",
            status="active",
            createdAtUtc=utc_now(),
        )
    )
    store.write_enrolled_agent(
        EnrolledAgent(
            enrollmentId="enr-test",
            workspaceId="pilot-workspace",
            agentId="external-agent",
            principalId="principal-agent",
            deviceId="device-host-01",
            tokenId="enrtok-test",
            status="active",
            capabilities=("read", "external_write"),
            policyProfile="enterprise",
            createdAtUtc=utc_now(),
        )
    )
