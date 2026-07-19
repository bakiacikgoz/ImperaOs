from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class GovernanceAction(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"


class GovernancePhase(StrEnum):
    TASK = "task"
    TOOL = "tool"
    HANDOFF = "handoff"
    MEMORY_WRITE = "memory_write"
    DEVICE_ACTION = "device_action"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    EXECUTED = "executed"
    CONSUMED = "consumed"
    EXECUTION_FAILED = "execution_failed"
    CANCELLED = "cancelled"


class ExecutionStatus(StrEnum):
    NOT_EXECUTED = "not_executed"
    EXECUTED = "executed"
    EXECUTION_FAILED = "execution_failed"


class ToolCallRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    command_root: str
    args_fingerprint: str
    decision_action: GovernanceAction
    reason_code: str


class HandoffCallRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    from_role: str
    to_role: str
    payload_hash: str
    decision_action: GovernanceAction
    reason_code: str


class MemoryWriteRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    scope: str
    producer_role: str
    visibility: str
    decision_action: GovernanceAction
    reason_code: str


class DeviceActionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    action_id: str
    category: str
    risk_class: str
    target_ref: str
    app_identity: str
    window_identity: str
    selector_source: str
    decision_action: GovernanceAction
    reason_code: str


class GovernanceDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    phase: GovernancePhase
    target: str
    action: GovernanceAction
    reason_code: str
    matched_rule_path: str | None = None
    policy_schema_version: str
    policy_version: str
    policy_hash: str
    decision_engine_version: str
    approval_required: bool = False
    approval_id: str | None = None
    explain: str | None = None


class ApprovalTicket(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    version: int = Field(ge=0)
    approval_id: str
    workspace_id: str = "default"
    run_id: str
    status: ApprovalStatus
    target_kind: str
    target_ref: str
    action_hash: str
    policy_hash: str
    request_hash: str
    snapshot_hash: str
    snapshot: dict[str, Any] = Field(default_factory=dict)
    expires_at: datetime
    actor: str | None = None
    decision_reason: str | None = None
    execution_status: ExecutionStatus = ExecutionStatus.NOT_EXECUTED
    executed_at: datetime | None = None
    execution_error_code: str | None = None
    executed_by: str | None = None
    execution_contract_hash: str | None = None
    resume_token_ref: str | None = None
    resume_claimed_job_id: str | None = None
    resume_claimed_at: datetime | None = None
    consumed_by_job_id: str | None = None
    consumed_at: datetime | None = None
    idempotency_key: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    decided_at: datetime | None = None


class AuditRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    schema_version: str = "1.0"
    run_id: str
    runtime_version: str
    git_commit: str | None = None
    profile: str
    model_provider: str
    model_name: str
    requested_provider: str | None = None
    requested_fallback_provider: str | None = None
    requested_model_name: str | None = None
    requested_hf_model_id: str | None = None
    selected_provider: str | None = None
    selected_model_name: str | None = None
    selected_hf_model_id: str | None = None
    fallback_used: bool = False
    config_source_model_name: str | None = None
    config_source_hf_model_id: str | None = None
    router_reason_code: str | None = None
    policy_schema_version: str
    policy_version: str
    policy_hash: str
    decision_engine_version: str
    governance_decisions: list[GovernanceDecision] = Field(default_factory=list)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    handoffs: list[HandoffCallRecord] = Field(default_factory=list)
    memory_writes: list[MemoryWriteRecord] = Field(default_factory=list)
    device_actions: list[DeviceActionRecord] = Field(default_factory=list)
    approval_status: str = "none"
    redaction_mode: str = "trace"
    privacy_mode: bool = True
    integrity: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
