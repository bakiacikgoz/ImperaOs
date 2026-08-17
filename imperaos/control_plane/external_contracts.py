from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from imperaos.control_plane.models import ControlPlanePolicyDecision, StrictModel


class ExternalActionRequest(StrictModel):
    version: Literal["control-plane.external-action-request/v1"] = (
        "control-plane.external-action-request/v1"
    )
    request_id: str = Field(alias="requestId")
    agent_id: str = Field(alias="agentId")
    actor_id: str = Field(alias="actorId")
    intent: str = Field(min_length=1, max_length=500)
    action_kind: Literal[
        "read",
        "mutate",
        "external_write",
        "destructive",
        "credential_sensitive",
        "unknown",
    ] = Field(alias="actionKind")
    target_ref: str | None = Field(default=None, alias="targetRef")
    payload_hash: str = Field(alias="payloadHash")
    payload_redaction_summary: dict[str, Any] = Field(
        default_factory=dict,
        alias="payloadRedactionSummary",
    )
    requested_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        alias="requestedAt",
    )
    dry_run: bool = Field(default=True, alias="dryRun")

    @field_validator("request_id")
    @classmethod
    def _request_id_valid(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{2,127}", value):
            raise ValueError("request_id must be a stable external idempotency key")
        return value

    @field_validator("agent_id")
    @classmethod
    def _agent_id_valid(cls, value: str) -> str:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,62}[a-z0-9]", value):
            raise ValueError("agent_id must be kebab-case and 3-64 chars")
        return value

    @field_validator("payload_hash")
    @classmethod
    def _payload_hash_valid(cls, value: str) -> str:
        if not re.fullmatch(r"sha256:[a-fA-F0-9]{64}", value):
            raise ValueError("payload_hash must be sha256:<64 hex chars>")
        return value.lower()


class ExternalActionResponse(StrictModel):
    version: Literal["control-plane.external-action-response/v1"] = (
        "control-plane.external-action-response/v1"
    )
    request_id: str = Field(alias="requestId")
    agent_id: str = Field(alias="agentId")
    status: Literal[
        "accepted",
        "requires_approval",
        "blocked_pending_approval",
        "denied",
        "invalid_request",
        "unknown_agent",
    ]
    reason_code: str = Field(alias="reasonCode")
    policy_decision: ControlPlanePolicyDecision | None = Field(
        default=None,
        alias="policyDecision",
    )
    run_id: str | None = Field(default=None, alias="runId")
    approval_id: str | None = Field(default=None, alias="approvalId")
    evidence_ref: str | None = Field(default=None, alias="evidenceRef")
    dry_run: bool = Field(alias="dryRun")
    next_actions: list[str] = Field(default_factory=list, alias="nextActions")
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        alias="generatedAt",
    )


class ExternalAgentActionV11(StrictModel):
    action_id: str = Field(alias="actionId")
    kind: Literal[
        "read",
        "mutate",
        "external_write",
        "destructive",
        "credential_sensitive",
        "unknown",
    ] = "unknown"
    target_ref: str | None = Field(default=None, alias="targetRef")
    effect: str = Field(default="", max_length=500)

    @field_validator("action_id")
    @classmethod
    def _action_id_valid(cls, value: str) -> str:
        if not re.fullmatch(r"[a-z0-9][a-z0-9_.:-]{1,127}", value):
            raise ValueError("action_id must be a stable lowercase action key")
        return value


class ExternalAgentRequestV11(StrictModel):
    version: Literal["control-plane.external-agent-request/v1.1"] = (
        "control-plane.external-agent-request/v1.1"
    )
    request_id: str = Field(alias="requestId")
    agent_id: str = Field(alias="agentId")
    workflow_id: str = Field(alias="workflowId")
    intent: str = Field(min_length=1, max_length=500)
    actions: list[ExternalAgentActionV11] = Field(default_factory=list)
    idempotency_key: str = Field(alias="idempotencyKey")
    requested_by: str = Field(alias="requestedBy")
    risk_hint: Literal[
        "read_only",
        "mutation",
        "destructive",
        "external_write",
        "credential_sensitive",
        "unknown",
    ] = Field(default="unknown", alias="riskHint")
    metadata: dict[str, Any] = Field(default_factory=dict)
    requested_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        alias="requestedAt",
    )
    dry_run: bool = Field(default=False, alias="dryRun")

    @field_validator("request_id", "idempotency_key")
    @classmethod
    def _stable_id_valid(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{2,127}", value):
            raise ValueError("stable ids must be 3-128 characters")
        return value

    @field_validator("agent_id")
    @classmethod
    def _agent_id_valid(cls, value: str) -> str:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,62}[a-z0-9]", value):
            raise ValueError("agent_id must be kebab-case and 3-64 chars")
        return value

    @model_validator(mode="after")
    def _validate_actions_and_metadata(self) -> ExternalAgentRequestV11:
        if not self.actions:
            raise ValueError("actions cannot be empty")
        for key in self.metadata:
            lowered = str(key).lower()
            sensitive_markers = {"secret", "token", "password", "private_key", "api_key"}
            if any(marker in lowered for marker in sensitive_markers):
                raise ValueError("metadata cannot include sensitive key names")
        return self


class ExternalAgentV11Result(StrictModel):
    version: Literal["control-plane.external-agent-result/v1.1"] = (
        "control-plane.external-agent-result/v1.1"
    )
    request_id: str = Field(alias="requestId")
    agent_id: str = Field(alias="agentId")
    workflow_id: str = Field(alias="workflowId")
    status: Literal[
        "accepted",
        "blocked_pending_approval",
        "denied",
        "invalid_request",
        "unknown_agent",
    ]
    reason_code: str = Field(alias="reasonCode")
    policy_decision: Literal["allow", "deny", "require_approval", "unknown"] = Field(
        alias="policyDecision"
    )
    run_id: str | None = Field(default=None, alias="runId")
    approval_id: str | None = Field(default=None, alias="approvalId")
    evidence_ref: str | None = Field(default=None, alias="evidenceRef")
    replay_status: Literal["recorded", "replayed", "verified", "mismatch", "missing"] = Field(
        alias="replayStatus"
    )
    idempotency_status: Literal["created", "replayed", "conflict"] = Field(
        alias="idempotencyStatus"
    )
    request_hash: str = Field(alias="requestHash")
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        alias="generatedAt",
    )
