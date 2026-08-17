from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class ApprovalSnapshotV2(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: Literal["approval.snapshot/v2"] = "approval.snapshot/v2"
    kind: str
    run_id: str
    policy_hash: str


class TaskApprovalSnapshot(ApprovalSnapshotV2):
    kind: Literal["task"] = "task"
    task_type: str
    user_input: str
    workspace_id: str = "default"


class ControlPlaneActionSnapshot(ApprovalSnapshotV2):
    kind: Literal["control_plane_action"] = "control_plane_action"
    agent_id: str
    action_id: str
    proposal_ref: str
    proposal_hash: str
    input_hash: str
    runtime_version: str


class ExternalAgentActionSnapshot(ApprovalSnapshotV2):
    kind: Literal["external_agent_action"] = "external_agent_action"
    agent_id: str
    action_id: str
    request_ref: str
    request_hash: str
    idempotency_key: str


class DeviceActionSnapshot(ApprovalSnapshotV2):
    kind: Literal["device_action"] = "device_action"
    action_id: str
    observation_hash: str
    action_hash: str
    observed_at_utc: str
    qualification_ref: str


ApprovalSnapshot = (
    TaskApprovalSnapshot
    | ControlPlaneActionSnapshot
    | ExternalAgentActionSnapshot
    | DeviceActionSnapshot
)

_MODELS = {
    "task": TaskApprovalSnapshot,
    "control_plane_action": ControlPlaneActionSnapshot,
    "external_agent_action": ExternalAgentActionSnapshot,
    "device_action": DeviceActionSnapshot,
}


def parse_approval_snapshot(value: dict[str, Any] | ApprovalSnapshot) -> ApprovalSnapshot:
    if isinstance(value, ApprovalSnapshotV2):
        return value
    if value.get("schema_version") != "approval.snapshot/v2":
        raise ValueError("APPROVAL_SNAPSHOT_SCHEMA_UNSUPPORTED")
    model = _MODELS.get(str(value.get("kind")))
    if model is None:
        raise ValueError("APPROVAL_SNAPSHOT_SCHEMA_UNSUPPORTED: unknown kind")
    try:
        return model.model_validate(value)
    except Exception as exc:
        raise ValueError(f"approval snapshot validation failed: {exc}") from exc


def canonical_approval_payload(value: dict[str, Any] | ApprovalSnapshot) -> bytes:
    snapshot = parse_approval_snapshot(value)
    return json.dumps(
        snapshot.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def compute_approval_request_hash(value: dict[str, Any] | ApprovalSnapshot) -> str:
    return hashlib.sha256(canonical_approval_payload(value)).hexdigest()
