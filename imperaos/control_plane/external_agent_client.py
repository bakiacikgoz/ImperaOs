from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from imperaos.control_plane.agent_enrollment import EnrolledAgent
from imperaos.control_plane.enterprise_workspace import utc_now
from imperaos.control_plane.enterprise_workspace_store import EnterpriseWorkspaceStore
from imperaos.control_plane.external_contracts import ExternalActionRequest
from imperaos.control_plane.external_gateway import ExternalAgentGateway
from imperaos.control_plane.models import (
    AgentOwner,
    AgentSpec,
    DeclaredAction,
    ExecutionSurface,
    RiskClass,
    RuntimeKind,
)
from imperaos.control_plane.registry import AgentRegistry
from imperaos.runtime.config import RuntimeConfig


class ExternalAgentPilotManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    version: Literal["control-plane.external-agent-manifest/v1"] = (
        "control-plane.external-agent-manifest/v1"
    )
    agent_id: str = Field(alias="agentId")
    name: str = Field(min_length=1, max_length=120)
    owner: str = "pilot"
    transport: Literal["stdio_json"] = Field(default="stdio_json")
    risk_profile: Literal["read_only", "mutation", "destructive_denied"] = Field(
        alias="riskProfile"
    )
    policy_pack_id: str = Field(default="enterprise_default", alias="policyPackId")
    entrypoint: list[str]
    allowed_actions: list[str] = Field(default_factory=list, alias="allowedActions")
    evidence_required: bool = Field(default=True, alias="evidenceRequired")

    @field_validator("entrypoint")
    @classmethod
    def _entrypoint_safe(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("entrypoint cannot be empty")
        forbidden = {";", "&&", "||", "|", ">", "<"}
        if any(any(token in part for token in forbidden) for part in value):
            raise ValueError("entrypoint must be argv-style without shell operators")
        return value


class ExternalAgentRunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    agent_id: str = Field(alias="agentId")
    run_id: str | None = Field(default=None, alias="runId")
    policy_decision: Literal["allow", "deny", "require_approval"] = Field(
        alias="policyDecision"
    )
    reason_code: str = Field(alias="reasonCode")
    approval_id: str | None = Field(default=None, alias="approvalId")
    evidence_id: str | None = Field(default=None, alias="evidenceId")
    evidence_verify_status: Literal["valid", "invalid", "missing"] = Field(
        default="missing",
        alias="evidenceVerifyStatus",
    )
    status: str


class ExternalAgentClient:
    def __init__(
        self,
        manifest: ExternalAgentPilotManifest,
        *,
        config: RuntimeConfig,
        root_dir: Path,
    ) -> None:
        self.manifest = manifest
        self.config = config
        self.root_dir = root_dir

    def submit_action(self, action: ExternalActionRequest) -> ExternalAgentRunResponse:
        registry = AgentRegistry(root_dir=self.root_dir)
        _ensure_pilot_enrollment(root_dir=self.root_dir, manifest=self.manifest)
        registry.register(_agent_spec_from_manifest(self.manifest), actor="external-agent-client")
        gateway = ExternalAgentGateway(
            config=self.config,
            registry=registry,
            root_dir=self.root_dir,
        )
        response = gateway.submit_action(action)
        decision = "deny"
        if response.status == "accepted":
            decision = "allow"
        elif response.status in {"requires_approval", "blocked_pending_approval"}:
            decision = "require_approval"
        return ExternalAgentRunResponse(
            agentId=response.agent_id,
            runId=response.run_id,
            policyDecision=decision,
            reasonCode=response.reason_code,
            approvalId=response.approval_id,
            evidenceId=response.evidence_ref,
            evidenceVerifyStatus="valid" if response.evidence_ref else "missing",
            status=response.status,
        )


def run_external_agent_manifest(
    *,
    manifest_path: Path,
    request_path: Path,
    config: RuntimeConfig,
    root_dir: Path,
) -> ExternalAgentRunResponse:
    manifest = ExternalAgentPilotManifest.model_validate(
        json.loads(manifest_path.read_text(encoding="utf-8"))
    )
    request = ExternalActionRequest.model_validate(
        json.loads(request_path.read_text(encoding="utf-8"))
    )
    return ExternalAgentClient(manifest, config=config, root_dir=root_dir).submit_action(request)


def run_external_agent_pilot_suite(
    *,
    examples_root: Path,
    output_path: Path,
    config: RuntimeConfig,
    root_dir: Path,
) -> dict[str, Any]:
    cases = []
    expected = {
        "read_only_inventory_agent": "allow",
        "ops_remediation_agent": "require_approval",
        "destructive_blocked_agent": "deny",
    }
    for directory in sorted(path for path in examples_root.iterdir() if path.is_dir()):
        manifest = directory / "agent.json"
        request = directory / "request.json"
        if not manifest.exists() or not request.exists():
            continue
        response = run_external_agent_manifest(
            manifest_path=manifest,
            request_path=request,
            config=config,
            root_dir=root_dir,
        )
        case = {
            "case": directory.name,
            "agentId": response.agent_id,
            "policyDecision": response.policy_decision,
            "expectedDecision": expected.get(directory.name),
            "reasonCode": response.reason_code,
            "runId": response.run_id,
            "approvalId": response.approval_id,
            "evidenceId": response.evidence_id,
        }
        case["passed"] = case["policyDecision"] == case["expectedDecision"]
        cases.append(case)
    report = {
        "version": "control-plane.external-agent-pilot/v1",
        "generatedAtUtc": datetime.now(UTC).isoformat(),
        "status": "pass" if cases and all(case["passed"] for case in cases) else "fail",
        "cases": cases,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def _agent_spec_from_manifest(manifest: ExternalAgentPilotManifest) -> AgentSpec:
    workspace_id = "pilot-workspace"
    principal_id = f"principal-{manifest.agent_id}"
    device_id = f"device-{manifest.agent_id}"
    enrollment_id = f"enrollment-{manifest.agent_id}"
    risk = {
        "read_only": RiskClass.READ_ONLY,
        "mutation": RiskClass.EXTERNAL_WRITE,
        "destructive_denied": RiskClass.DESTRUCTIVE,
    }[manifest.risk_profile]
    return AgentSpec(
        version="control-plane.agent/v1",
        agent_id=manifest.agent_id,
        display_name=manifest.name,
        description="Design partner pilot external stdio JSON agent.",
        runtime_kind=RuntimeKind.EXTERNAL_STDIO,
        profile="enterprise",
        policy_profile="enterprise",
        owner=AgentOwner(team=manifest.owner, contact=f"{manifest.owner}@example.local"),
        allowed_surfaces=[ExecutionSurface.EXTERNAL_STDIO],
        blocked_surfaces=[ExecutionSurface.COMPUTER_USE_LIVE],
        declared_actions=[
            DeclaredAction(
                action_id=f"external_{action}",
                phase="tool",
                risk_class=risk if action != "read" else RiskClass.READ_ONLY,
                target_kind="external_system",
                effect=action,
            )
            for action in (manifest.allowed_actions or ["read"])
        ],
        metadata={
            "agent_type": "external_stdio",
            "policy_pack_id": manifest.policy_pack_id,
            "risk_profile": manifest.risk_profile,
            "transport": manifest.transport,
            "workspace_id": workspace_id,
            "principal_id": principal_id,
            "device_id": device_id,
            "enrollment_id": enrollment_id,
            "enrollment_status": "active",
            "workspace_binding_status": "bound",
        },
    )


def _ensure_pilot_enrollment(*, root_dir: Path, manifest: ExternalAgentPilotManifest) -> None:
    store = EnterpriseWorkspaceStore(root_dir)
    store.write_enrolled_agent(
        EnrolledAgent(
            enrollmentId=f"enrollment-{manifest.agent_id}",
            workspaceId="pilot-workspace",
            agentId=manifest.agent_id,
            principalId=f"principal-{manifest.agent_id}",
            deviceId=f"device-{manifest.agent_id}",
            tokenId=f"token-{manifest.agent_id}",
            status="active",
            capabilities=tuple(manifest.allowed_actions or ["read"]),
            policyProfile="enterprise",
            createdAtUtc=utc_now(),
        )
    )
