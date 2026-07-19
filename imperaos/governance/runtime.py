from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from imperaos import __version__
from imperaos.enterprise.signing import build_integrity
from imperaos.governance.approval_store import ApprovalDecisionResult, ApprovalStore
from imperaos.governance.models import (
    ApprovalStatus,
    ApprovalTicket,
    AuditRecord,
    DeviceActionRecord,
    ExecutionStatus,
    GovernanceAction,
    GovernanceDecision,
    GovernancePhase,
    HandoffCallRecord,
    MemoryWriteRecord,
    ToolCallRecord,
)
from imperaos.governance.policy import (
    PolicyBundle,
    evaluate_handoff,
    evaluate_memory_scope_write,
    evaluate_task,
    evaluate_tool,
    load_policy,
    normalize_command,
)
from imperaos.governance.redaction import (
    fingerprint_args,
    redact_audit_payload,
    redact_trace_payload,
)
from imperaos.runtime.config import GovernanceConfig, RuntimeConfig


@dataclass(slots=True)
class GovernanceRunState:
    decisions: list[GovernanceDecision] = field(default_factory=list)
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    handoffs: list[HandoffCallRecord] = field(default_factory=list)
    memory_writes: list[MemoryWriteRecord] = field(default_factory=list)
    device_actions: list[DeviceActionRecord] = field(default_factory=list)
    approval_status: str = "none"


class GovernanceRuntime:
    def __init__(self, *, config: RuntimeConfig):
        self._config = config
        self._gov = config.governance
        self._policy_bundle: PolicyBundle | None = None
        self._policy_error: str | None = None
        self._runs: dict[str, GovernanceRunState] = {}
        self._run_workspaces: dict[str, str] = {}
        self._approval_store = ApprovalStore(self._gov.approval_store_path)
        self._audit_dir = Path(self._gov.audit_dir)
        self._audit_dir.mkdir(parents=True, exist_ok=True)
        self._load_policy()

    @property
    def enabled(self) -> bool:
        return self._gov.enabled

    @property
    def policy_available(self) -> bool:
        return self._policy_bundle is not None

    @property
    def policy_error(self) -> str | None:
        return self._policy_error

    @property
    def approval_store(self) -> ApprovalStore:
        return self._approval_store

    @property
    def policy_hash(self) -> str:
        if self._policy_bundle is None:
            return "disabled"
        return self._policy_bundle.policy_hash

    def _approval_workspace_id(self) -> str:
        return self._config.memory.workspace_authority.default_workspace_id

    def get_approval(
        self,
        approval_id: str,
        *,
        workspace_id: str | None = None,
        run_id: str | None = None,
    ) -> ApprovalTicket | None:
        effective_workspace = self._workspace_for_run(run_id, workspace_id)
        if not effective_workspace:
            return None
        return self._approval_store.get(
            approval_id, workspace_id=effective_workspace
        )

    def _workspace_for_run(
        self, run_id: str | None, workspace_id: str | None = None
    ) -> str:
        explicit = (workspace_id or "").strip()
        if explicit:
            if run_id:
                self._run_workspaces[run_id] = explicit
            return explicit
        if run_id and run_id in self._run_workspaces:
            return self._run_workspaces[run_id]
        return self._approval_workspace_id().strip()

    def _load_policy(self) -> None:
        if not self._gov.enabled:
            return
        try:
            self._policy_bundle = load_policy(self._gov.policy_path)
            self._policy_error = None
        except Exception as exc:  # noqa: BLE001
            self._policy_bundle = None
            self._policy_error = str(exc)

    def execution_startup_error(self) -> str | None:
        if not self._gov.enabled:
            return None
        if self._policy_bundle is not None:
            return None
        if self._gov.policy_fail_mode == "fail_closed":
            return self._policy_error or "POLICY_UNAVAILABLE"
        return None

    def evaluate_task(
        self,
        *,
        run_id: str,
        task_type: str,
        user_input: str,
        override_approval_id: str | None = None,
        execution_contract_hash: str | None = None,
        resume_token_ref: str | None = None,
        workspace_id: str | None = None,
    ) -> tuple[GovernanceDecision, ApprovalTicket | None]:
        effective_workspace = self._workspace_for_run(run_id, workspace_id)
        if not self._gov.enabled:
            decision = self._default_allow_decision(phase=GovernancePhase.TASK, target=task_type)
            return decision, None
        if self._policy_bundle is None:
            decision = GovernanceDecision(
                phase=GovernancePhase.TASK,
                target=task_type,
                action=GovernanceAction.DENY,
                reason_code="POLICY_UNAVAILABLE",
                matched_rule_path=None,
                policy_schema_version="unavailable",
                policy_version="unavailable",
                policy_hash="unavailable",
                decision_engine_version=self._gov.decision_engine_version,
                explain=self._policy_error,
            )
            self._record_decision(run_id, decision)
            return decision, None

        target_ref = task_type
        action_hash = self._task_action_hash(task_type=task_type, user_input=user_input)
        override_ticket = self._consume_override_ticket(
            approval_id=override_approval_id,
            run_id=run_id,
            target_kind="task",
            target_ref=target_ref,
            action_hash=action_hash,
            policy_hash=self._policy_bundle.policy_hash,
            execution_contract_hash=execution_contract_hash,
            resume_token_ref=resume_token_ref,
            workspace_id=effective_workspace,
        )
        if override_ticket is not None:
            decision = GovernanceDecision(
                phase=GovernancePhase.TASK,
                target=task_type,
                action=GovernanceAction.ALLOW,
                reason_code="APPROVAL_OVERRIDE",
                matched_rule_path="approval_override",
                policy_schema_version=self._policy_bundle.policy.policy_schema_version,
                policy_version=self._policy_bundle.policy.policy_version,
                policy_hash=self._policy_bundle.policy_hash,
                decision_engine_version=self._gov.decision_engine_version,
                approval_required=False,
                approval_id=override_ticket.approval_id,
                explain="executed approval override validated",
            )
            self._set_approval_status(run_id, "validated")
            self._record_decision(run_id, decision)
            return decision, None
        if override_approval_id:
            override_error = self._override_error_code(
                approval_id=override_approval_id,
                run_id=run_id,
                target_kind="task",
                target_ref=target_ref,
                action_hash=action_hash,
                policy_hash=self._policy_bundle.policy_hash,
                execution_contract_hash=execution_contract_hash,
                resume_token_ref=resume_token_ref,
                workspace_id=effective_workspace,
            )
            if override_error is not None:
                decision = GovernanceDecision(
                    phase=GovernancePhase.TASK,
                    target=task_type,
                    action=GovernanceAction.DENY,
                    reason_code=override_error,
                    matched_rule_path="approval_override",
                    policy_schema_version=self._policy_bundle.policy.policy_schema_version,
                    policy_version=self._policy_bundle.policy.policy_version,
                    policy_hash=self._policy_bundle.policy_hash,
                    decision_engine_version=self._gov.decision_engine_version,
                    explain="approval override validation failed",
                )
                self._record_decision(run_id, decision)
                return decision, None

        match = evaluate_task(self._policy_bundle.policy, task_type=task_type)
        decision = GovernanceDecision(
            phase=GovernancePhase.TASK,
            target=task_type,
            action=match.action,
            reason_code=match.reason_code,
            matched_rule_path=match.matched_rule_path,
            policy_schema_version=self._policy_bundle.policy.policy_schema_version,
            policy_version=self._policy_bundle.policy.policy_version,
            policy_hash=self._policy_bundle.policy_hash,
            decision_engine_version=self._gov.decision_engine_version,
            approval_required=match.action == GovernanceAction.REQUIRE_APPROVAL,
            explain=match.explain,
        )

        ticket: ApprovalTicket | None = None
        if decision.action == GovernanceAction.REQUIRE_APPROVAL:
            request_hash = self._hash_payload({"task_type": task_type, "user_input": user_input})
            snapshot = {
                "kind": "task",
                "target_kind": "task",
                "target_ref": target_ref,
                "action_hash": action_hash,
                "task_type": task_type,
                "user_input": user_input,
                "policy_hash": self._policy_bundle.policy_hash,
            }
            snapshot_hash = self._hash_payload(snapshot)
            ticket = self._approval_store.create_ticket(
                workspace_id=effective_workspace,
                run_id=run_id,
                target_kind="task",
                target_ref=target_ref,
                action_hash=action_hash,
                policy_hash=self._policy_bundle.policy_hash,
                request_hash=request_hash,
                snapshot_hash=snapshot_hash,
                snapshot=snapshot,
                ttl_seconds=self._gov.approval_ttl_seconds,
                idempotency_key=f"task:{run_id}:{snapshot_hash}",
            )
            decision = decision.model_copy(update={"approval_id": ticket.approval_id})
            self._set_approval_status(run_id, "pending")

        self._record_decision(run_id, decision)
        return decision, ticket

    def evaluate_tool_command(
        self,
        *,
        run_id: str,
        command: list[str],
        workdir: str | Path,
    ) -> tuple[GovernanceDecision, ApprovalTicket | None, list[str]]:
        if not self._gov.enabled:
            decision = self._default_allow_decision(phase=GovernancePhase.TOOL, target="")
            return decision, None, command[1:]
        if self._policy_bundle is None:
            decision = GovernanceDecision(
                phase=GovernancePhase.TOOL,
                target=command[0] if command else "",
                action=GovernanceAction.DENY,
                reason_code="POLICY_UNAVAILABLE",
                matched_rule_path=None,
                policy_schema_version="unavailable",
                policy_version="unavailable",
                policy_hash="unavailable",
                decision_engine_version=self._gov.decision_engine_version,
                explain=self._policy_error,
            )
            self._record_decision(run_id, decision)
            return decision, None, command[1:]

        command_root, normalized_args = normalize_command(command, workdir=workdir)
        match = evaluate_tool(
            self._policy_bundle.policy,
            command_root=command_root,
            args=normalized_args,
        )
        decision = GovernanceDecision(
            phase=GovernancePhase.TOOL,
            target=command_root,
            action=match.action,
            reason_code=match.reason_code,
            matched_rule_path=match.matched_rule_path,
            policy_schema_version=self._policy_bundle.policy.policy_schema_version,
            policy_version=self._policy_bundle.policy.policy_version,
            policy_hash=self._policy_bundle.policy_hash,
            decision_engine_version=self._gov.decision_engine_version,
            approval_required=match.action == GovernanceAction.REQUIRE_APPROVAL,
            explain=match.explain,
        )
        ticket: ApprovalTicket | None = None
        if match.action == GovernanceAction.REQUIRE_APPROVAL:
            action_hash = self._tool_action_hash(
                command_root=command_root,
                normalized_args=normalized_args,
                policy_hash=self._policy_bundle.policy_hash,
            )
            snapshot = {
                "kind": "tool",
                "target_kind": "tool",
                "target_ref": command_root,
                "action_hash": action_hash,
                "command": command,
                "normalized": [command_root, *normalized_args],
                "policy_hash": self._policy_bundle.policy_hash,
            }
            request_hash = self._hash_payload(snapshot["normalized"])
            snapshot_hash = self._hash_payload(snapshot)
            ticket = self._approval_store.create_ticket(
                workspace_id=self._workspace_for_run(run_id),
                run_id=run_id,
                target_kind="tool",
                target_ref=command_root,
                action_hash=action_hash,
                policy_hash=self._policy_bundle.policy_hash,
                request_hash=request_hash,
                snapshot_hash=snapshot_hash,
                snapshot=snapshot,
                ttl_seconds=self._gov.approval_ttl_seconds,
                idempotency_key=f"tool:{run_id}:{snapshot_hash}",
            )
            decision = decision.model_copy(update={"approval_id": ticket.approval_id})
            self._set_approval_status(run_id, "pending")

        tool_record = ToolCallRecord(
            command_root=command_root,
            args_fingerprint=fingerprint_args(
                normalized_args,
                pii_patterns=self._policy_bundle.policy.pii_rules.patterns,
            ),
            decision_action=decision.action,
            reason_code=decision.reason_code,
        )
        self._record_tool_call(run_id, tool_record)
        self._record_decision(run_id, decision)
        return decision, ticket, normalized_args

    def evaluate_handoff(
        self,
        *,
        run_id: str,
        from_role: str,
        to_role: str,
        payload: dict[str, Any],
        override_approval_id: str | None = None,
        execution_contract_hash: str | None = None,
        resume_token_ref: str | None = None,
    ) -> tuple[GovernanceDecision, ApprovalTicket | None]:
        if not self._gov.enabled:
            decision = self._default_allow_decision(
                phase=GovernancePhase.HANDOFF,
                target=f"{from_role}->{to_role}",
            )
            return decision, None
        if self._policy_bundle is None:
            decision = GovernanceDecision(
                phase=GovernancePhase.HANDOFF,
                target=f"{from_role}->{to_role}",
                action=GovernanceAction.DENY,
                reason_code="POLICY_UNAVAILABLE",
                matched_rule_path=None,
                policy_schema_version="unavailable",
                policy_version="unavailable",
                policy_hash="unavailable",
                decision_engine_version=self._gov.decision_engine_version,
                explain=self._policy_error,
            )
            self._record_decision(run_id, decision)
            return decision, None

        payload_hash = self._hash_payload(payload)
        target_ref = f"{from_role}->{to_role}"
        action_hash = self._handoff_action_hash(
            from_role=from_role,
            to_role=to_role,
            payload_hash=payload_hash,
            policy_hash=self._policy_bundle.policy_hash,
        )
        override_ticket = self._consume_override_ticket(
            approval_id=override_approval_id,
            run_id=run_id,
            target_kind="handoff",
            target_ref=target_ref,
            action_hash=action_hash,
            policy_hash=self._policy_bundle.policy_hash,
            execution_contract_hash=execution_contract_hash,
            resume_token_ref=resume_token_ref,
        )
        if override_ticket is not None:
            decision = GovernanceDecision(
                phase=GovernancePhase.HANDOFF,
                target=target_ref,
                action=GovernanceAction.ALLOW,
                reason_code="APPROVAL_OVERRIDE",
                matched_rule_path="approval_override",
                policy_schema_version=self._policy_bundle.policy.policy_schema_version,
                policy_version=self._policy_bundle.policy.policy_version,
                policy_hash=self._policy_bundle.policy_hash,
                decision_engine_version=self._gov.decision_engine_version,
                approval_required=False,
                approval_id=override_ticket.approval_id,
                explain="executed approval override validated",
            )
            self._record_handoff(
                run_id,
                HandoffCallRecord(
                    from_role=from_role,
                    to_role=to_role,
                    payload_hash=payload_hash,
                    decision_action=decision.action,
                    reason_code=decision.reason_code,
                ),
            )
            self._set_approval_status(run_id, "validated")
            self._record_decision(run_id, decision)
            return decision, None
        if override_approval_id:
            override_error = self._override_error_code(
                approval_id=override_approval_id,
                run_id=run_id,
                target_kind="handoff",
                target_ref=target_ref,
                action_hash=action_hash,
                policy_hash=self._policy_bundle.policy_hash,
                execution_contract_hash=execution_contract_hash,
                resume_token_ref=resume_token_ref,
            )
            if override_error is not None:
                decision = GovernanceDecision(
                    phase=GovernancePhase.HANDOFF,
                    target=target_ref,
                    action=GovernanceAction.DENY,
                    reason_code=override_error,
                    matched_rule_path="approval_override",
                    policy_schema_version=self._policy_bundle.policy.policy_schema_version,
                    policy_version=self._policy_bundle.policy.policy_version,
                    policy_hash=self._policy_bundle.policy_hash,
                    decision_engine_version=self._gov.decision_engine_version,
                    explain="approval override validation failed",
                )
                self._record_decision(run_id, decision)
                return decision, None

        match = evaluate_handoff(
            self._policy_bundle.policy,
            from_role=from_role,
            to_role=to_role,
        )
        decision = GovernanceDecision(
            phase=GovernancePhase.HANDOFF,
            target=f"{from_role}->{to_role}",
            action=match.action,
            reason_code=match.reason_code,
            matched_rule_path=match.matched_rule_path,
            policy_schema_version=self._policy_bundle.policy.policy_schema_version,
            policy_version=self._policy_bundle.policy.policy_version,
            policy_hash=self._policy_bundle.policy_hash,
            decision_engine_version=self._gov.decision_engine_version,
            approval_required=match.action == GovernanceAction.REQUIRE_APPROVAL,
            explain=match.explain,
        )

        ticket: ApprovalTicket | None = None
        if match.action == GovernanceAction.REQUIRE_APPROVAL:
            snapshot = {
                "kind": "handoff",
                "target_kind": "handoff",
                "target_ref": target_ref,
                "action_hash": action_hash,
                "from_role": from_role,
                "to_role": to_role,
                "payload_hash": payload_hash,
                "policy_hash": self._policy_bundle.policy_hash,
            }
            request_hash = self._hash_payload([from_role, to_role, payload_hash])
            snapshot_hash = self._hash_payload(snapshot)
            ticket = self._approval_store.create_ticket(
                workspace_id=self._workspace_for_run(run_id),
                run_id=run_id,
                target_kind="handoff",
                target_ref=target_ref,
                action_hash=action_hash,
                policy_hash=self._policy_bundle.policy_hash,
                request_hash=request_hash,
                snapshot_hash=snapshot_hash,
                snapshot=snapshot,
                ttl_seconds=self._gov.approval_ttl_seconds,
                idempotency_key=f"handoff:{run_id}:{snapshot_hash}",
            )
            decision = decision.model_copy(update={"approval_id": ticket.approval_id})
            self._set_approval_status(run_id, "pending")

        self._record_handoff(
            run_id,
            HandoffCallRecord(
                from_role=from_role,
                to_role=to_role,
                payload_hash=payload_hash,
                decision_action=decision.action,
                reason_code=decision.reason_code,
            ),
        )
        self._record_decision(run_id, decision)
        return decision, ticket

    def evaluate_memory_write(
        self,
        *,
        run_id: str,
        scope: str,
        producer_role: str,
        visibility: str,
        override_approval_id: str | None = None,
        memory_target: str | None = None,
        expected_state_version: int | None = None,
        execution_contract_hash: str | None = None,
        resume_token_ref: str | None = None,
    ) -> tuple[GovernanceDecision, ApprovalTicket | None]:
        if not self._gov.enabled:
            decision = self._default_allow_decision(
                phase=GovernancePhase.MEMORY_WRITE,
                target=f"{scope}:{producer_role}:{visibility}",
            )
            return decision, None
        if self._policy_bundle is None:
            decision = GovernanceDecision(
                phase=GovernancePhase.MEMORY_WRITE,
                target=f"{scope}:{producer_role}:{visibility}",
                action=GovernanceAction.DENY,
                reason_code="POLICY_UNAVAILABLE",
                matched_rule_path=None,
                policy_schema_version="unavailable",
                policy_version="unavailable",
                policy_hash="unavailable",
                decision_engine_version=self._gov.decision_engine_version,
                explain=self._policy_error,
            )
            self._record_decision(run_id, decision)
            return decision, None

        target_ref = f"{scope}:{producer_role}:{visibility}:{memory_target or ''}"
        action_hash = self._memory_action_hash(
            scope=scope,
            producer_role=producer_role,
            visibility=visibility,
            memory_target=memory_target,
            expected_state_version=expected_state_version,
            policy_hash=self._policy_bundle.policy_hash,
        )
        override_ticket = self._consume_override_ticket(
            approval_id=override_approval_id,
            run_id=run_id,
            target_kind="memory_write",
            target_ref=target_ref,
            action_hash=action_hash,
            policy_hash=self._policy_bundle.policy_hash,
            execution_contract_hash=execution_contract_hash,
            resume_token_ref=resume_token_ref,
        )
        if override_ticket is not None:
            decision = GovernanceDecision(
                phase=GovernancePhase.MEMORY_WRITE,
                target=target_ref,
                action=GovernanceAction.ALLOW,
                reason_code="APPROVAL_OVERRIDE",
                matched_rule_path="approval_override",
                policy_schema_version=self._policy_bundle.policy.policy_schema_version,
                policy_version=self._policy_bundle.policy.policy_version,
                policy_hash=self._policy_bundle.policy_hash,
                decision_engine_version=self._gov.decision_engine_version,
                approval_required=False,
                approval_id=override_ticket.approval_id,
                explain="executed approval override validated",
            )
            self._record_memory_write(
                run_id,
                MemoryWriteRecord(
                    scope=scope,
                    producer_role=producer_role,
                    visibility=visibility,
                    decision_action=decision.action,
                    reason_code=decision.reason_code,
                ),
            )
            self._set_approval_status(run_id, "validated")
            self._record_decision(run_id, decision)
            return decision, None
        if override_approval_id:
            override_error = self._override_error_code(
                approval_id=override_approval_id,
                run_id=run_id,
                target_kind="memory_write",
                target_ref=target_ref,
                action_hash=action_hash,
                policy_hash=self._policy_bundle.policy_hash,
                execution_contract_hash=execution_contract_hash,
                resume_token_ref=resume_token_ref,
            )
            if override_error is not None:
                decision = GovernanceDecision(
                    phase=GovernancePhase.MEMORY_WRITE,
                    target=target_ref,
                    action=GovernanceAction.DENY,
                    reason_code=override_error,
                    matched_rule_path="approval_override",
                    policy_schema_version=self._policy_bundle.policy.policy_schema_version,
                    policy_version=self._policy_bundle.policy.policy_version,
                    policy_hash=self._policy_bundle.policy_hash,
                    decision_engine_version=self._gov.decision_engine_version,
                    explain="approval override validation failed",
                )
                self._record_decision(run_id, decision)
                return decision, None

        match = evaluate_memory_scope_write(
            self._policy_bundle.policy,
            scope=scope,
            producer_role=producer_role,
            visibility=visibility,
        )
        decision = GovernanceDecision(
            phase=GovernancePhase.MEMORY_WRITE,
            target=f"{scope}:{producer_role}:{visibility}",
            action=match.action,
            reason_code=match.reason_code,
            matched_rule_path=match.matched_rule_path,
            policy_schema_version=self._policy_bundle.policy.policy_schema_version,
            policy_version=self._policy_bundle.policy.policy_version,
            policy_hash=self._policy_bundle.policy_hash,
            decision_engine_version=self._gov.decision_engine_version,
            approval_required=match.action == GovernanceAction.REQUIRE_APPROVAL,
            explain=match.explain,
        )

        ticket: ApprovalTicket | None = None
        if match.action == GovernanceAction.REQUIRE_APPROVAL:
            snapshot = {
                "kind": "memory_write",
                "target_kind": "memory_write",
                "target_ref": target_ref,
                "action_hash": action_hash,
                "scope": scope,
                "producer_role": producer_role,
                "visibility": visibility,
                "memory_target": memory_target,
                "expected_state_version": expected_state_version,
                "policy_hash": self._policy_bundle.policy_hash,
            }
            request_hash = self._hash_payload([scope, producer_role, visibility])
            snapshot_hash = self._hash_payload(snapshot)
            ticket = self._approval_store.create_ticket(
                workspace_id=self._workspace_for_run(run_id),
                run_id=run_id,
                target_kind="memory_write",
                target_ref=target_ref,
                action_hash=action_hash,
                policy_hash=self._policy_bundle.policy_hash,
                request_hash=request_hash,
                snapshot_hash=snapshot_hash,
                snapshot=snapshot,
                ttl_seconds=self._gov.approval_ttl_seconds,
                idempotency_key=f"memory:{run_id}:{snapshot_hash}",
            )
            decision = decision.model_copy(update={"approval_id": ticket.approval_id})
            self._set_approval_status(run_id, "pending")

        self._record_memory_write(
            run_id,
            MemoryWriteRecord(
                scope=scope,
                producer_role=producer_role,
                visibility=visibility,
                decision_action=decision.action,
                reason_code=decision.reason_code,
            ),
        )
        self._record_decision(run_id, decision)
        return decision, ticket

    def trace_redact(self, data: dict[str, Any]) -> dict[str, Any]:
        patterns = []
        if self._policy_bundle is not None:
            patterns = self._policy_bundle.policy.pii_rules.patterns
        return redact_trace_payload(data, pii_patterns=patterns)

    def audit_redact(self, data: dict[str, Any]) -> dict[str, Any]:
        patterns = []
        if self._policy_bundle is not None:
            patterns = self._policy_bundle.policy.pii_rules.patterns
        return redact_audit_payload(data, pii_patterns=patterns)

    def finalize_run(
        self,
        *,
        run_id: str,
        router_reason_code: str | None,
        model_metadata: dict[str, Any] | None = None,
    ) -> str | None:
        if not self._gov.enabled:
            return None
        if self._policy_bundle is None:
            return None
        state = self._runs.get(run_id, GovernanceRunState())
        model_metadata = model_metadata or {}

        requested_provider = str(
            model_metadata.get("requested_provider") or self._config.llm_provider
        )
        requested_model_name = str(
            model_metadata.get("requested_model_name") or self._config.model_name
        )

        record = AuditRecord(
            run_id=run_id,
            runtime_version=__version__,
            profile=self._config.profile_name,
            model_provider=requested_provider,
            model_name=requested_model_name,
            requested_provider=requested_provider,
            requested_fallback_provider=str(
                model_metadata.get("requested_fallback_provider") or self._config.fallback_provider
            ),
            requested_model_name=requested_model_name,
            requested_hf_model_id=str(
                model_metadata.get("requested_hf_model_id") or self._config.hf_model_id
            ),
            selected_provider=(
                str(model_metadata["selected_provider"])
                if model_metadata.get("selected_provider") is not None
                else None
            ),
            selected_model_name=(
                str(model_metadata["selected_model_name"])
                if model_metadata.get("selected_model_name") is not None
                else None
            ),
            selected_hf_model_id=(
                str(model_metadata["selected_hf_model_id"])
                if model_metadata.get("selected_hf_model_id") is not None
                else None
            ),
            fallback_used=bool(model_metadata.get("fallback_used", False)),
            config_source_model_name=(
                str(model_metadata["config_source_model_name"])
                if model_metadata.get("config_source_model_name") is not None
                else "profile"
            ),
            config_source_hf_model_id=(
                str(model_metadata["config_source_hf_model_id"])
                if model_metadata.get("config_source_hf_model_id") is not None
                else "profile"
            ),
            router_reason_code=router_reason_code,
            policy_schema_version=self._policy_bundle.policy.policy_schema_version,
            policy_version=self._policy_bundle.policy.policy_version,
            policy_hash=self._policy_bundle.policy_hash,
            decision_engine_version=self._gov.decision_engine_version,
            governance_decisions=state.decisions,
            tool_calls=state.tool_calls,
            handoffs=state.handoffs,
            memory_writes=state.memory_writes,
            device_actions=state.device_actions,
            approval_status=state.approval_status,
            redaction_mode="audit",
            privacy_mode=self._config.privacy_mode,
        )
        payload = self.audit_redact(record.model_dump(mode="json"))
        integrity = build_integrity(
            payload=payload,
            config=self._config,
            purpose="governance-audit",
        )
        payload["integrity"] = integrity
        path = self._audit_dir / f"{run_id}.json"
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return str(path)

    def decide_approval(
        self,
        *,
        approval_id: str,
        workspace_id: str | None = None,
        approve: bool,
        actor: str,
        reason: str | None,
    ) -> ApprovalDecisionResult:
        return self._approval_store.decide(
            approval_id=approval_id,
            workspace_id=workspace_id or self._approval_workspace_id(),
            approve=approve,
            actor=actor,
            reason=reason,
        )

    def execute_approval(
        self,
        *,
        approval_id: str,
        workspace_id: str | None = None,
        executed_by: str = "system",
    ) -> ApprovalDecisionResult:
        return self._approval_store.mark_executed(
            approval_id=approval_id,
            workspace_id=workspace_id or self._approval_workspace_id(),
            executed_by=executed_by,
        )

    def request_manual_task_approval(
        self,
        *,
        run_id: str,
        task_type: str,
        user_input: str,
        reason_code: str,
        explain: str,
    ) -> tuple[GovernanceDecision, ApprovalTicket | None]:
        if not self._gov.enabled:
            decision = self._default_allow_decision(phase=GovernancePhase.TASK, target=task_type)
            return decision, None
        if self._policy_bundle is None:
            decision = GovernanceDecision(
                phase=GovernancePhase.TASK,
                target=task_type,
                action=GovernanceAction.DENY,
                reason_code="POLICY_UNAVAILABLE",
                matched_rule_path=None,
                policy_schema_version="unavailable",
                policy_version="unavailable",
                policy_hash="unavailable",
                decision_engine_version=self._gov.decision_engine_version,
                explain=self._policy_error,
            )
            self._record_decision(run_id, decision)
            return decision, None

        target_ref = task_type
        action_hash = self._task_action_hash(task_type=task_type, user_input=user_input)
        snapshot = {
            "kind": "task",
            "target_kind": "task",
            "target_ref": target_ref,
            "action_hash": action_hash,
            "task_type": task_type,
            "user_input": user_input,
            "policy_hash": self._policy_bundle.policy_hash,
            "manual_reason_code": reason_code,
        }
        request_hash = self._hash_payload({"task_type": task_type, "user_input": user_input})
        snapshot_hash = self._hash_payload(snapshot)
        ticket = self._approval_store.create_ticket(
            workspace_id=self._workspace_for_run(run_id),
            run_id=run_id,
            target_kind="task",
            target_ref=target_ref,
            action_hash=action_hash,
            policy_hash=self._policy_bundle.policy_hash,
            request_hash=request_hash,
            snapshot_hash=snapshot_hash,
            snapshot=snapshot,
            ttl_seconds=self._gov.approval_ttl_seconds,
            idempotency_key=f"task-manual:{run_id}:{snapshot_hash}",
        )
        self._set_approval_status(run_id, "pending")
        decision = GovernanceDecision(
            phase=GovernancePhase.TASK,
            target=task_type,
            action=GovernanceAction.REQUIRE_APPROVAL,
            reason_code=reason_code,
            matched_rule_path="manual_approval",
            policy_schema_version=self._policy_bundle.policy.policy_schema_version,
            policy_version=self._policy_bundle.policy.policy_version,
            policy_hash=self._policy_bundle.policy_hash,
            decision_engine_version=self._gov.decision_engine_version,
            approval_required=True,
            approval_id=ticket.approval_id,
            explain=explain,
        )
        self._record_decision(run_id, decision)
        return decision, ticket

    def request_device_action_approval(
        self,
        *,
        run_id: str,
        target_ref: str,
        action_payload: dict[str, Any],
        reason_code: str = "POLICY_REQUIRE_APPROVAL",
        explain: str = "device action requires explicit approval",
    ) -> tuple[GovernanceDecision, ApprovalTicket | None]:
        if not self._gov.enabled:
            decision = self._default_allow_decision(
                phase=GovernancePhase.DEVICE_ACTION,
                target=target_ref,
            )
            return decision, None
        if self._policy_bundle is None:
            decision = GovernanceDecision(
                phase=GovernancePhase.DEVICE_ACTION,
                target=target_ref,
                action=GovernanceAction.DENY,
                reason_code="POLICY_UNAVAILABLE",
                matched_rule_path=None,
                policy_schema_version="unavailable",
                policy_version="unavailable",
                policy_hash="unavailable",
                decision_engine_version=self._gov.decision_engine_version,
                explain=self._policy_error,
            )
            self._record_decision(run_id, decision)
            return decision, None

        action_hash = self._hash_payload(
            {
                "kind": "device_action",
                "target_ref": target_ref,
                "action": action_payload,
                "policy_hash": self._policy_bundle.policy_hash,
            }
        )
        snapshot = {
            "kind": "device_action",
            "target_kind": "device_action",
            "target_ref": target_ref,
            "action_hash": action_hash,
            "policy_hash": self._policy_bundle.policy_hash,
            **action_payload,
        }
        request_hash = self._hash_payload(
            {
                "target_ref": target_ref,
                "action_id": action_payload.get("action_id"),
                "category": action_payload.get("category"),
                "risk_class": action_payload.get("risk_class"),
            }
        )
        snapshot_hash = self._hash_payload(snapshot)
        ticket = self._approval_store.create_ticket(
            workspace_id=self._workspace_for_run(run_id),
            run_id=run_id,
            target_kind="device_action",
            target_ref=target_ref,
            action_hash=action_hash,
            policy_hash=self._policy_bundle.policy_hash,
            request_hash=request_hash,
            snapshot_hash=snapshot_hash,
            snapshot=snapshot,
            ttl_seconds=self._gov.approval_ttl_seconds,
            idempotency_key=f"device_action:{run_id}:{snapshot_hash}",
        )
        decision = GovernanceDecision(
            phase=GovernancePhase.DEVICE_ACTION,
            target=target_ref,
            action=GovernanceAction.REQUIRE_APPROVAL,
            reason_code=reason_code,
            matched_rule_path="manual_device_action",
            policy_schema_version=self._policy_bundle.policy.policy_schema_version,
            policy_version=self._policy_bundle.policy.policy_version,
            policy_hash=self._policy_bundle.policy_hash,
            decision_engine_version=self._gov.decision_engine_version,
            approval_required=True,
            approval_id=ticket.approval_id,
            explain=explain,
        )
        self._record_device_action(
            run_id,
            DeviceActionRecord(
                action_id=str(action_payload.get("action_id") or ""),
                category=str(action_payload.get("category") or ""),
                risk_class=str(action_payload.get("risk_class") or ""),
                target_ref=target_ref,
                app_identity=str(action_payload.get("app_identity") or ""),
                window_identity=str(action_payload.get("window_identity") or ""),
                selector_source=str(action_payload.get("selector_source") or ""),
                decision_action=decision.action,
                reason_code=decision.reason_code,
            ),
        )
        self._set_approval_status(run_id, "pending")
        self._record_decision(run_id, decision)
        return decision, ticket

    def consume_approval(
        self,
        *,
        approval_id: str,
        consumed_by_job_id: str,
        execution_contract_hash: str | None = None,
        resume_token_ref: str | None = None,
        workspace_id: str | None = None,
    ) -> ApprovalDecisionResult:
        return self._approval_store.mark_consumed(
            approval_id=approval_id,
            workspace_id=self._workspace_for_run(
                consumed_by_job_id, workspace_id
            ),
            consumed_by_job_id=consumed_by_job_id,
            execution_contract_hash=execution_contract_hash,
            resume_token_ref=resume_token_ref,
        )

    def attach_execution_contract(
        self,
        *,
        approval_id: str,
        execution_contract: dict[str, Any],
        execution_contract_hash: str,
    ) -> ApprovalDecisionResult:
        workspace_id = self._approval_workspace_id()
        ticket = self._approval_store.get(approval_id, workspace_id=workspace_id)
        snapshot_hash = self._hash_payload(
            {
                **(ticket.snapshot if ticket else {}),
                "execution_contract": execution_contract,
            }
        )
        return self._approval_store.attach_execution_contract(
            approval_id=approval_id,
            workspace_id=workspace_id,
            execution_contract=execution_contract,
            execution_contract_hash=execution_contract_hash,
            snapshot_hash=snapshot_hash,
        )

    def prepare_resume_approval(
        self,
        *,
        approval_id: str,
        run_id: str,
        task_run_id: str,
        target_kind: str,
        execution_contract_hash: str,
        workspace_id: str | None = None,
    ) -> ApprovalDecisionResult:
        self._approval_store.expire_pending()
        effective_workspace = self._workspace_for_run(run_id, workspace_id)
        ticket = self._approval_store.get(
            approval_id, workspace_id=effective_workspace
        )
        if ticket is None:
            return ApprovalDecisionResult(ticket=None, error_code="APPROVAL_NOT_FOUND")
        contract_task_run_id = str(
            ticket.snapshot.get("execution_contract", {}).get("task_run_id") or task_run_id
        )
        resume_token_ref = self._hash_payload(
            {
                "source_job_id": ticket.run_id,
                "task_run_id": contract_task_run_id,
                "approval_id": approval_id,
                "snapshot_hash": ticket.snapshot_hash,
                "target_kind": target_kind,
            }
        )
        return self._approval_store.claim_resume(
            approval_id=approval_id,
            workspace_id=effective_workspace,
            resume_job_id=run_id,
            resume_token_ref=resume_token_ref,
            execution_contract_hash=execution_contract_hash,
        )

    def task_action_hash(self, *, task_type: str, user_input: str) -> str:
        return self._task_action_hash(task_type=task_type, user_input=user_input)

    def handoff_action_hash(
        self,
        *,
        from_role: str,
        to_role: str,
        payload_hash: str,
    ) -> str:
        return self._handoff_action_hash(
            from_role=from_role,
            to_role=to_role,
            payload_hash=payload_hash,
            policy_hash=self.policy_hash,
        )

    def memory_action_hash(
        self,
        *,
        scope: str,
        producer_role: str,
        visibility: str,
        memory_target: str | None,
        expected_state_version: int | None,
    ) -> str:
        return self._memory_action_hash(
            scope=scope,
            producer_role=producer_role,
            visibility=visibility,
            memory_target=memory_target,
            expected_state_version=expected_state_version,
            policy_hash=self.policy_hash,
        )

    def _record_decision(self, run_id: str, decision: GovernanceDecision) -> None:
        state = self._runs.setdefault(run_id, GovernanceRunState())
        state.decisions.append(decision)

    def _record_tool_call(self, run_id: str, tool_call: ToolCallRecord) -> None:
        state = self._runs.setdefault(run_id, GovernanceRunState())
        state.tool_calls.append(tool_call)

    def _record_handoff(self, run_id: str, handoff: HandoffCallRecord) -> None:
        state = self._runs.setdefault(run_id, GovernanceRunState())
        state.handoffs.append(handoff)

    def _record_memory_write(self, run_id: str, memory_write: MemoryWriteRecord) -> None:
        state = self._runs.setdefault(run_id, GovernanceRunState())
        state.memory_writes.append(memory_write)

    def _record_device_action(self, run_id: str, device_action: DeviceActionRecord) -> None:
        state = self._runs.setdefault(run_id, GovernanceRunState())
        state.device_actions.append(device_action)

    def _set_approval_status(self, run_id: str, status: str) -> None:
        state = self._runs.setdefault(run_id, GovernanceRunState())
        state.approval_status = status

    def _consume_override_ticket(
        self,
        *,
        approval_id: str | None,
        run_id: str,
        target_kind: str,
        target_ref: str,
        action_hash: str,
        policy_hash: str,
        execution_contract_hash: str | None = None,
        resume_token_ref: str | None = None,
        workspace_id: str | None = None,
    ) -> ApprovalTicket | None:
        if not approval_id:
            return None
        self._approval_store.expire_pending()
        ticket = self.get_approval(
            approval_id, workspace_id=workspace_id, run_id=run_id
        )
        if ticket is None:
            return None
        if ticket.status != ApprovalStatus.EXECUTED:
            return None
        if ticket.execution_status != ExecutionStatus.EXECUTED:
            return None
        if ticket.consumed_at is not None or ticket.consumed_by_job_id is not None:
            return None
        if ticket.target_kind != target_kind:
            return None
        if ticket.target_ref != target_ref:
            return None
        if ticket.action_hash != action_hash:
            return None
        if ticket.policy_hash != policy_hash:
            return None
        if (
            ticket.execution_contract_hash
            and execution_contract_hash
            and ticket.execution_contract_hash != execution_contract_hash
        ):
            return None
        if ticket.execution_contract_hash and not execution_contract_hash:
            return None
        if ticket.resume_claimed_job_id not in {None, run_id}:
            return None
        if (
            ticket.resume_token_ref
            and resume_token_ref
            and ticket.resume_token_ref != resume_token_ref
        ):
            return None
        if ticket.resume_claimed_job_id is None and execution_contract_hash:
            claim = self.prepare_resume_approval(
                approval_id=approval_id,
                run_id=run_id,
                task_run_id=str(
                    ticket.snapshot.get("execution_contract", {}).get("task_run_id") or target_ref
                ),
                target_kind=target_kind,
                execution_contract_hash=execution_contract_hash,
                workspace_id=workspace_id,
            )
            if claim.error_code:
                return None
            return claim.ticket
        return ticket

    def _override_error_code(
        self,
        *,
        approval_id: str,
        run_id: str,
        target_kind: str,
        target_ref: str,
        action_hash: str,
        policy_hash: str,
        execution_contract_hash: str | None = None,
        resume_token_ref: str | None = None,
        workspace_id: str | None = None,
    ) -> str | None:
        ticket = self.get_approval(
            approval_id, workspace_id=workspace_id, run_id=run_id
        )
        if ticket is None:
            return "APPROVAL_NOT_FOUND"
        if ticket.status in {ApprovalStatus.PENDING, ApprovalStatus.APPROVED}:
            return None
        if ticket.execution_status == ExecutionStatus.NOT_EXECUTED:
            return None
        if ticket.status != ApprovalStatus.EXECUTED:
            if ticket.status == ApprovalStatus.CONSUMED:
                return "REPLAY_BLOCKED"
            return "APPROVAL_CONFLICT"
        if ticket.execution_status != ExecutionStatus.EXECUTED:
            return "APPROVAL_CONFLICT"
        if ticket.consumed_at is not None or ticket.consumed_by_job_id is not None:
            return "REPLAY_BLOCKED"
        if ticket.target_kind != target_kind:
            return "STALE_APPROVAL_SNAPSHOT"
        if ticket.target_ref != target_ref:
            return "STALE_APPROVAL_SNAPSHOT"
        if ticket.action_hash != action_hash:
            return "STALE_APPROVAL_SNAPSHOT"
        if ticket.policy_hash != policy_hash:
            return "STALE_POLICY_INPUT"
        if (
            ticket.execution_contract_hash
            and execution_contract_hash
            and ticket.execution_contract_hash != execution_contract_hash
        ):
            return "STALE_APPROVAL_SNAPSHOT"
        if ticket.execution_contract_hash and not execution_contract_hash:
            return "STALE_APPROVAL_SNAPSHOT"
        if ticket.resume_claimed_job_id not in {None, run_id}:
            return "RESUME_DUPLICATE_SUPPRESSED"
        if (
            ticket.resume_token_ref
            and resume_token_ref
            and ticket.resume_token_ref != resume_token_ref
        ):
            return "STALE_RESUME_TOKEN"
        return None

    def _default_allow_decision(self, *, phase: GovernancePhase, target: str) -> GovernanceDecision:
        return GovernanceDecision(
            phase=phase,
            target=target,
            action=GovernanceAction.ALLOW,
            reason_code="RULE_ROUTE",
            matched_rule_path=None,
            policy_schema_version="disabled",
            policy_version="disabled",
            policy_hash="disabled",
            decision_engine_version=self._gov.decision_engine_version,
            explain="governance disabled",
        )

    @staticmethod
    def _hash_payload(payload: Any) -> str:
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _task_action_hash(self, *, task_type: str, user_input: str) -> str:
        return self._hash_payload(
            {
                "kind": "task",
                "task_type": task_type,
                "user_input": user_input,
                "policy_hash": (
                    self._policy_bundle.policy_hash if self._policy_bundle else "disabled"
                ),
            }
        )

    def _handoff_action_hash(
        self,
        *,
        from_role: str,
        to_role: str,
        payload_hash: str,
        policy_hash: str,
    ) -> str:
        return self._hash_payload(
            {
                "kind": "handoff",
                "from_role": from_role,
                "to_role": to_role,
                "payload_hash": payload_hash,
                "policy_hash": policy_hash,
            }
        )

    def _memory_action_hash(
        self,
        *,
        scope: str,
        producer_role: str,
        visibility: str,
        memory_target: str | None,
        expected_state_version: int | None,
        policy_hash: str,
    ) -> str:
        return self._hash_payload(
            {
                "kind": "memory_write",
                "scope": scope,
                "producer_role": producer_role,
                "visibility": visibility,
                "memory_target": memory_target,
                "expected_state_version": expected_state_version,
                "policy_hash": policy_hash,
            }
        )

    def _tool_action_hash(
        self,
        *,
        command_root: str,
        normalized_args: list[str],
        policy_hash: str,
    ) -> str:
        return self._hash_payload(
            {
                "kind": "tool",
                "command_root": command_root,
                "normalized_args": normalized_args,
                "policy_hash": policy_hash,
            }
        )


def build_governance_runtime(config: RuntimeConfig) -> GovernanceRuntime | None:
    gov_cfg = config.governance
    if not gov_cfg.enabled:
        return None
    return GovernanceRuntime(config=config)


def governance_startup_abort(
    config: RuntimeConfig,
    runtime: GovernanceRuntime | None,
) -> str | None:
    if runtime is None:
        return None
    err = runtime.execution_startup_error()
    if err is None:
        return None
    if config.governance.policy_fail_mode == "fail_closed":
        return err
    return None


def default_governance_policy_path(profile_name: str) -> str:
    return str(Path("config") / "policies" / f"{profile_name}.toml")


def ensure_governance_defaults(config: GovernanceConfig, *, profile_name: str) -> GovernanceConfig:
    if config.policy_path:
        return config
    return config.model_copy(update={"policy_path": default_governance_policy_path(profile_name)})
