from __future__ import annotations

import hashlib
import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from imperaos.core.orchestrator import Orchestrator
from imperaos.memory.models import (
    MemoryOwnerType,
    MemoryScope,
    MemoryVisibility,
    hash_identity,
)
from imperaos.runtime.config import RuntimeConfig
from imperaos.team.artifacts import (
    ensure_team_artifact_paths,
    write_audit_envelope,
    write_handoffs,
    write_status,
    write_task_runs,
)
from imperaos.team.checkpoint_store import TeamCheckpointStore
from imperaos.team.event_recorder import EventRecorder
from imperaos.team.execution_contract import (
    build_handoff_execution_contract,
    build_memory_write_execution_contract,
    build_task_execution_contract,
    derive_execution_contract_refs,
    payload_hash,
)
from imperaos.team.handoff import evaluate_handoff_transfer
from imperaos.team.memory_scope import (
    evaluate_memory_scope_write,
    read_scoped_memory,
    validate_memory_access,
    write_scoped_memory,
)
from imperaos.team.models import (
    HandoffRecord,
    JobRun,
    JobStatus,
    TaskDefinition,
    TaskRun,
    TaskStatus,
    TeamEvent,
    TeamRunResult,
    TeamSpec,
)
from imperaos.team.scheduler import ParallelScheduler
from imperaos.team.validation import validate_team_spec


class TeamSupervisor:
    def __init__(
        self,
        *,
        orchestrator: Orchestrator,
        config: RuntimeConfig,
    ):
        self._orchestrator = orchestrator
        self._config = config
        self._governance_runtime = getattr(orchestrator, "governance_runtime", None)
        self._memory_manager = getattr(orchestrator, "_memory_manager", None)
        self._memory_runtime_bridge = getattr(orchestrator, "_memory_runtime_bridge", None)

    def run(
        self,
        *,
        spec: TeamSpec,
        request: str,
        case_id: str | None = None,
        job_id: str | None = None,
        approval_overrides: dict[str, dict[str, str]] | None = None,
        continuation_state: dict[str, Any] | None = None,
    ) -> TeamRunResult:
        created_at = datetime.now(UTC)
        resolved_case_id = case_id or f"case-{uuid4().hex[:12]}"
        resolved_job_id = job_id or f"job-{uuid4().hex[:12]}"
        job = JobRun(
            job_id=resolved_job_id,
            case_id=resolved_case_id,
            team_id=spec.team.team_id,
            request=request,
            status=JobStatus.RUNNING,
            created_at=created_at,
        )

        team_cfg = self._config.team
        paths = ensure_team_artifact_paths(job_id=resolved_job_id, root_dir=team_cfg.artifact_dir)
        checkpoint_store = TeamCheckpointStore(team_cfg.checkpoint_db_path)
        events: list[TeamEvent] = []
        handoffs: list[HandoffRecord] = []
        task_outputs: dict[str, dict[str, Any]] = {}
        task_runs: dict[str, TaskRun] = {}
        task_last_event: dict[str, str] = {}
        consumed_handoffs: set[str] = set()
        lock = threading.RLock()
        protected_execution_lock = threading.RLock()
        recorder = EventRecorder(
            paths=paths,
            team_id=spec.team.team_id,
            case_id=resolved_case_id,
            job_id=resolved_job_id,
            sink=events,
            lock=lock,
        )

        all_tasks = _resolve_tasks(spec, request)
        resolved_spec = spec.model_copy(update={"tasks": all_tasks})
        validation_errors = validate_team_spec(
            resolved_spec,
            active_policy_profile=_active_policy_profile(self._config),
        )
        branch_cache: dict[str, tuple[str, str | None]] = {}
        tasks_by_id = {item.task_id: item for item in all_tasks}
        continuation = continuation_state or {}
        root_run_id = str(continuation.get("root_run_id") or resolved_job_id)
        checkpoint_generation = int(continuation.get("checkpoint_generation") or 0)
        continuation_index = int(continuation.get("continuation_index") or 0)
        scheduled_task_ids = set(
            str(item)
            for item in (
                continuation.get("continuation_task_ids")
                or [task.task_id for task in all_tasks]
            )
        )
        tasks = [item for item in all_tasks if item.task_id in scheduled_task_ids]
        inherited_completed_task_ids = {
            str(item) for item in continuation.get("completed_task_ids", [])
        }
        inherited_completed_outputs = {
            str(task_id): dict(value)
            for task_id, value in dict(continuation.get("completed_outputs") or {}).items()
        }
        inherited_task_lineage = {
            str(task_id): dict(value)
            for task_id, value in dict(continuation.get("task_lineage") or {}).items()
        }
        blocked_task_ids = [
            str(item) for item in list(continuation.get("blocked_task_ids") or [])
        ]
        task_run_ids = {}
        for item in all_tasks:
            lineage = inherited_task_lineage.get(item.task_id) or {}
            task_run_ids[item.task_id] = str(
                lineage.get("task_run_id") or _task_run_id(resolved_job_id, item.task_id, 1)
            )
        resume_outcomes: list[dict[str, Any]] = []

        def task_branch(task_id: str | None) -> tuple[str | None, str | None]:
            if task_id is None:
                return None, None
            if task_id not in branch_cache:
                branch_cache[task_id] = _task_branch_info(task_id, tasks_by_id, branch_cache)
            return branch_cache[task_id]

        def emit(
            event: str,
            *,
            task_id: str | None = None,
            task_run_id: str | None = None,
            task_attempt: int | None = None,
            agent_id: str | None = None,
            role: str | None = None,
            phase: str | None = None,
            status_before: str | None = None,
            status_after: str | None = None,
            trace_id: str | None = None,
            causal_ref: str | None = None,
            approval_id: str | None = None,
            payload_hash: str | None = None,
            branch_id: str | None = None,
            branch_parent: str | None = None,
            snapshot_hash: str | None = None,
            resolved_memory_fingerprint: str | None = None,
            memory_target: str | None = None,
            expected_state_version: int | None = None,
            committed_state_version: int | None = None,
            resume_token_ref: str | None = None,
            conflict_detected: bool | None = None,
            conflict_resolution: str | None = None,
            fallback_mode_applied: str | None = None,
            serialized_due_to_policy: bool | None = None,
            data: dict[str, Any] | None = None,
        ) -> TeamEvent:
            resolved_branch_id, resolved_branch_parent = task_branch(task_id)
            entry = recorder.emit(
                event,
                task_id=task_id,
                task_run_id=task_run_id,
                task_attempt=task_attempt,
                agent_id=agent_id,
                role=role,
                phase=phase,
                status_before=status_before,
                status_after=status_after,
                trace_id=trace_id,
                causal_ref=causal_ref,
                approval_id=approval_id,
                payload_hash=payload_hash,
                branch_id=branch_id or resolved_branch_id,
                branch_parent=branch_parent
                if branch_parent is not None
                else resolved_branch_parent,
                snapshot_hash=snapshot_hash,
                resolved_memory_fingerprint=resolved_memory_fingerprint,
                memory_target=memory_target,
                expected_state_version=expected_state_version,
                committed_state_version=committed_state_version,
                resume_token_ref=resume_token_ref,
                conflict_detected=conflict_detected,
                conflict_resolution=conflict_resolution,
                fallback_mode_applied=fallback_mode_applied,
                serialized_due_to_policy=serialized_due_to_policy,
                data=data,
            )
            if task_run_id is not None:
                task_last_event[task_run_id] = entry.event_id
            return entry

        def lineage_meta(task_id: str) -> dict[str, Any]:
            branch_id, branch_parent = task_branch(task_id)
            inherited = inherited_task_lineage.get(task_id) or {}
            lineage_hash = str(
                inherited.get("lineage_hash")
                or payload_hash(
                    {
                        "root_run_id": root_run_id,
                        "logical_task_id": task_id,
                        "branch_id": branch_id,
                        "branch_parent": branch_parent,
                    }
                )
            )
            return {
                "root_run_id": str(inherited.get("root_run_id") or root_run_id),
                "logical_task_id": str(inherited.get("logical_task_id") or task_id),
                "task_run_id": str(inherited.get("task_run_id") or task_run_ids[task_id]),
                "branch_id": str(inherited.get("branch_id") or branch_id or f"branch:{task_id}"),
                "branch_parent": (
                    str(inherited.get("branch_parent"))
                    if inherited.get("branch_parent") is not None
                    else branch_parent
                ),
                "lineage_hash": lineage_hash,
                "continuation_index": int(
                    inherited.get("continuation_index") or continuation_index or 0
                ),
                "checkpoint_generation": int(
                    inherited.get("checkpoint_generation") or checkpoint_generation or 0
                ),
                "terminal_event_id": inherited.get("terminal_event_id"),
                "task_attempt": int(inherited.get("task_attempt") or 1),
            }

        emit(
            "team_start",
            phase="team",
            status_before="pending",
            status_after="running",
            data={"request": request},
        )
        for task_id, output in inherited_completed_outputs.items():
            if task_id in tasks_by_id:
                task_outputs[task_id] = dict(output)
        for _task_id, lineage in inherited_task_lineage.items():
            task_run_id = str(lineage.get("task_run_id") or "").strip()
            terminal_event_id = str(lineage.get("terminal_event_id") or "").strip()
            if task_run_id and terminal_event_id:
                task_last_event[task_run_id] = terminal_event_id
        if continuation:
            frontier_loaded = emit(
                "team.resume.frontier_loaded",
                phase="team",
                status_before="blocked",
                status_after="frontier_loaded",
                data={
                    "resume_source_job_id": continuation.get("resume_source_job_id"),
                    "root_run_id": root_run_id,
                    "checkpoint_generation": checkpoint_generation,
                    "continuation_index": continuation_index,
                    "blocked_task_ids": blocked_task_ids,
                    "continuation_token": continuation.get("continuation_token"),
                },
            )
            emit(
                "team.resume.continuation_selected",
                phase="team",
                status_before="frontier_loaded",
                status_after="continuing",
                causal_ref=frontier_loaded.event_id,
                data={
                    "scheduled_task_ids": [item.task_id for item in tasks],
                    "upstream_completed_nodes": list(
                        continuation.get("upstream_completed_nodes") or []
                    ),
                    "resume_root_restart_count": 0,
                },
            )
        checkpoint_store.upsert(
            job_id=resolved_job_id,
            case_id=resolved_case_id,
            team_id=spec.team.team_id,
            status=job.status.value,
            payload={
                "phase": "started",
                "continuation": {
                    "root_run_id": root_run_id,
                    "checkpoint_generation": checkpoint_generation,
                    "continuation_index": continuation_index,
                    "blocked_task_ids": blocked_task_ids,
                    "continuation_task_ids": [item.task_id for item in tasks],
                },
            },
        )

        if len(tasks) > spec.team.termination_rules.max_tasks:
            return _finalize_early(
                paths=paths,
                checkpoint_store=checkpoint_store,
                job=job,
                events=events,
                handoffs=handoffs,
                emit=emit,
                reason_code="TEAM_BUDGET_EXCEEDED",
                message="Team task budget exceeded.",
            )

        if validation_errors:
            return _finalize_early(
                paths=paths,
                checkpoint_store=checkpoint_store,
                job=job,
                events=events,
                handoffs=handoffs,
                emit=emit,
                reason_code="TEAM_SPEC_INVALID",
                message="Team spec validation failed.",
                extra={"errors": validation_errors},
            )

        if continuation and not tasks:
            return _finalize_early(
                paths=paths,
                checkpoint_store=checkpoint_store,
                job=job,
                events=events,
                handoffs=handoffs,
                emit=emit,
                reason_code="INVALID_CONTINUATION_FRONTIER",
                message="Continuation frontier contained no runnable tasks.",
            )

        for item in tasks:
            emit(
                "task_created",
                task_id=item.task_id,
                task_run_id=task_run_ids[item.task_id],
                task_attempt=1,
                role=item.role,
                phase="task",
                status_before="none",
                status_after="pending",
                data={
                    "task_type": item.task_type,
                    "depends_on": item.depends_on,
                    "memory_target": item.memory_target,
                },
            )

        if approval_overrides:
            for task_id, target_map in sorted(approval_overrides.items()):
                task_def = tasks_by_id.get(task_id)
                for target, approval_id in sorted(target_map.items()):
                    ticket = (
                        self._governance_runtime.get_approval(approval_id)
                        if self._governance_runtime is not None
                        else None
                    )
                    emit(
                        "approval_resolved",
                        task_id=task_id,
                        task_run_id=task_run_ids.get(task_id),
                        task_attempt=1,
                        role=task_def.role if task_def else None,
                        phase="approval",
                        status_before="executed",
                        status_after="available",
                        approval_id=approval_id,
                        snapshot_hash=ticket.snapshot_hash if ticket else None,
                        resume_token_ref=ticket.resume_token_ref if ticket else None,
                        data={
                            "approval_id": approval_id,
                            "status": "executed",
                            "target": target,
                        },
                    )

        scheduler = ParallelScheduler(
            max_parallel_tasks=max(1, _team_parallelism(self._config)),
            max_total_tasks=max(1, spec.team.termination_rules.max_tasks),
        )

        def execute_task(task_def: TaskDefinition) -> TaskRun:
            task_run_id = task_run_ids[task_def.task_id]
            branch_id, branch_parent = task_branch(task_def.task_id)
            lineage = lineage_meta(task_def.task_id)
            try:
                agent = _select_agent(spec, task_def.role)
            except ValueError:
                return _blocked_task_run(
                    task_def=task_def,
                    task_run_id=task_run_id,
                    reason_code="AGENT_ROLE_UNRESOLVED",
                    emit=emit,
                )

            assigned = emit(
                "task_assigned",
                task_id=task_def.task_id,
                task_run_id=task_run_id,
                task_attempt=1,
                role=task_def.role,
                agent_id=agent.agent_id,
                phase="task",
                status_before="pending",
                status_after="pending",
                causal_ref=task_last_event.get(task_run_id),
                data={"task_type": task_def.task_type},
            )

            if agent.allowed_task_types and task_def.task_type not in agent.allowed_task_types:
                return _blocked_task_run(
                    task_def=task_def,
                    task_run_id=task_run_id,
                    agent_id=agent.agent_id,
                    reason_code="TASK_TYPE_NOT_ALLOWED",
                    emit=emit,
                    causal_ref=assigned.event_id,
                )

            dependency_snippets: list[str] = []
            dependency_events: list[str] = []
            for dep_id in task_def.depends_on:
                dep_output = task_outputs.get(dep_id)
                dep_task = tasks_by_id.get(dep_id)
                dep_task_run_id = task_run_ids.get(dep_id)
                if dep_output is None or dep_task is None or dep_task_run_id is None:
                    return _blocked_task_run(
                        task_def=task_def,
                        task_run_id=task_run_id,
                        agent_id=agent.agent_id,
                        reason_code="TEAM_DEADLOCK",
                        emit=emit,
                        phase="dependency",
                        causal_ref=task_last_event.get(task_run_id),
                        extra={"missing_dependency": dep_id},
                    )

                if spec.team.handoff_rules and not _handoff_allowed(
                    spec, dep_task.role, task_def.role
                ):
                    return _blocked_task_run(
                        task_def=task_def,
                        task_run_id=task_run_id,
                        agent_id=agent.agent_id,
                        reason_code="HANDOFF_RULE_DENY",
                        emit=emit,
                        phase="handoff",
                        causal_ref=task_last_event.get(task_run_id),
                        extra={
                            "from_task_id": dep_id,
                            "from_role": dep_task.role,
                            "to_role": task_def.role,
                        },
                    )

                handoff_override = _task_override(
                    approval_overrides,
                    task_id=task_def.task_id,
                    target="handoff",
                )
                handoff_override_ticket = (
                    self._governance_runtime.get_approval(handoff_override)
                    if self._governance_runtime is not None and handoff_override
                    else None
                )
                redacted_dep_output = (
                    self._governance_runtime.trace_redact(dep_output)
                    if self._governance_runtime is not None
                    else dep_output
                )
                handoff_payload_hash = payload_hash(redacted_dep_output)
                handoff_action_hash = (
                    self._governance_runtime.handoff_action_hash(
                        from_role=dep_task.role,
                        to_role=task_def.role,
                        payload_hash=handoff_payload_hash,
                    )
                    if self._governance_runtime is not None
                    else handoff_payload_hash
                )
                handoff_context = _contract_context(
                    approval_ticket=handoff_override_ticket,
                    default_task_run_id=task_run_id,
                    default_task_attempt=1,
                    default_branch_id=lineage["branch_id"],
                    default_branch_parent=lineage["branch_parent"],
                    default_causal_ancestry=[task_last_event.get(dep_task_run_id, "")],
                    default_root_run_id=lineage["root_run_id"],
                    default_logical_task_id=lineage["logical_task_id"],
                    default_lineage_hash=lineage["lineage_hash"],
                    default_continuation_index=lineage["continuation_index"],
                    default_checkpoint_generation=lineage["checkpoint_generation"],
                )
                handoff_contract = build_handoff_execution_contract(
                    task_run_id=handoff_context["task_run_id"],
                    task_attempt=handoff_context["task_attempt"],
                    target_ref=f"{dep_task.role}->{task_def.role}",
                    payload_hash_value=handoff_payload_hash,
                    action_payload_hash=handoff_payload_hash,
                    policy_input_hash=handoff_payload_hash,
                    causal_ancestry=handoff_context["causal_ancestry"],
                    branch_id=handoff_context["branch_id"],
                    branch_parent=handoff_context["branch_parent"],
                    root_run_id=handoff_context["root_run_id"],
                    logical_task_id=handoff_context["logical_task_id"],
                    lineage_hash=handoff_context["lineage_hash"],
                    continuation_index=handoff_context["continuation_index"],
                    checkpoint_generation=handoff_context["checkpoint_generation"],
                )
                handoff_resume_token_ref, handoff_contract_hash, handoff_snapshot_hash = (
                    _override_contract_refs(
                        governance_runtime=self._governance_runtime,
                        approval_id=handoff_override,
                        task_run_id=task_run_id,
                        target_kind="handoff",
                        action_hash=handoff_action_hash,
                        policy_hash=_policy_hash(self._governance_runtime),
                        contract=handoff_contract,
                    )
                )
                handoff = evaluate_handoff_transfer(
                    governance_runtime=self._governance_runtime,
                    run_id=resolved_job_id,
                    from_role=dep_task.role,
                    to_role=task_def.role,
                    payload=redacted_dep_output,
                    override_approval_id=handoff_override,
                    execution_contract_hash=handoff_contract_hash,
                    resume_token_ref=handoff_resume_token_ref,
                )
                handoff_id = _handoff_id(
                    source_task_run_id=dep_task_run_id,
                    dest_task_id=task_def.task_id,
                    payload_hash=handoff.payload_hash,
                )
                handoff_event = emit(
                    "handoff",
                    task_id=task_def.task_id,
                    task_run_id=task_run_id,
                    task_attempt=1,
                    agent_id=agent.agent_id,
                    role=task_def.role,
                    phase="handoff",
                    status_before="ready",
                    status_after=(
                        "approval_pending"
                        if handoff.requires_approval
                        else "allowed"
                        if handoff.allowed
                        else "blocked"
                    ),
                    causal_ref=task_last_event.get(dep_task_run_id),
                    approval_id=handoff.approval_id,
                    payload_hash=handoff.payload_hash,
                    snapshot_hash=handoff_snapshot_hash,
                    resume_token_ref=handoff_resume_token_ref,
                    data={
                        "handoff_id": handoff_id,
                        "from_task_id": dep_id,
                        "from_role": dep_task.role,
                        "to_role": task_def.role,
                        "policy_decision": handoff.reason_code,
                        "approval_id": handoff.approval_id,
                        "payload_hash": handoff.payload_hash,
                    },
                )
                with lock:
                    handoffs.append(
                        HandoffRecord(
                            handoff_id=handoff_id,
                            from_task_id=dep_id,
                            to_task_id=task_def.task_id,
                            from_role=dep_task.role,
                            to_role=task_def.role,
                            from_agent=str(dep_output.get("agent_id", "unknown")),
                            to_agent=agent.agent_id,
                            source_task_run_id=dep_task_run_id,
                            dest_task_run_id=task_run_id,
                            payload=handoff.payload,
                            payload_hash=handoff.payload_hash,
                            policy_decision=handoff.reason_code,
                            policy_decision_ref=handoff_event.event_id,
                            redaction_applied=handoff.redaction_applied,
                            approval_state=(
                                "pending"
                                if handoff.requires_approval
                                else "consumed"
                                if handoff.allowed
                                else "denied"
                            ),
                            approval_id=handoff.approval_id,
                            consumed_at=datetime.now(UTC) if handoff.allowed else None,
                        )
                    )

                if handoff.requires_approval:
                    if handoff.approval_id and self._governance_runtime is not None:
                        contract = build_handoff_execution_contract(
                            task_run_id=handoff_context["task_run_id"],
                            task_attempt=handoff_context["task_attempt"],
                            target_ref=f"{dep_task.role}->{task_def.role}",
                            payload_hash_value=handoff.payload_hash,
                            action_payload_hash=handoff.payload_hash,
                            policy_input_hash=handoff.payload_hash,
                            causal_ancestry=handoff_context["causal_ancestry"],
                            branch_id=handoff_context["branch_id"],
                            branch_parent=handoff_context["branch_parent"],
                            root_run_id=handoff_context["root_run_id"],
                            logical_task_id=handoff_context["logical_task_id"],
                            lineage_hash=handoff_context["lineage_hash"],
                            continuation_index=handoff_context["continuation_index"],
                            checkpoint_generation=handoff_context["checkpoint_generation"],
                        )
                        _attach_contract(
                            governance_runtime=self._governance_runtime,
                            approval_id=handoff.approval_id,
                            source_job_id=resolved_job_id,
                            task_run_id=task_run_id,
                            target_kind="handoff",
                            action_hash=handoff_action_hash,
                            contract=contract,
                        )
                    if agent.approval_mode == "never":
                        return _blocked_task_run(
                            task_def=task_def,
                            task_run_id=task_run_id,
                            agent_id=agent.agent_id,
                            reason_code="AGENT_APPROVAL_MODE_DENY",
                            emit=emit,
                            phase="handoff",
                            causal_ref=handoff_event.event_id,
                            approval_id=handoff.approval_id,
                            payload_hash_value=handoff.payload_hash,
                        )
                    approval_requested = emit(
                        "approval_requested",
                        task_id=task_def.task_id,
                        task_run_id=task_run_id,
                        task_attempt=1,
                        agent_id=agent.agent_id,
                        role=task_def.role,
                        phase="approval",
                        status_before="none",
                        status_after="pending",
                        causal_ref=handoff_event.event_id,
                        approval_id=handoff.approval_id,
                        payload_hash=handoff.payload_hash,
                        data={
                            "approval_id": handoff.approval_id,
                            "reason_code": "TASK_ESCALATED",
                            "target": "handoff",
                        },
                    )
                    return _escalated_task_run(
                        task_def=task_def,
                        task_run_id=task_run_id,
                        agent_id=agent.agent_id,
                        input_payload={},
                        reason_code="TASK_ESCALATED",
                        approval_id=handoff.approval_id,
                        emit=emit,
                        causal_ref=approval_requested.event_id,
                    )
                if not handoff.allowed:
                    return _blocked_task_run(
                        task_def=task_def,
                        task_run_id=task_run_id,
                        agent_id=agent.agent_id,
                        reason_code="HANDOFF_DENY",
                        emit=emit,
                        phase="handoff",
                        causal_ref=handoff_event.event_id,
                        payload_hash_value=handoff.payload_hash,
                    )

                with lock:
                    if handoff_id in consumed_handoffs:
                        return _blocked_task_run(
                            task_def=task_def,
                            task_run_id=task_run_id,
                            agent_id=agent.agent_id,
                            reason_code="HANDOFF_REPLAY_BLOCKED",
                            emit=emit,
                            phase="handoff",
                            causal_ref=handoff_event.event_id,
                            payload_hash_value=handoff.payload_hash,
                        )
                    consumed_handoffs.add(handoff_id)
                if handoff.approval_id and self._governance_runtime is not None:
                    consume_result = self._governance_runtime.consume_approval(
                        approval_id=handoff.approval_id,
                        consumed_by_job_id=resolved_job_id,
                        execution_contract_hash=handoff_contract_hash,
                        resume_token_ref=handoff_resume_token_ref,
                    )
                    if consume_result.error_code is None:
                        emit(
                            "approval_consumed",
                            task_id=task_def.task_id,
                            task_run_id=task_run_id,
                            task_attempt=1,
                            agent_id=agent.agent_id,
                            role=task_def.role,
                            phase="approval",
                            status_before="executed",
                            status_after="consumed",
                            causal_ref=handoff_event.event_id,
                            approval_id=handoff.approval_id,
                            payload_hash=handoff.payload_hash,
                            resume_token_ref=handoff_resume_token_ref,
                            data={"approval_id": handoff.approval_id, "target": "handoff"},
                        )

                dependency_snippets.append(str(handoff.payload.get("output", "")))
                dependency_events.append(handoff_event.event_id)

            requested_scope, requested_visibility = _requested_memory_target(agent)
            task_override = _task_override(
                approval_overrides, task_id=task_def.task_id, target="task"
            )
            task_override_ticket = (
                self._governance_runtime.get_approval(task_override)
                if self._governance_runtime is not None and task_override
                else None
            )
            task_override_contract = (
                task_override_ticket.snapshot.get("execution_contract", {})
                if task_override_ticket is not None
                else {}
            )
            frozen_task_input = str(
                task_override_contract.get("canonical_task_input") or ""
            ).strip()
            frozen_memory_records = list(task_override_contract.get("resolved_memory_refs") or [])
            frozen_memory_fingerprint = str(
                task_override_contract.get("resolved_memory_fingerprint") or ""
            ).strip()
            task_input = _build_task_input(
                request=request,
                task=task_def,
                dependency_snippets=dependency_snippets,
            )
            memory_context: dict[str, Any] = {
                "snippets": [],
                "refs": [],
                "fingerprint": None,
                "records": [],
                "count": 0,
                "reason": "empty",
            }
            if task_def.depends_on:
                if (
                    continuation
                    and task_override_ticket is not None
                    and task_override_ticket.target_kind == "task"
                    and frozen_task_input
                ):
                    memory_attempt = emit(
                        "memory_read_attempt",
                        task_id=task_def.task_id,
                        task_run_id=task_run_id,
                        task_attempt=1,
                        agent_id=agent.agent_id,
                        role=task_def.role,
                        phase="memory",
                        status_before="ready",
                        status_after="allowed",
                        causal_ref=task_last_event.get(task_run_id),
                        data={
                            "scope": requested_scope,
                            "visibility": requested_visibility,
                            "source": "approval_snapshot",
                        },
                    )
                    memory_context = {
                        "snippets": [],
                        "refs": [
                            item.get("id")
                            for item in frozen_memory_records
                            if isinstance(item, dict) and item.get("id") is not None
                        ],
                        "fingerprint": frozen_memory_fingerprint or None,
                        "records": frozen_memory_records,
                        "count": len(frozen_memory_records),
                        "reason": "frozen_snapshot",
                    }
                    emit(
                        "memory_read_succeeded",
                        task_id=task_def.task_id,
                        task_run_id=task_run_id,
                        task_attempt=1,
                        agent_id=agent.agent_id,
                        role=task_def.role,
                        phase="memory",
                        status_before="allowed",
                        status_after="read",
                        causal_ref=memory_attempt.event_id,
                        resolved_memory_fingerprint=frozen_memory_fingerprint or None,
                        data={
                            "scope": requested_scope,
                            "visibility": requested_visibility,
                            "count": len(frozen_memory_records),
                            "reason": "frozen_snapshot",
                            "refs": list(memory_context.get("refs", [])),
                        },
                    )
                    task_input = frozen_task_input
                elif requested_scope is None or requested_visibility is None:
                    emit(
                        "memory_read_blocked",
                        task_id=task_def.task_id,
                        task_run_id=task_run_id,
                        task_attempt=1,
                        agent_id=agent.agent_id,
                        role=task_def.role,
                        phase="memory",
                        status_before="ready",
                        status_after="blocked",
                        causal_ref=task_last_event.get(task_run_id),
                        data={"reason_code": "MEMORY_SCOPE_UNDECLARED"},
                    )
                else:
                    access_check = validate_memory_access(
                        declared_scopes=list(getattr(agent, "memory_scope_access", [])),
                        requested_scope=requested_scope,
                        requested_visibility=requested_visibility,
                    )
                    if not access_check.allowed:
                        emit(
                            "memory_read_blocked",
                            task_id=task_def.task_id,
                            task_run_id=task_run_id,
                            task_attempt=1,
                            agent_id=agent.agent_id,
                            role=task_def.role,
                            phase="memory",
                            status_before="ready",
                            status_after="blocked",
                            causal_ref=task_last_event.get(task_run_id),
                            data={"reason_code": access_check.reason_code},
                        )
                    else:
                        memory_read_query = _memory_read_query(
                            request=request,
                            dependency_snippets=dependency_snippets,
                        )
                        memory_attempt = emit(
                            "memory_read_attempt",
                            task_id=task_def.task_id,
                            task_run_id=task_run_id,
                            task_attempt=1,
                            agent_id=agent.agent_id,
                            role=task_def.role,
                            phase="memory",
                            status_before="ready",
                            status_after="allowed",
                            causal_ref=task_last_event.get(task_run_id),
                            data={
                                "scope": requested_scope,
                                "visibility": requested_visibility,
                            },
                        )
                        memory_context = read_scoped_memory(
                            memory_manager=self._memory_manager,
                            query=memory_read_query,
                            scope=requested_scope,
                            team_id=spec.team.team_id,
                            case_id=resolved_case_id,
                            job_id=resolved_job_id,
                            visibility=requested_visibility,
                            memory_runtime_bridge=self._memory_runtime_bridge,
                            producer_agent_id=agent.agent_id,
                        )
                        snippets = [
                            str(item)
                            for item in memory_context.get("snippets", [])
                            if str(item).strip()
                        ]
                        emit(
                            "memory_read_succeeded",
                            task_id=task_def.task_id,
                            task_run_id=task_run_id,
                            task_attempt=1,
                            agent_id=agent.agent_id,
                            role=task_def.role,
                            phase="memory",
                            status_before="allowed",
                            status_after="read",
                            causal_ref=memory_attempt.event_id,
                            resolved_memory_fingerprint=str(memory_context.get("fingerprint") or "")
                            or None,
                            data={
                                "scope": requested_scope,
                                "visibility": requested_visibility,
                                "count": int(memory_context.get("count", 0) or 0),
                                "reason": str(memory_context.get("reason", "unknown")),
                                "refs": list(memory_context.get("refs", [])),
                            },
                        )
                        if snippets:
                            task_input = _append_memory_context(task_input, snippets)
            input_payload = {
                "input": task_input,
                "requested_scope": requested_scope,
                "requested_visibility": requested_visibility,
                "memory_target": task_def.memory_target,
            }
            contract_context = _contract_context(
                approval_ticket=task_override_ticket,
                default_task_run_id=task_run_id,
                default_task_attempt=1,
                default_branch_id=lineage["branch_id"],
                default_branch_parent=lineage["branch_parent"],
                default_causal_ancestry=dependency_events or [task_last_event.get(task_run_id, "")],
                default_root_run_id=lineage["root_run_id"],
                default_logical_task_id=lineage["logical_task_id"],
                default_lineage_hash=lineage["lineage_hash"],
                default_continuation_index=lineage["continuation_index"],
                default_checkpoint_generation=lineage["checkpoint_generation"],
            )
            governed_task_type = str(task_override_contract.get("target_ref") or task_def.task_type)

            def _build_task_contract(governed_target: str) -> dict[str, Any]:
                action_hash_value = (
                    self._governance_runtime.task_action_hash(
                        task_type=governed_target,
                        user_input=task_input,
                    )
                    if self._governance_runtime is not None
                    else payload_hash({"task_type": governed_target, "user_input": task_input})
                )
                return build_task_execution_contract(
                    task_run_id=contract_context["task_run_id"],
                    task_attempt=contract_context["task_attempt"],
                    task_type=governed_target,
                    target_ref=governed_target,
                    canonical_task_input=task_input,
                    action_payload_hash=action_hash_value,
                    policy_input_hash=payload_hash(
                        {"task_type": governed_target, "user_input": task_input}
                    ),
                    resolved_memory_refs=list(memory_context.get("records", [])),
                    causal_ancestry=contract_context["causal_ancestry"],
                    branch_id=contract_context["branch_id"],
                    branch_parent=contract_context["branch_parent"],
                    root_run_id=contract_context["root_run_id"],
                    logical_task_id=contract_context["logical_task_id"],
                    lineage_hash=contract_context["lineage_hash"],
                    continuation_index=contract_context["continuation_index"],
                    checkpoint_generation=contract_context["checkpoint_generation"],
                )

            task_contract = _build_task_contract(governed_task_type)
            task_action_hash = str(task_contract.get("action_payload_hash") or "")
            task_resume_token_ref, task_contract_hash, task_snapshot_hash = _override_contract_refs(
                governance_runtime=self._governance_runtime,
                approval_id=task_override,
                task_run_id=task_run_id,
                target_kind="task",
                action_hash=task_action_hash,
                policy_hash=_policy_hash(self._governance_runtime),
                contract=task_contract,
            )

            if (
                agent.approval_mode == "always"
                and task_override is None
                and self._governance_runtime is not None
            ):
                manual_decision, manual_ticket = (
                    self._governance_runtime.request_manual_task_approval(
                        run_id=resolved_job_id,
                        task_type=task_def.task_type,
                        user_input=task_input,
                        reason_code="AGENT_APPROVAL_MODE_ALWAYS",
                        explain=f"agent {agent.agent_id} requires explicit task approval",
                    )
                )
                if manual_ticket is not None:
                    _attach_contract(
                        governance_runtime=self._governance_runtime,
                        approval_id=manual_ticket.approval_id,
                        source_job_id=resolved_job_id,
                        task_run_id=task_run_id,
                        target_kind="task",
                        action_hash=task_action_hash,
                        contract=task_contract,
                    )
                    approval_requested = emit(
                        "approval_requested",
                        task_id=task_def.task_id,
                        task_run_id=task_run_id,
                        task_attempt=1,
                        agent_id=agent.agent_id,
                        role=task_def.role,
                        phase="approval",
                        status_before="none",
                        status_after="pending",
                        causal_ref=task_last_event.get(task_run_id),
                        approval_id=manual_ticket.approval_id,
                        snapshot_hash=manual_ticket.snapshot_hash,
                        resolved_memory_fingerprint=task_contract.get(
                            "resolved_memory_fingerprint"
                        ),
                        data={
                            "approval_id": manual_ticket.approval_id,
                            "reason_code": manual_decision.reason_code,
                            "target": "task",
                        },
                    )
                    return _escalated_task_run(
                        task_def=task_def,
                        task_run_id=task_run_id,
                        agent_id=agent.agent_id,
                        input_payload=input_payload,
                        reason_code="AGENT_APPROVAL_MODE_ALWAYS",
                        approval_id=manual_ticket.approval_id,
                        emit=emit,
                        causal_ref=approval_requested.event_id,
                    )

            if task_override and self._governance_runtime is not None:
                if (
                    continuation
                    and task_override_contract.get("lineage_hash")
                    and str(task_override_contract.get("lineage_hash")) != lineage["lineage_hash"]
                ):
                    mismatch = emit(
                        "team.resume.lineage_mismatch",
                        task_id=task_def.task_id,
                        task_run_id=task_run_id,
                        task_attempt=1,
                        agent_id=agent.agent_id,
                        role=task_def.role,
                        phase="approval",
                        status_before="executed",
                        status_after="blocked",
                        approval_id=task_override,
                        causal_ref=task_last_event.get(task_run_id),
                        snapshot_hash=task_snapshot_hash,
                        resolved_memory_fingerprint=task_contract.get(
                            "resolved_memory_fingerprint"
                        ),
                        resume_token_ref=task_resume_token_ref,
                        data={
                            "reason_code": "RESUME_LINEAGE_MISMATCH",
                            "expected_lineage_hash": task_override_contract.get("lineage_hash"),
                            "observed_lineage_hash": lineage["lineage_hash"],
                        },
                    )
                    return _blocked_task_run(
                        task_def=task_def,
                        task_run_id=task_run_id,
                        agent_id=agent.agent_id,
                        reason_code="RESUME_LINEAGE_MISMATCH",
                        emit=emit,
                        causal_ref=mismatch.event_id,
                        input_payload=input_payload,
                        resume_status="stale",
                        stale_reason="RESUME_LINEAGE_MISMATCH",
                    )
                prepared = self._governance_runtime.prepare_resume_approval(
                    approval_id=task_override,
                    run_id=task_run_id,
                    task_run_id=task_run_id,
                    target_kind="task",
                    execution_contract_hash=task_contract_hash or payload_hash(task_contract),
                )
                if prepared.error_code:
                    resume_token_ref = (
                        prepared.ticket.resume_token_ref
                        if prepared.ticket
                        else task_resume_token_ref
                    )
                    if prepared.error_code in {
                        "RESUME_DUPLICATE_SUPPRESSED",
                        "RESUME_REPLAY_BLOCKED",
                    }:
                        suppressed = emit(
                            "resume_duplicate_suppressed",
                            task_id=task_def.task_id,
                            task_run_id=task_run_id,
                            task_attempt=1,
                            agent_id=agent.agent_id,
                            role=task_def.role,
                            phase="approval",
                            status_before="executed",
                            status_after="blocked",
                            approval_id=task_override,
                            causal_ref=task_last_event.get(task_run_id),
                            snapshot_hash=task_snapshot_hash,
                            resolved_memory_fingerprint=task_contract.get(
                                "resolved_memory_fingerprint"
                            ),
                            resume_token_ref=resume_token_ref,
                            data={"reason_code": prepared.error_code},
                        )
                        run = _blocked_task_run(
                            task_def=task_def,
                            task_run_id=task_run_id,
                            agent_id=agent.agent_id,
                            reason_code=prepared.error_code,
                            emit=emit,
                            causal_ref=suppressed.event_id,
                            input_payload=input_payload,
                            resume_status="duplicate_suppressed",
                            stale_reason=prepared.error_code,
                        )
                        resume_outcomes.append(
                            {
                                "task_id": task_def.task_id,
                                "approval_id": task_override,
                                "resume_status": "duplicate_suppressed",
                                "stale_reason": prepared.error_code,
                                "resume_token_ref": resume_token_ref,
                            }
                        )
                        return run

                    stale_event = emit(
                        "approval_stale",
                        task_id=task_def.task_id,
                        task_run_id=task_run_id,
                        task_attempt=1,
                        agent_id=agent.agent_id,
                        role=task_def.role,
                        phase="approval",
                        status_before="executed",
                        status_after="stale",
                        approval_id=task_override,
                        causal_ref=task_last_event.get(task_run_id),
                        snapshot_hash=task_snapshot_hash,
                        resolved_memory_fingerprint=task_contract.get(
                            "resolved_memory_fingerprint"
                        ),
                        resume_token_ref=resume_token_ref,
                        data={"reason_code": prepared.error_code},
                    )
                    emit(
                        "team.resume.snapshot_drift",
                        task_id=task_def.task_id,
                        task_run_id=task_run_id,
                        task_attempt=1,
                        agent_id=agent.agent_id,
                        role=task_def.role,
                        phase="approval",
                        status_before="executed",
                        status_after="stale",
                        approval_id=task_override,
                        causal_ref=stale_event.event_id,
                        snapshot_hash=task_snapshot_hash,
                        resolved_memory_fingerprint=task_contract.get(
                            "resolved_memory_fingerprint"
                        ),
                        resume_token_ref=resume_token_ref,
                        data={"reason_code": prepared.error_code},
                    )
                    replacement_decision, replacement_ticket = (
                        self._governance_runtime.evaluate_task(
                            run_id=resolved_job_id,
                            task_type=governed_task_type,
                            user_input=task_input,
                        )
                    )
                    replacement_id = None
                    if replacement_ticket is not None:
                        replacement_id = replacement_ticket.approval_id
                        _attach_contract(
                            governance_runtime=self._governance_runtime,
                            approval_id=replacement_id,
                            source_job_id=resolved_job_id,
                            task_run_id=task_run_id,
                            target_kind="task",
                            action_hash=task_action_hash,
                            contract=task_contract,
                        )
                        emit(
                            "approval_requested",
                            task_id=task_def.task_id,
                            task_run_id=task_run_id,
                            task_attempt=1,
                            agent_id=agent.agent_id,
                            role=task_def.role,
                            phase="approval",
                            status_before="none",
                            status_after="pending",
                            causal_ref=stale_event.event_id,
                            approval_id=replacement_id,
                            snapshot_hash=replacement_ticket.snapshot_hash,
                            resolved_memory_fingerprint=task_contract.get(
                                "resolved_memory_fingerprint"
                            ),
                            data={
                                "approval_id": replacement_id,
                                "reason_code": replacement_decision.reason_code,
                                "target": "task",
                                "replacement_for": task_override,
                            },
                        )
                    run = _escalated_task_run(
                        task_def=task_def,
                        task_run_id=task_run_id,
                        agent_id=agent.agent_id,
                        input_payload=input_payload,
                        reason_code=prepared.error_code,
                        approval_id=replacement_id,
                        emit=emit,
                        causal_ref=stale_event.event_id,
                        resume_status="stale",
                        stale_reason=prepared.error_code,
                    )
                    resume_outcomes.append(
                        {
                            "task_id": task_def.task_id,
                            "approval_id": task_override,
                            "replacement_approval_id": replacement_id,
                            "resume_status": "stale",
                            "stale_reason": prepared.error_code,
                            "resume_token_ref": resume_token_ref,
                        }
                    )
                    return run
                if prepared.ticket is not None:
                    task_resume_token_ref = (
                        prepared.ticket.resume_token_ref or task_resume_token_ref
                    )
                    task_snapshot_hash = prepared.ticket.snapshot_hash
                    emit(
                        "team.resume.approval_carry_forwarded",
                        task_id=task_def.task_id,
                        task_run_id=task_run_id,
                        task_attempt=1,
                        agent_id=agent.agent_id,
                        role=task_def.role,
                        phase="approval",
                        status_before="executed",
                        status_after="carry_forwarded",
                        approval_id=task_override,
                        causal_ref=task_last_event.get(task_run_id),
                        snapshot_hash=task_snapshot_hash,
                        resolved_memory_fingerprint=task_contract.get(
                            "resolved_memory_fingerprint"
                        ),
                        resume_token_ref=task_resume_token_ref,
                        data={
                            "lineage_hash": contract_context["lineage_hash"],
                            "logical_task_id": contract_context["logical_task_id"],
                            "continuation_index": contract_context["continuation_index"],
                            "checkpoint_generation": contract_context["checkpoint_generation"],
                        },
                    )

            session_context = {
                "session_id": resolved_job_id,
                "team_id": spec.team.team_id,
                "case_id": resolved_case_id,
                "job_id": resolved_job_id,
                "task_id": task_def.task_id,
                "agent_id": agent.agent_id,
                "role": task_def.role,
                "task_run_id": task_run_id,
                "task_type": task_def.task_type,
            }
            if task_override:
                session_context["governance_approval_id"] = task_override
                session_context["governance_run_id"] = task_run_id
                if task_contract_hash:
                    session_context["governance_execution_contract_hash"] = task_contract_hash
                if task_resume_token_ref:
                    session_context["governance_resume_token_ref"] = task_resume_token_ref

            started_at: datetime | None = None
            finished_at: datetime | None = None
            result = None
            attempt_used = 0
            max_attempts = max(1, spec.team.termination_rules.max_retries + 1)
            serialized = bool(task_override)
            fallback_applied_event = None
            if serialized:
                fallback_applied_event = emit(
                    "fallback_mode_applied",
                    task_id=task_def.task_id,
                    task_run_id=task_run_id,
                    task_attempt=1,
                    agent_id=agent.agent_id,
                    role=task_def.role,
                    phase="task",
                    status_before="ready",
                    status_after="serialized",
                    causal_ref=task_last_event.get(task_run_id),
                    approval_id=task_override,
                    snapshot_hash=task_snapshot_hash,
                    resolved_memory_fingerprint=task_contract.get("resolved_memory_fingerprint"),
                    resume_token_ref=task_resume_token_ref,
                    fallback_mode_applied="bounded_serial_subtree",
                    serialized_due_to_policy=True,
                    data={"reason_code": "APPROVAL_GATED_SUBTREE"},
                )

            def _run_once() -> None:
                nonlocal result, started_at, finished_at, attempt_used
                for attempt in range(1, max_attempts + 1):
                    attempt_used = attempt
                    started_at = datetime.now(UTC)
                    start_event = emit(
                        "task_started",
                        task_id=task_def.task_id,
                        task_run_id=task_run_id,
                        task_attempt=attempt,
                        role=task_def.role,
                        agent_id=agent.agent_id,
                        phase="task",
                        status_before="pending" if attempt == 1 else "retrying",
                        status_after="running",
                        causal_ref=task_last_event.get(task_run_id),
                        approval_id=task_override,
                        snapshot_hash=task_snapshot_hash,
                        resolved_memory_fingerprint=task_contract.get(
                            "resolved_memory_fingerprint"
                        ),
                        resume_token_ref=task_resume_token_ref,
                        serialized_due_to_policy=serialized,
                        data={"attempt": attempt},
                    )
                    try:
                        if (
                            task_def.task_type == "chat"
                            and _is_team_fast_chat_candidate(task_input)
                            and hasattr(self._orchestrator, "process_fast_chat")
                        ):
                            result = self._orchestrator.process_fast_chat(
                                task_input,
                                session_context=session_context,
                                stream=False,
                                candidate_reason="team_chat_task",
                            )
                        else:
                            result = self._orchestrator.process(
                                task_input,
                                session_context=session_context,
                                use_router=True,
                            )
                        finished_at = datetime.now(UTC)
                        return
                    except Exception as exc:  # noqa: BLE001
                        finished_at = datetime.now(UTC)
                        if attempt < max_attempts:
                            emit(
                                "task_retry",
                                task_id=task_def.task_id,
                                task_run_id=task_run_id,
                                task_attempt=attempt,
                                role=task_def.role,
                                agent_id=agent.agent_id,
                                phase="task",
                                status_before="running",
                                status_after="retrying",
                                causal_ref=start_event.event_id,
                                data={
                                    "reason_code": f"TASK_EXEC_EXCEPTION:{type(exc).__name__}",
                                    "attempt": attempt,
                                },
                                serialized_due_to_policy=serialized,
                            )
                            continue
                        raise

            try:
                if serialized:
                    with protected_execution_lock:
                        _run_once()
                else:
                    _run_once()
            except Exception as exc:  # noqa: BLE001
                failed = emit(
                    "task_failed",
                    task_id=task_def.task_id,
                    task_run_id=task_run_id,
                    task_attempt=attempt_used,
                    role=task_def.role,
                    agent_id=agent.agent_id,
                    phase="task",
                    status_before="running",
                    status_after="failed",
                    causal_ref=task_last_event.get(task_run_id),
                    approval_id=task_override,
                    snapshot_hash=task_snapshot_hash,
                    resolved_memory_fingerprint=task_contract.get("resolved_memory_fingerprint"),
                    resume_token_ref=task_resume_token_ref,
                    serialized_due_to_policy=serialized,
                    data={"reason_code": f"TASK_EXEC_EXCEPTION:{type(exc).__name__}"},
                )
                emit(
                    "safe_abort",
                    task_id=task_def.task_id,
                    task_run_id=task_run_id,
                    task_attempt=attempt_used,
                    role=task_def.role,
                    agent_id=agent.agent_id,
                    phase="task",
                    status_before="running",
                    status_after="failed",
                    causal_ref=failed.event_id,
                    approval_id=task_override,
                    data={"reason_code": f"TASK_EXEC_EXCEPTION:{type(exc).__name__}"},
                    serialized_due_to_policy=serialized,
                )
                if fallback_applied_event is not None:
                    emit(
                        "fallback_mode_released",
                        task_id=task_def.task_id,
                        task_run_id=task_run_id,
                        task_attempt=attempt_used,
                        role=task_def.role,
                        agent_id=agent.agent_id,
                        phase="task",
                        status_before="serialized",
                        status_after="failed",
                        causal_ref=fallback_applied_event.event_id,
                        fallback_mode_applied="bounded_serial_subtree",
                        serialized_due_to_policy=True,
                        data={"reason_code": "TASK_FAILED"},
                    )
                run = TaskRun(
                    task_id=task_def.task_id,
                    task_run_id=task_run_id,
                    assigned_agent_id=agent.agent_id,
                    role=task_def.role,
                    task_attempt=attempt_used,
                    requested_scope=requested_scope,
                    requested_visibility=requested_visibility,
                    memory_target=task_def.memory_target,
                    input_payload=input_payload,
                    status=TaskStatus.FAILED,
                    attempt_count=attempt_used,
                    approval_state="none",
                    reason_code=f"TASK_EXEC_EXCEPTION:{type(exc).__name__}",
                    started_at=started_at,
                    finished_at=finished_at,
                    result_payload={
                        "resume_status": "failed",
                        "resume_token_ref": task_resume_token_ref,
                    },
                )
                with lock:
                    task_runs[task_def.task_id] = run
                return run

            if result is None:
                return _failed_task_run(
                    task_def=task_def,
                    task_run_id=task_run_id,
                    agent_id=agent.agent_id,
                    input_payload=input_payload,
                    requested_scope=requested_scope,
                    requested_visibility=requested_visibility,
                    memory_target=task_def.memory_target,
                    reason_code="TASK_RESULT_MISSING",
                    started_at=started_at,
                    finished_at=finished_at,
                )

            status = TaskStatus.COMPLETED
            reason_code = None
            approval_state = "none"
            approval_id = None
            if result.used_path == "governance_pending":
                if agent.approval_mode == "never":
                    status = TaskStatus.BLOCKED
                    reason_code = "AGENT_APPROVAL_MODE_DENY"
                else:
                    status = TaskStatus.ESCALATED
                    reason_code = "TASK_ESCALATED"
                    approval_state = "pending"
                    approval_id = str(result.metrics.get("approval_id") or "").strip() or None
                    if approval_id and self._governance_runtime is not None:
                        approval_target = str(
                            result.metrics.get("governance_target")
                            or task_contract.get("target_ref")
                            or governed_task_type
                        )
                        approval_task_contract = (
                            task_contract
                            if approval_target == str(task_contract.get("target_ref") or "")
                            else _build_task_contract(approval_target)
                        )
                        approval_action_hash = str(
                            approval_task_contract.get("action_payload_hash") or task_action_hash
                        )
                        _attach_contract(
                            governance_runtime=self._governance_runtime,
                            approval_id=approval_id,
                            source_job_id=resolved_job_id,
                            task_run_id=task_run_id,
                            target_kind="task",
                            action_hash=approval_action_hash,
                            contract=approval_task_contract,
                        )
                        ticket = self._governance_runtime.get_approval(approval_id)
                        approval_requested = emit(
                            "approval_requested",
                            task_id=task_def.task_id,
                            task_run_id=task_run_id,
                            task_attempt=attempt_used,
                            agent_id=agent.agent_id,
                            role=task_def.role,
                            phase="approval",
                            status_before="none",
                            status_after="pending",
                            causal_ref=task_last_event.get(task_run_id),
                            approval_id=approval_id,
                            trace_id=result.trace_id,
                            snapshot_hash=ticket.snapshot_hash if ticket else None,
                            resolved_memory_fingerprint=approval_task_contract.get(
                                "resolved_memory_fingerprint"
                            ),
                            data={
                                "approval_id": approval_id,
                                "reason_code": "TASK_ESCALATED",
                                "target": "task",
                            },
                        )
                    else:
                        approval_requested = None
                    if approval_requested is not None:
                        task_last_event[task_run_id] = approval_requested.event_id
            elif result.used_path == "governance_blocked":
                status = TaskStatus.BLOCKED
                reason_code = str(result.metrics.get("governance_reason_code", "POLICY_DENY"))

            if (
                status == TaskStatus.COMPLETED
                and task_override
                and self._governance_runtime is not None
            ):
                consume_result = self._governance_runtime.consume_approval(
                    approval_id=task_override,
                    consumed_by_job_id=resolved_job_id,
                    execution_contract_hash=task_contract_hash,
                    resume_token_ref=task_resume_token_ref,
                )
                if consume_result.error_code is None:
                    emit(
                        "approval_consumed",
                        task_id=task_def.task_id,
                        task_run_id=task_run_id,
                        task_attempt=attempt_used,
                        agent_id=agent.agent_id,
                        role=task_def.role,
                        phase="approval",
                        status_before="executed",
                        status_after="consumed",
                        causal_ref=task_last_event.get(task_run_id),
                        approval_id=task_override,
                        trace_id=result.trace_id,
                        snapshot_hash=task_snapshot_hash,
                        resolved_memory_fingerprint=task_contract.get(
                            "resolved_memory_fingerprint"
                        ),
                        resume_token_ref=task_resume_token_ref,
                        data={"approval_id": task_override, "target": "task"},
                    )
                resume_outcomes.append(
                    {
                        "task_id": task_def.task_id,
                        "approval_id": task_override,
                        "resume_status": (
                            "consumed" if consume_result.error_code is None else "consume_failed"
                        ),
                        "stale_reason": consume_result.error_code,
                        "resume_token_ref": task_resume_token_ref,
                    }
                )

            memory_write_override = _task_override(
                approval_overrides,
                task_id=task_def.task_id,
                target="memory_write",
            )
            memory_write_override_ticket = (
                self._governance_runtime.get_approval(memory_write_override)
                if self._governance_runtime is not None and memory_write_override
                else None
            )
            expected_state_version = None
            if (
                status == TaskStatus.COMPLETED
                and task_def.memory_target
                and requested_scope in {"team", "case"}
            ):
                target_version_reader = getattr(self._memory_manager, "target_version", None)
                if callable(target_version_reader):
                    expected_state_version = int(
                        target_version_reader(
                            scope=requested_scope,
                            team_id=spec.team.team_id,
                            case_id=resolved_case_id,
                            visibility=requested_visibility or "team",
                            memory_target=task_def.memory_target,
                        )
                    )
                elif (
                    self._memory_runtime_bridge is not None
                    and self._memory_runtime_bridge.enabled
                ):
                    owner = spec.team.team_id if requested_scope == "team" else resolved_case_id
                    expected_state_version = int(
                        self._memory_runtime_bridge.authority.store.target_version(
                            scope=MemoryScope(requested_scope),
                            owner_type=(
                                MemoryOwnerType.TEAM
                                if requested_scope == "team"
                                else MemoryOwnerType.CASE
                            ),
                            owner_id_hash=hash_identity(owner),
                            visibility=MemoryVisibility(requested_visibility or "team"),
                            namespace="default",
                            memory_target=task_def.memory_target,
                        )
                    )

            if status == TaskStatus.COMPLETED and (
                requested_scope is None or requested_visibility is None
            ):
                emit(
                    "memory_write_blocked",
                    task_id=task_def.task_id,
                    task_run_id=task_run_id,
                    task_attempt=attempt_used,
                    agent_id=agent.agent_id,
                    role=task_def.role,
                    phase="memory",
                    status_before="ready",
                    status_after="blocked",
                    causal_ref=task_last_event.get(task_run_id),
                    trace_id=result.trace_id,
                    data={"reason_code": "MEMORY_SCOPE_UNDECLARED"},
                )
                status = TaskStatus.BLOCKED
                reason_code = "MEMORY_SCOPE_UNDECLARED"
            elif status == TaskStatus.COMPLETED:
                access_check = validate_memory_access(
                    declared_scopes=list(getattr(agent, "memory_scope_access", [])),
                    requested_scope=requested_scope,
                    requested_visibility=requested_visibility,
                )
                if not access_check.allowed:
                    emit(
                        "memory_write_blocked",
                        task_id=task_def.task_id,
                        task_run_id=task_run_id,
                        task_attempt=attempt_used,
                        agent_id=agent.agent_id,
                        role=task_def.role,
                        phase="memory",
                        status_before="ready",
                        status_after="blocked",
                        causal_ref=task_last_event.get(task_run_id),
                        trace_id=result.trace_id,
                        data={"reason_code": access_check.reason_code},
                    )
                    status = TaskStatus.BLOCKED
                    reason_code = access_check.reason_code
                else:
                    memory_action_hash = (
                        self._governance_runtime.memory_action_hash(
                            scope=requested_scope,
                            producer_role=task_def.role,
                            visibility=requested_visibility,
                            memory_target=task_def.memory_target,
                            expected_state_version=expected_state_version,
                        )
                        if self._governance_runtime is not None
                        else payload_hash(
                            {
                                "scope": requested_scope,
                                "producer_role": task_def.role,
                                "visibility": requested_visibility,
                                "memory_target": task_def.memory_target,
                                "expected_state_version": expected_state_version,
                            }
                        )
                    )
                    memory_target_ref = (
                        f"{requested_scope}:{task_def.role}:{requested_visibility}:"
                        f"{task_def.memory_target or ''}"
                    )
                    memory_contract_context = _contract_context(
                        approval_ticket=memory_write_override_ticket,
                        default_task_run_id=task_run_id,
                        default_task_attempt=attempt_used,
                        default_branch_id=lineage["branch_id"],
                        default_branch_parent=lineage["branch_parent"],
                        default_causal_ancestry=dependency_events
                        or [task_last_event.get(task_run_id, "")],
                        default_root_run_id=lineage["root_run_id"],
                        default_logical_task_id=lineage["logical_task_id"],
                        default_lineage_hash=lineage["lineage_hash"],
                        default_continuation_index=lineage["continuation_index"],
                        default_checkpoint_generation=lineage["checkpoint_generation"],
                    )
                    memory_contract = build_memory_write_execution_contract(
                        task_run_id=memory_contract_context["task_run_id"],
                        task_attempt=memory_contract_context["task_attempt"],
                        target_ref=memory_target_ref,
                        canonical_task_input=task_input,
                        action_payload_hash=memory_action_hash,
                        policy_input_hash=payload_hash(
                            {
                                "scope": requested_scope,
                                "role": task_def.role,
                                "visibility": requested_visibility,
                                "memory_target": task_def.memory_target,
                                "expected_state_version": expected_state_version,
                            }
                        ),
                        resolved_memory_refs=list(memory_context.get("records", [])),
                        causal_ancestry=memory_contract_context["causal_ancestry"],
                        branch_id=memory_contract_context["branch_id"],
                        branch_parent=memory_contract_context["branch_parent"],
                        memory_target=task_def.memory_target,
                        expected_state_version=expected_state_version,
                        root_run_id=memory_contract_context["root_run_id"],
                        logical_task_id=memory_contract_context["logical_task_id"],
                        lineage_hash=memory_contract_context["lineage_hash"],
                        continuation_index=memory_contract_context["continuation_index"],
                        checkpoint_generation=memory_contract_context["checkpoint_generation"],
                    )
                    memory_resume_token_ref, memory_contract_hash, _memory_snapshot_hash = (
                        _override_contract_refs(
                            governance_runtime=self._governance_runtime,
                            approval_id=memory_write_override,
                            task_run_id=task_run_id,
                            target_kind="memory_write",
                            action_hash=memory_action_hash,
                            policy_hash=_policy_hash(self._governance_runtime),
                            contract=memory_contract,
                        )
                    )
                    scope_decision = evaluate_memory_scope_write(
                        governance_runtime=self._governance_runtime,
                        run_id=resolved_job_id,
                        scope=requested_scope,
                        producer_role=task_def.role,
                        visibility=requested_visibility,
                        override_approval_id=memory_write_override,
                        memory_target=task_def.memory_target,
                        expected_state_version=expected_state_version,
                        execution_contract_hash=memory_contract_hash,
                        resume_token_ref=memory_resume_token_ref,
                    )
                    memory_attempt = emit(
                        "memory_write_attempt",
                        task_id=task_def.task_id,
                        task_run_id=task_run_id,
                        task_attempt=attempt_used,
                        agent_id=agent.agent_id,
                        role=task_def.role,
                        phase="memory",
                        status_before="ready",
                        status_after=(
                            "approval_pending"
                            if scope_decision.requires_approval
                            else "allowed"
                            if scope_decision.allowed
                            else "blocked"
                        ),
                        causal_ref=task_last_event.get(task_run_id),
                        approval_id=scope_decision.approval_id,
                        trace_id=result.trace_id,
                        resolved_memory_fingerprint=task_contract.get(
                            "resolved_memory_fingerprint"
                        ),
                        memory_target=task_def.memory_target,
                        expected_state_version=expected_state_version,
                        resume_token_ref=memory_resume_token_ref,
                        data={
                            "scope": requested_scope,
                            "visibility": requested_visibility,
                            "reason_code": scope_decision.reason_code,
                        },
                    )
                    if scope_decision.requires_approval:
                        if scope_decision.approval_id and self._governance_runtime is not None:
                            _attach_contract(
                                governance_runtime=self._governance_runtime,
                                approval_id=scope_decision.approval_id,
                                source_job_id=resolved_job_id,
                                task_run_id=task_run_id,
                                target_kind="memory_write",
                                action_hash=memory_action_hash,
                                contract=memory_contract,
                            )
                        if agent.approval_mode == "never":
                            emit(
                                "memory_write_blocked",
                                task_id=task_def.task_id,
                                task_run_id=task_run_id,
                                task_attempt=attempt_used,
                                agent_id=agent.agent_id,
                                role=task_def.role,
                                phase="memory",
                                status_before="ready",
                                status_after="blocked",
                                causal_ref=memory_attempt.event_id,
                                approval_id=scope_decision.approval_id,
                                trace_id=result.trace_id,
                                data={"reason_code": "AGENT_APPROVAL_MODE_DENY"},
                            )
                            status = TaskStatus.BLOCKED
                            reason_code = "AGENT_APPROVAL_MODE_DENY"
                        else:
                            emit(
                                "memory_write_blocked",
                                task_id=task_def.task_id,
                                task_run_id=task_run_id,
                                task_attempt=attempt_used,
                                agent_id=agent.agent_id,
                                role=task_def.role,
                                phase="memory",
                                status_before="ready",
                                status_after="approval_pending",
                                causal_ref=memory_attempt.event_id,
                                approval_id=scope_decision.approval_id,
                                trace_id=result.trace_id,
                                data={
                                    "reason_code": "TASK_ESCALATED",
                                    "approval_id": scope_decision.approval_id,
                                },
                            )
                            emit(
                                "approval_requested",
                                task_id=task_def.task_id,
                                task_run_id=task_run_id,
                                task_attempt=attempt_used,
                                agent_id=agent.agent_id,
                                role=task_def.role,
                                phase="approval",
                                status_before="none",
                                status_after="pending",
                                causal_ref=memory_attempt.event_id,
                                approval_id=scope_decision.approval_id,
                                trace_id=result.trace_id,
                                data={
                                    "approval_id": scope_decision.approval_id,
                                    "reason_code": "TASK_ESCALATED",
                                    "target": "memory_write",
                                },
                            )
                            status = TaskStatus.ESCALATED
                            reason_code = "TASK_ESCALATED"
                            approval_state = "pending"
                            approval_id = scope_decision.approval_id
                    elif not scope_decision.allowed:
                        emit(
                            "memory_write_blocked",
                            task_id=task_def.task_id,
                            task_run_id=task_run_id,
                            task_attempt=attempt_used,
                            agent_id=agent.agent_id,
                            role=task_def.role,
                            phase="memory",
                            status_before="ready",
                            status_after="blocked",
                            causal_ref=memory_attempt.event_id,
                            trace_id=result.trace_id,
                            data={"reason_code": "MEMORY_SCOPE_DENY"},
                        )
                        status = TaskStatus.BLOCKED
                        reason_code = "MEMORY_SCOPE_DENY"
                    else:
                        memory_write = write_scoped_memory(
                            memory_manager=self._memory_manager,
                            session_id=resolved_job_id,
                            task_type=task_def.task_type,
                            user_input=task_input,
                            assistant_output=result.final_text,
                            scope=requested_scope,
                            team_id=spec.team.team_id,
                            case_id=resolved_case_id,
                            job_id=resolved_job_id,
                            producer_agent_id=agent.agent_id,
                            producer_role=task_def.role,
                            visibility=requested_visibility,
                            memory_target=task_def.memory_target,
                            expected_state_version=expected_state_version,
                            memory_runtime_bridge=self._memory_runtime_bridge,
                        )
                        if memory_write.get("conflict_detected"):
                            detected = emit(
                                "memory_conflict_detected",
                                task_id=task_def.task_id,
                                task_run_id=task_run_id,
                                task_attempt=attempt_used,
                                agent_id=agent.agent_id,
                                role=task_def.role,
                                phase="memory",
                                status_before="allowed",
                                status_after="conflict",
                                causal_ref=memory_attempt.event_id,
                                trace_id=result.trace_id,
                                memory_target=task_def.memory_target,
                                expected_state_version=expected_state_version,
                                committed_state_version=memory_write.get("committed_state_version"),
                                conflict_detected=True,
                                conflict_resolution="reject",
                                data={"reason_code": "MEMORY_CONFLICT"},
                            )
                            emit(
                                "memory_conflict_rejected",
                                task_id=task_def.task_id,
                                task_run_id=task_run_id,
                                task_attempt=attempt_used,
                                agent_id=agent.agent_id,
                                role=task_def.role,
                                phase="memory",
                                status_before="conflict",
                                status_after="blocked",
                                causal_ref=detected.event_id,
                                trace_id=result.trace_id,
                                memory_target=task_def.memory_target,
                                expected_state_version=expected_state_version,
                                committed_state_version=memory_write.get("committed_state_version"),
                                conflict_detected=True,
                                conflict_resolution="reject",
                                data={"reason_code": "MEMORY_CONFLICT"},
                            )
                            status = TaskStatus.BLOCKED
                            reason_code = "MEMORY_CONFLICT"
                        else:
                            emit(
                                "memory_write_succeeded",
                                task_id=task_def.task_id,
                                task_run_id=task_run_id,
                                task_attempt=attempt_used,
                                agent_id=agent.agent_id,
                                role=task_def.role,
                                phase="memory",
                                status_before="allowed",
                                status_after="written",
                                causal_ref=memory_attempt.event_id,
                                trace_id=result.trace_id,
                                memory_target=task_def.memory_target,
                                expected_state_version=memory_write.get("expected_state_version"),
                                committed_state_version=memory_write.get("committed_state_version"),
                                data={
                                    "scope": requested_scope,
                                    "visibility": requested_visibility,
                                    "record_id": memory_write.get("record_id"),
                                    "written": memory_write.get("written"),
                                    "reason": memory_write.get("reason"),
                                },
                            )
                            if scope_decision.approval_id and self._governance_runtime is not None:
                                consume_result = self._governance_runtime.consume_approval(
                                    approval_id=scope_decision.approval_id,
                                    consumed_by_job_id=resolved_job_id,
                                    execution_contract_hash=memory_contract_hash,
                                    resume_token_ref=memory_resume_token_ref,
                                )
                                if consume_result.error_code is None:
                                    emit(
                                        "approval_consumed",
                                        task_id=task_def.task_id,
                                        task_run_id=task_run_id,
                                        task_attempt=attempt_used,
                                        agent_id=agent.agent_id,
                                        role=task_def.role,
                                        phase="approval",
                                        status_before="executed",
                                        status_after="consumed",
                                        causal_ref=task_last_event.get(task_run_id),
                                        approval_id=scope_decision.approval_id,
                                        trace_id=result.trace_id,
                                        resume_token_ref=memory_resume_token_ref,
                                        data={
                                            "approval_id": scope_decision.approval_id,
                                            "target": "memory_write",
                                        },
                                    )

            terminal_event_name = "task_completed"
            terminal_status = "completed"
            if status == TaskStatus.ESCALATED:
                terminal_event_name = "task_escalated"
                terminal_status = "escalated"
            elif status == TaskStatus.BLOCKED:
                terminal_event_name = "task_blocked"
                terminal_status = "blocked"
            elif status == TaskStatus.FAILED:
                terminal_event_name = "task_failed"
                terminal_status = "failed"

            terminal = emit(
                terminal_event_name,
                task_id=task_def.task_id,
                task_run_id=task_run_id,
                task_attempt=attempt_used,
                agent_id=agent.agent_id,
                role=task_def.role,
                phase="task",
                status_before="running",
                status_after=terminal_status,
                causal_ref=task_last_event.get(task_run_id),
                approval_id=approval_id,
                trace_id=result.trace_id,
                snapshot_hash=task_snapshot_hash,
                resolved_memory_fingerprint=task_contract.get("resolved_memory_fingerprint"),
                resume_token_ref=task_resume_token_ref,
                serialized_due_to_policy=serialized,
                data={"reason_code": reason_code},
            )
            if status != TaskStatus.COMPLETED:
                emit(
                    "safe_abort",
                    task_id=task_def.task_id,
                    task_run_id=task_run_id,
                    task_attempt=attempt_used,
                    agent_id=agent.agent_id,
                    role=task_def.role,
                    phase="task",
                    status_before="running",
                    status_after=terminal_status,
                    causal_ref=terminal.event_id,
                    approval_id=approval_id,
                    trace_id=result.trace_id,
                    data={"reason_code": reason_code},
                    serialized_due_to_policy=serialized,
                )
            if fallback_applied_event is not None:
                emit(
                    "fallback_mode_released",
                    task_id=task_def.task_id,
                    task_run_id=task_run_id,
                    task_attempt=attempt_used,
                    role=task_def.role,
                    agent_id=agent.agent_id,
                    phase="task",
                    status_before="serialized",
                    status_after=terminal_status,
                    causal_ref=fallback_applied_event.event_id,
                    fallback_mode_applied="bounded_serial_subtree",
                    serialized_due_to_policy=True,
                    data={"reason_code": reason_code or "completed"},
                )

            run = TaskRun(
                task_id=task_def.task_id,
                task_run_id=task_run_id,
                assigned_agent_id=agent.agent_id,
                role=task_def.role,
                task_attempt=attempt_used,
                requested_scope=requested_scope,
                requested_visibility=requested_visibility,
                memory_target=task_def.memory_target,
                input_payload=input_payload,
                status=status,
                attempt_count=attempt_used,
                approval_state=approval_state,
                result_payload={
                    "output": result.final_text,
                    "metrics": result.metrics,
                    "trace_id": result.trace_id,
                    "agent_id": agent.agent_id,
                    "terminal_event_id": terminal.event_id,
                    "branch_id": branch_id,
                    "branch_parent": branch_parent,
                    "resume_status": "consumed"
                    if task_override and status == TaskStatus.COMPLETED
                    else "not_applicable",
                    "resume_token_ref": task_resume_token_ref,
                    "snapshot_hash": task_snapshot_hash,
                },
                reason_code=reason_code,
                started_at=started_at,
                finished_at=finished_at,
            )
            with lock:
                task_runs[task_def.task_id] = run
                if status == TaskStatus.COMPLETED:
                    task_outputs[task_def.task_id] = {
                        "output": result.final_text,
                        "trace_id": result.trace_id,
                        "agent_id": agent.agent_id,
                        "task_run_id": task_run_id,
                    }
            return run

        scheduler_result = scheduler.run(
            tasks=tasks,
            execute_task=execute_task,
            initially_completed=inherited_completed_task_ids,
        )
        ordered_runs = scheduler_result.tasks
        for item in ordered_runs:
            item_lineage = lineage_meta(item.task_id)
            item.result_payload.setdefault("branch_id", item_lineage["branch_id"])
            item.result_payload.setdefault("branch_parent", item_lineage["branch_parent"])
            item.result_payload.setdefault("lineage_hash", item_lineage["lineage_hash"])
            item.result_payload.setdefault("root_run_id", item_lineage["root_run_id"])
            item.result_payload.setdefault("logical_task_id", item_lineage["logical_task_id"])
            item.result_payload.setdefault(
                "continuation_index", item_lineage["continuation_index"]
            )
            item.result_payload.setdefault(
                "checkpoint_generation", item_lineage["checkpoint_generation"]
            )
            expected_task_run_id = task_run_ids.get(item.task_id)
            if expected_task_run_id and item.task_run_id != expected_task_run_id:
                item.task_run_id = expected_task_run_id
            if item.result_payload.get("terminal_event_id"):
                continue
            terminal_event_name = "task_completed"
            terminal_status = "completed"
            if item.status == TaskStatus.ESCALATED:
                terminal_event_name = "task_escalated"
                terminal_status = "escalated"
            elif item.status == TaskStatus.BLOCKED:
                terminal_event_name = "task_blocked"
                terminal_status = "blocked"
            elif item.status == TaskStatus.FAILED:
                terminal_event_name = "task_failed"
                terminal_status = "failed"
            terminal = emit(
                terminal_event_name,
                task_id=item.task_id,
                task_run_id=item.task_run_id,
                task_attempt=max(1, int(item.task_attempt or item.attempt_count or 1)),
                agent_id=item.assigned_agent_id if item.assigned_agent_id != "unassigned" else None,
                role=item.role,
                phase="task",
                status_before="pending",
                status_after=terminal_status,
                causal_ref=task_last_event.get(item.task_run_id),
                data={"reason_code": item.reason_code},
            )
            if item.status != TaskStatus.COMPLETED:
                emit(
                    "safe_abort",
                    task_id=item.task_id,
                    task_run_id=item.task_run_id,
                    task_attempt=max(1, int(item.task_attempt or item.attempt_count or 1)),
                    agent_id=item.assigned_agent_id
                    if item.assigned_agent_id != "unassigned"
                    else None,
                    role=item.role,
                    phase="task",
                    status_before="running",
                    status_after=terminal_status,
                    causal_ref=terminal.event_id,
                    data={"reason_code": item.reason_code},
                )
            item.result_payload["terminal_event_id"] = terminal.event_id

        last_completed = [item for item in ordered_runs if item.status == TaskStatus.COMPLETED]
        final_output = last_completed[-1].result_payload.get("output") if last_completed else None
        has_failed_tasks = any(item.status == TaskStatus.FAILED for item in ordered_runs)
        has_blocked_tasks = any(
            item.status in {TaskStatus.BLOCKED, TaskStatus.ESCALATED} for item in ordered_runs
        )
        if has_failed_tasks:
            job.status = JobStatus.FAILED
        elif has_blocked_tasks:
            job.status = JobStatus.BLOCKED
        elif scheduler_result.reason_code == "TEAM_DEADLOCK":
            job.status = JobStatus.FAILED
        else:
            job.status = JobStatus.COMPLETED

        job.finished_at = datetime.now(UTC)
        job.final_output = str(final_output) if final_output is not None else ""
        completed_count = len(
            [item for item in ordered_runs if item.status == TaskStatus.COMPLETED]
        )
        blocked_count = len(
            [
                item
                for item in ordered_runs
                if item.status in {TaskStatus.BLOCKED, TaskStatus.ESCALATED}
            ]
        )
        failed_count = len([item for item in ordered_runs if item.status == TaskStatus.FAILED])
        job.metrics = {
            "task_count": len(ordered_runs),
            "completed_count": completed_count,
            "blocked_count": blocked_count,
            "failed_count": failed_count,
            "reason_code": scheduler_result.reason_code,
            "resume_outcome_count": len(resume_outcomes),
            "root_run_id": root_run_id,
            "checkpoint_generation": checkpoint_generation,
            "continuation_index": continuation_index,
        }

        continuation_payload = _build_continuation_payload(
            spec_tasks=all_tasks,
            root_run_id=root_run_id,
            checkpoint_generation=checkpoint_generation,
            continuation_index=continuation_index,
            source_job_id=str(continuation.get("resume_source_job_id") or ""),
            inherited_task_lineage=inherited_task_lineage,
            inherited_completed_outputs=inherited_completed_outputs,
            scheduled_runs=ordered_runs,
        )

        if continuation:
            emit(
                "team.resume.completed",
                phase="team",
                status_before="continuing",
                status_after=job.status.value,
                data={
                    "root_run_id": root_run_id,
                    "checkpoint_generation": checkpoint_generation,
                    "continuation_index": continuation_index,
                    "resume_source_job_id": continuation.get("resume_source_job_id"),
                    "terminal_status": job.status.value,
                },
            )

        emit(
            "team_final",
            phase="team",
            status_before="running",
            status_after=job.status.value,
            data={
                "status": job.status.value,
                "reason_code": scheduler_result.reason_code,
                "task_count": len(ordered_runs),
            },
        )

        write_task_runs(paths, ordered_runs)
        write_handoffs(paths, handoffs)

        policy_bundle = getattr(self._governance_runtime, "_policy_bundle", None)  # noqa: SLF001
        policy_bundle_id = "disabled"
        policy_bundle_hash = "disabled"
        if policy_bundle is not None:
            policy_bundle_id = str(getattr(policy_bundle.policy, "policy_version", "unknown"))
            policy_bundle_hash = str(getattr(policy_bundle, "policy_hash", "unknown"))

        envelope_path = write_audit_envelope(
            paths=paths,
            job=job,
            tasks=ordered_runs,
            events=events,
            handoffs=handoffs,
            policy_bundle_id=policy_bundle_id,
            policy_bundle_hash=policy_bundle_hash,
            runtime_config_hash=_runtime_config_hash(self._config),
            config=self._config,
        )
        status_payload = {
            "job": job.model_dump(mode="json"),
            "tasks": [item.model_dump(mode="json") for item in ordered_runs],
            "audit_envelope_path": envelope_path,
            "job_dir": str(paths.job_dir),
            "resume_outcomes": resume_outcomes,
            "continuation": continuation_payload,
        }
        write_status(paths, status_payload)
        checkpoint_store.upsert(
            job_id=resolved_job_id,
            case_id=resolved_case_id,
            team_id=spec.team.team_id,
            status=job.status.value,
            payload={
                "reason_code": scheduler_result.reason_code,
                "task_count": len(ordered_runs),
                "audit_envelope_path": envelope_path,
                "continuation": continuation_payload,
            },
        )
        checkpoint_store.close()

        return TeamRunResult(
            job=job,
            tasks=ordered_runs,
            events=events,
            handoffs=handoffs,
            audit_envelope_path=envelope_path,
            resume_outcomes=resume_outcomes,
        )


def _finalize_early(
    *,
    paths,
    checkpoint_store: TeamCheckpointStore,
    job: JobRun,
    events: list[TeamEvent],
    handoffs: list[HandoffRecord],
    emit,
    reason_code: str,
    message: str,
    extra: dict[str, Any] | None = None,
) -> TeamRunResult:
    job.status = JobStatus.FAILED
    job.finished_at = datetime.now(UTC)
    job.final_output = message
    emit(
        "team_final",
        phase="team",
        status_before="running",
        status_after="failed",
        data={"reason_code": reason_code, **(extra or {})},
    )
    write_status(
        paths,
        {"job": job.model_dump(mode="json"), "reason_code": reason_code, **(extra or {})},
    )
    checkpoint_store.upsert(
        job_id=job.job_id,
        case_id=job.case_id,
        team_id=job.team_id,
        status=job.status.value,
        payload={"reason_code": reason_code, **(extra or {})},
    )
    checkpoint_store.close()
    return TeamRunResult(job=job, tasks=[], events=events, handoffs=handoffs)


def _resolve_tasks(spec: TeamSpec, request: str) -> list[TaskDefinition]:
    if spec.tasks:
        return spec.tasks

    role_index = _role_index(spec)
    intake = (
        role_index.get("intake agent")
        or role_index.get("case manager agent")
        or spec.team.agents[0].role
    )
    analyst = role_index.get("research analyst agent") or intake
    compliance = role_index.get("policy/compliance agent") or intake
    execution = role_index.get("execution agent") or intake
    reviewer = role_index.get("reviewer/qa agent") or intake

    complex_request = len(request.split()) >= 12
    if not complex_request:
        return [
            TaskDefinition(
                task_id="task-1",
                title="Single-pass response",
                task_type="chat",
                role=intake,
                depends_on=[],
                input_template="{{request}}",
            )
        ]

    return [
        TaskDefinition(
            task_id="task-1",
            title="Intake and normalization",
            task_type="plan",
            role=intake,
            depends_on=[],
            input_template="Normalize request for team execution: {{request}}",
        ),
        TaskDefinition(
            task_id="task-2",
            title="Research analysis",
            task_type="research",
            role=analyst,
            depends_on=["task-1"],
            input_template="Produce evidence and analysis from intake output.",
        ),
        TaskDefinition(
            task_id="task-3",
            title="Policy compliance check",
            task_type="plan",
            role=compliance,
            depends_on=["task-1"],
            input_template="Check policy and compliance constraints for the case.",
        ),
        TaskDefinition(
            task_id="task-4",
            title="Execution synthesis",
            task_type="mixed",
            role=execution,
            depends_on=["task-2", "task-3"],
            input_template="Synthesize actionable output from analysis + compliance.",
        ),
        TaskDefinition(
            task_id="task-5",
            title="Reviewer gate",
            task_type="chat",
            role=reviewer,
            depends_on=["task-4"],
            input_template="Review final output quality and safety; publish final response.",
        ),
    ]


def _build_task_input(*, request: str, task: TaskDefinition, dependency_snippets: list[str]) -> str:
    body = task.input_template or task.title
    if "{{request}}" in body:
        body = body.replace("{{request}}", request)
    if dependency_snippets:
        deps = "\n\n".join(dependency_snippets)
        return f"{body}\n\nDependencies:\n{deps}"
    return body


def _append_memory_context(task_input: str, snippets: list[str]) -> str:
    joined = "\n\n".join(snippets)
    return f"{task_input}\n\nScoped Memory Context:\n{joined}"


def _memory_read_query(*, request: str, dependency_snippets: list[str]) -> str:
    if dependency_snippets:
        return dependency_snippets[-1]
    return request


def _select_agent(spec: TeamSpec, role: str):
    lowered = role.strip().lower()
    for agent in spec.team.agents:
        if agent.role.strip().lower() == lowered:
            return agent
    raise ValueError(f"agent role not found: {role}")


def _role_index(spec: TeamSpec) -> dict[str, str]:
    return {item.role.strip().lower(): item.role for item in spec.team.agents}


def _runtime_config_hash(config: RuntimeConfig) -> str:
    payload = config.model_dump(mode="json")
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _team_parallelism(config: RuntimeConfig) -> int:
    team_cfg = getattr(config, "team", None)
    if team_cfg is None:
        return 2
    return int(getattr(team_cfg, "max_parallel_tasks", 2))


def _task_override(
    approval_overrides: dict[str, dict[str, str]] | None,
    *,
    task_id: str,
    target: str,
) -> str | None:
    if approval_overrides is None:
        return None
    task_map = approval_overrides.get(task_id)
    if not isinstance(task_map, dict):
        return None
    value = task_map.get(target)
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _task_run_id(job_id: str, task_id: str, attempt: int) -> str:
    return f"{job_id}:{task_id}:attempt-{attempt}"


def _handoff_id(*, source_task_run_id: str, dest_task_id: str, payload_hash: str) -> str:
    raw = f"{source_task_run_id}|{dest_task_id}|{payload_hash}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _requested_memory_target(agent) -> tuple[str | None, str | None]:
    scopes = [item.strip().lower() for item in getattr(agent, "memory_scope_access", [])]
    if "case" in scopes:
        return "case", "team"
    if "team" in scopes:
        return "team", "team"
    if "session" in scopes:
        return "session", "private"
    return None, None


def _handoff_allowed(spec: TeamSpec, from_role: str, to_role: str) -> bool:
    from_norm = from_role.strip().lower()
    to_norm = to_role.strip().lower()
    for rule in spec.team.handoff_rules:
        if rule.from_role.strip().lower() != from_norm:
            continue
        if rule.to_role.strip().lower() != to_norm:
            continue
        return bool(rule.required)
    return False


def _active_policy_profile(config: RuntimeConfig) -> str | None:
    policy_path = str(getattr(config.governance, "policy_path", "")).strip()
    if not policy_path:
        return None
    return Path(policy_path).stem or None


def _is_team_fast_chat_candidate(text: str) -> bool:
    normalized = text.strip().lower()
    if not normalized:
        return False
    if len(normalized) > 64:
        return False
    if len(normalized.split()) > 10:
        return False
    heavy_tokens = {
        "kod",
        "python",
        "test",
        "debug",
        "araştır",
        "research",
        "tool",
        "benchmark",
        "lint",
        "diff",
    }
    return not any(token in normalized for token in heavy_tokens)


def _task_branch_info(
    task_id: str,
    tasks_by_id: dict[str, TaskDefinition],
    cache: dict[str, tuple[str, str | None]],
) -> tuple[str, str | None]:
    if task_id in cache:
        return cache[task_id]
    task = tasks_by_id[task_id]
    if not task.depends_on:
        value = (f"branch:{task_id}", None)
        cache[task_id] = value
        return value
    parents = [
        _task_branch_info(dep_id, tasks_by_id, cache)[0]
        for dep_id in task.depends_on
        if dep_id in tasks_by_id
    ]
    parent_ref = ",".join(sorted(parents)) or None
    if len(parents) == 1:
        branch_id = f"{parents[0]}>{task_id}"
    else:
        branch_id = (
            f"branch:{task_id}:{hashlib.sha256(parent_ref.encode('utf-8')).hexdigest()[:10]}"
        )
    value = (branch_id, parent_ref)
    cache[task_id] = value
    return value


def _policy_hash(governance_runtime) -> str:
    if governance_runtime is None:
        return "disabled"
    return str(getattr(governance_runtime, "policy_hash", "disabled"))


def _attach_contract(
    *,
    governance_runtime,
    approval_id: str,
    source_job_id: str,
    task_run_id: str,
    target_kind: str,
    action_hash: str,
    contract: dict[str, Any],
) -> tuple[str | None, str | None]:
    ticket = governance_runtime.get_approval(approval_id)
    if ticket is None:
        return None, None
    new_snapshot_hash = payload_hash(
        {
            **ticket.snapshot,
            "execution_contract": contract,
        }
    )
    resume_token_ref, execution_contract_hash = derive_execution_contract_refs(
        source_job_id=source_job_id,
        approval_id=approval_id,
        snapshot_hash=new_snapshot_hash,
        target_kind=target_kind,
        policy_hash=_policy_hash(governance_runtime),
        contract=contract,
        fallback_action_hash=action_hash,
    )
    governance_runtime.attach_execution_contract(
        approval_id=approval_id,
        execution_contract=contract,
        execution_contract_hash=execution_contract_hash or "",
    )
    return resume_token_ref, execution_contract_hash


def _override_contract_refs(
    *,
    governance_runtime,
    approval_id: str | None,
    task_run_id: str,
    target_kind: str,
    action_hash: str,
    policy_hash: str,
    contract: dict[str, Any],
) -> tuple[str | None, str | None, str | None]:
    if governance_runtime is None or not approval_id:
        return None, None, None
    ticket = governance_runtime.get_approval(approval_id)
    if ticket is None:
        return None, None, None
    resume_token_ref, execution_contract_hash = derive_execution_contract_refs(
        source_job_id=ticket.run_id,
        approval_id=approval_id,
        snapshot_hash=ticket.snapshot_hash,
        target_kind=target_kind,
        policy_hash=policy_hash,
        contract=contract,
        fallback_action_hash=action_hash,
    )
    return resume_token_ref, execution_contract_hash, ticket.snapshot_hash


def _contract_context(
    *,
    approval_ticket,
    default_task_run_id: str,
    default_task_attempt: int,
    default_branch_id: str,
    default_branch_parent: str | None,
    default_causal_ancestry: list[str],
    default_root_run_id: str,
    default_logical_task_id: str,
    default_lineage_hash: str,
    default_continuation_index: int,
    default_checkpoint_generation: int,
) -> dict[str, Any]:
    contract = (
        approval_ticket.snapshot.get("execution_contract", {})
        if approval_ticket is not None
        else {}
    )
    continuation_value = contract.get("continuation_index")
    checkpoint_value = contract.get("checkpoint_generation")
    return {
        "task_run_id": str(contract.get("task_run_id") or default_task_run_id),
        "task_attempt": int(contract.get("task_attempt") or default_task_attempt or 1),
        "branch_id": str(contract.get("branch_id") or default_branch_id),
        "branch_parent": (
            str(contract.get("branch_parent"))
            if contract.get("branch_parent") is not None
            else default_branch_parent
        ),
        "causal_ancestry": list(contract.get("causal_ancestry") or default_causal_ancestry),
        "root_run_id": str(contract.get("root_run_id") or default_root_run_id),
        "logical_task_id": str(contract.get("logical_task_id") or default_logical_task_id),
        "lineage_hash": str(contract.get("lineage_hash") or default_lineage_hash),
        "continuation_index": int(
            continuation_value
            if continuation_value is not None
            else default_continuation_index or 0
        ),
        "checkpoint_generation": int(
            checkpoint_value
            if checkpoint_value is not None
            else default_checkpoint_generation or 0
        ),
    }


def _build_continuation_payload(
    *,
    spec_tasks: list[TaskDefinition],
    root_run_id: str,
    checkpoint_generation: int,
    continuation_index: int,
    source_job_id: str,
    inherited_task_lineage: dict[str, dict[str, Any]],
    inherited_completed_outputs: dict[str, dict[str, Any]],
    scheduled_runs: list[TaskRun],
) -> dict[str, Any]:
    children: dict[str, list[str]] = {}
    for task in spec_tasks:
        for dependency in task.depends_on:
            children.setdefault(dependency, []).append(task.task_id)

    lineage = {task_id: dict(value) for task_id, value in inherited_task_lineage.items()}
    completed_outputs = {
        task_id: dict(value) for task_id, value in inherited_completed_outputs.items()
    }
    completed_ids = {
        task_id
        for task_id, value in lineage.items()
        if str(value.get("terminal_status") or "").lower() == "completed"
    }
    blocked_ids = {
        task_id
        for task_id, value in lineage.items()
        if str(value.get("terminal_status") or "").lower() in {"blocked", "escalated"}
    }

    for run in scheduled_runs:
        result_payload = dict(run.result_payload or {})
        entry = dict(lineage.get(run.task_id) or {})
        entry.update(
            {
                "root_run_id": root_run_id,
                "logical_task_id": run.task_id,
                "task_run_id": run.task_run_id,
                "branch_id": result_payload.get("branch_id"),
                "branch_parent": result_payload.get("branch_parent"),
                "lineage_hash": result_payload.get("lineage_hash")
                or entry.get("lineage_hash")
                or payload_hash(
                    {
                        "root_run_id": root_run_id,
                        "logical_task_id": run.task_id,
                        "branch_id": result_payload.get("branch_id"),
                        "branch_parent": result_payload.get("branch_parent"),
                    }
                ),
                "continuation_index": continuation_index,
                "checkpoint_generation": checkpoint_generation,
                "terminal_event_id": result_payload.get("terminal_event_id"),
                "task_attempt": run.task_attempt,
                "terminal_status": run.status.value,
                "reason_code": run.reason_code,
            }
        )
        lineage[run.task_id] = entry
        if run.status == TaskStatus.COMPLETED:
            completed_ids.add(run.task_id)
            blocked_ids.discard(run.task_id)
            if result_payload.get("output"):
                completed_outputs[run.task_id] = {
                    "output": result_payload.get("output"),
                    "trace_id": result_payload.get("trace_id"),
                    "agent_id": result_payload.get("agent_id"),
                    "task_run_id": run.task_run_id,
                }
        elif run.status in {TaskStatus.BLOCKED, TaskStatus.ESCALATED}:
            blocked_ids.add(run.task_id)
            completed_ids.discard(run.task_id)
            completed_outputs.pop(run.task_id, None)
        else:
            blocked_ids.discard(run.task_id)
            completed_ids.discard(run.task_id)
            completed_outputs.pop(run.task_id, None)

    continuation_task_ids: set[str] = set()
    stack = list(blocked_ids)
    while stack:
        current = stack.pop()
        if current in continuation_task_ids or current in completed_ids:
            continue
        continuation_task_ids.add(current)
        stack.extend(children.get(current, []))

    blocked_nodes = []
    for task_id in sorted(blocked_ids):
        entry = dict(lineage.get(task_id) or {})
        blocked_nodes.append(
            {
                "job_id": source_job_id or None,
                "root_run_id": root_run_id,
                "task_id": task_id,
                "task_run_id": entry.get("task_run_id"),
                "blocked_reason": entry.get("reason_code"),
                "lineage_path": {
                    "logical_task_id": task_id,
                    "branch_id": entry.get("branch_id"),
                    "parent_branch_id": entry.get("branch_parent"),
                    "lineage_hash": entry.get("lineage_hash"),
                    "continuation_index": continuation_index,
                    "checkpoint_generation": checkpoint_generation,
                },
                "continuation_token": payload_hash(
                    {
                        "root_run_id": root_run_id,
                        "task_id": task_id,
                        "task_run_id": entry.get("task_run_id"),
                        "continuation_index": continuation_index,
                        "checkpoint_generation": checkpoint_generation,
                    }
                ),
            }
        )

    return {
        "root_run_id": root_run_id,
        "checkpoint_generation": checkpoint_generation,
        "continuation_index": continuation_index,
        "resume_source_job_id": source_job_id or None,
        "blocked_task_ids": sorted(blocked_ids),
        "blocked_nodes": blocked_nodes,
        "completed_task_ids": sorted(completed_ids),
        "upstream_completed_nodes": [
            {
                "task_id": task_id,
                "task_run_id": (lineage.get(task_id) or {}).get("task_run_id"),
                "lineage_hash": (lineage.get(task_id) or {}).get("lineage_hash"),
                "terminal_event_id": (lineage.get(task_id) or {}).get("terminal_event_id"),
            }
            for task_id in sorted(completed_ids)
        ],
        "continuation_task_ids": [
            task.task_id for task in spec_tasks if task.task_id in continuation_task_ids
        ],
        "completed_outputs": completed_outputs,
        "task_lineage": lineage,
    }


def _blocked_task_run(
    *,
    task_def: TaskDefinition,
    task_run_id: str,
    reason_code: str,
    emit,
    agent_id: str | None = None,
    phase: str = "task",
    causal_ref: str | None = None,
    approval_id: str | None = None,
    payload_hash_value: str | None = None,
    input_payload: dict[str, Any] | None = None,
    resume_status: str | None = None,
    stale_reason: str | None = None,
    extra: dict[str, Any] | None = None,
) -> TaskRun:
    blocked = emit(
        "task_blocked",
        task_id=task_def.task_id,
        task_run_id=task_run_id,
        task_attempt=1,
        role=task_def.role,
        agent_id=agent_id,
        phase=phase,
        status_before="pending",
        status_after="blocked",
        causal_ref=causal_ref,
        approval_id=approval_id,
        payload_hash=payload_hash_value,
        data={"reason_code": reason_code, **(extra or {})},
    )
    emit(
        "safe_abort",
        task_id=task_def.task_id,
        task_run_id=task_run_id,
        task_attempt=1,
        role=task_def.role,
        agent_id=agent_id,
        phase=phase,
        status_before="running",
        status_after="blocked",
        causal_ref=blocked.event_id,
        approval_id=approval_id,
        payload_hash=payload_hash_value,
        data={"reason_code": reason_code},
    )
    return TaskRun(
        task_id=task_def.task_id,
        task_run_id=task_run_id,
        assigned_agent_id=agent_id or "unassigned",
        role=task_def.role,
        input_payload=input_payload or {},
        status=TaskStatus.BLOCKED,
        task_attempt=1,
        attempt_count=1,
        reason_code=reason_code,
        approval_state="none",
        result_payload={
            "resume_status": resume_status or "not_applicable",
            "stale_reason": stale_reason,
        },
    )


def _escalated_task_run(
    *,
    task_def: TaskDefinition,
    task_run_id: str,
    agent_id: str,
    input_payload: dict[str, Any],
    reason_code: str,
    approval_id: str | None,
    emit,
    causal_ref: str | None,
    resume_status: str | None = None,
    stale_reason: str | None = None,
) -> TaskRun:
    escalated = emit(
        "task_escalated",
        task_id=task_def.task_id,
        task_run_id=task_run_id,
        task_attempt=1,
        agent_id=agent_id,
        role=task_def.role,
        phase="task",
        status_before="pending",
        status_after="escalated",
        causal_ref=causal_ref,
        approval_id=approval_id,
        data={"reason_code": reason_code},
    )
    emit(
        "safe_abort",
        task_id=task_def.task_id,
        task_run_id=task_run_id,
        task_attempt=1,
        agent_id=agent_id,
        role=task_def.role,
        phase="task",
        status_before="running",
        status_after="escalated",
        causal_ref=escalated.event_id,
        approval_id=approval_id,
        data={"reason_code": reason_code},
    )
    return TaskRun(
        task_id=task_def.task_id,
        task_run_id=task_run_id,
        assigned_agent_id=agent_id,
        role=task_def.role,
        input_payload=input_payload,
        status=TaskStatus.ESCALATED,
        task_attempt=1,
        attempt_count=1,
        reason_code=reason_code,
        approval_state="pending",
        result_payload={
            "resume_status": resume_status or "pending",
            "stale_reason": stale_reason,
        },
    )


def _failed_task_run(
    *,
    task_def: TaskDefinition,
    task_run_id: str,
    agent_id: str,
    input_payload: dict[str, Any],
    requested_scope: str | None,
    requested_visibility: str | None,
    memory_target: str | None,
    reason_code: str,
    started_at: datetime | None,
    finished_at: datetime | None,
) -> TaskRun:
    return TaskRun(
        task_id=task_def.task_id,
        task_run_id=task_run_id,
        assigned_agent_id=agent_id,
        role=task_def.role,
        task_attempt=1,
        requested_scope=requested_scope,
        requested_visibility=requested_visibility,
        memory_target=memory_target,
        input_payload=input_payload,
        status=TaskStatus.FAILED,
        attempt_count=1,
        approval_state="none",
        reason_code=reason_code,
        started_at=started_at,
        finished_at=finished_at,
    )
