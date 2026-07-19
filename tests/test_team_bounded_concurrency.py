from __future__ import annotations

from pathlib import Path

from imperaos.governance.runtime import GovernanceRuntime
from imperaos.memory.manager import MemoryManager
from imperaos.memory.persistent_store import PersistentMemoryStore
from imperaos.memory.salience_gate import SalienceGate
from imperaos.runtime.config import RuntimeConfig
from imperaos.schemas.models import OrchestratorResult
from imperaos.team.execution_contract import build_execution_contract_hash, build_resume_token_ref
from imperaos.team.models import TeamSpec
from imperaos.team.supervisor import TeamSupervisor


class ApprovalAwareConcurrencyOrchestrator:
    def __init__(self, runtime: GovernanceRuntime, memory_manager: MemoryManager):
        self.governance_runtime = runtime
        self._memory_manager = memory_manager
        self._counter = 0

    def process(
        self,
        user_input: str,
        session_context: dict[str, str] | None = None,
        use_router: bool = True,
    ) -> OrchestratorResult:
        del use_router
        session_context = session_context or {}
        run_id = str(
            session_context.get("governance_run_id")
            or session_context.get("job_id")
            or "job-test"
        )
        task_type = str(session_context.get("task_type") or "chat")
        override_id = session_context.get("governance_approval_id")
        decision, ticket = self.governance_runtime.evaluate_task(
            run_id=run_id,
            task_type=task_type,
            user_input=user_input,
            override_approval_id=override_id,
            execution_contract_hash=session_context.get("governance_execution_contract_hash"),
            resume_token_ref=session_context.get("governance_resume_token_ref"),
        )
        self._counter += 1
        if decision.action.value == "require_approval":
            return OrchestratorResult(
                final_text="approval-required",
                used_path="governance_pending",
                fallback_events=["approval_pending"],
                trace_id=f"trace-{self._counter}",
                metrics={
                    "governance_reason_code": decision.reason_code,
                    "approval_id": ticket.approval_id if ticket else None,
                },
            )
        if decision.action.value == "deny":
            return OrchestratorResult(
                final_text="blocked",
                used_path="governance_blocked",
                fallback_events=["governance_blocked"],
                trace_id=f"trace-{self._counter}",
                metrics={"governance_reason_code": decision.reason_code},
            )
        return OrchestratorResult(
            final_text=f"ok::{task_type}::{self._counter}::{user_input[:48]}",
            used_path="llm_only",
            fallback_events=[],
            trace_id=f"trace-{self._counter}",
            metrics={"router_reason_code": "RULE_ROUTE"},
        )


class RoutedResearchOrchestrator(ApprovalAwareConcurrencyOrchestrator):
    def process(
        self,
        user_input: str,
        session_context: dict[str, str] | None = None,
        use_router: bool = True,
    ) -> OrchestratorResult:
        del use_router
        session_context = session_context or {}
        run_id = str(
            session_context.get("governance_run_id")
            or session_context.get("job_id")
            or "job-test"
        )
        override_id = session_context.get("governance_approval_id")
        decision, ticket = self.governance_runtime.evaluate_task(
            run_id=run_id,
            task_type="research",
            user_input=user_input,
            override_approval_id=override_id,
            execution_contract_hash=session_context.get("governance_execution_contract_hash"),
            resume_token_ref=session_context.get("governance_resume_token_ref"),
        )
        self._counter += 1
        if decision.action.value == "require_approval":
            return OrchestratorResult(
                final_text="approval-required",
                used_path="governance_pending",
                fallback_events=["approval_pending"],
                trace_id=f"trace-{self._counter}",
                metrics={
                    "governance_reason_code": decision.reason_code,
                    "governance_target": decision.target,
                    "approval_id": ticket.approval_id if ticket else None,
                },
            )
        if decision.action.value == "deny":
            return OrchestratorResult(
                final_text="blocked",
                used_path="governance_blocked",
                fallback_events=["governance_blocked"],
                trace_id=f"trace-{self._counter}",
                metrics={
                    "governance_reason_code": decision.reason_code,
                    "governance_target": decision.target,
                },
            )
        return OrchestratorResult(
            final_text=f"ok::research::{self._counter}::{user_input[:48]}",
            used_path="llm_only",
            fallback_events=[],
            trace_id=f"trace-{self._counter}",
            metrics={"router_reason_code": "RULE_ROUTE", "governance_target": "research"},
        )


def _policy(path: Path) -> None:
    path.write_text(
        """
policy_schema_version = "1.0"
policy_version = "bounded-concurrency"
web_egress = "deny"

[[task_rules]]
id = "task-plan-allow"
task_types = ["plan", "chat"]
action = "allow"

[[task_rules]]
id = "task-research-approval"
task_types = ["research"]
action = "require_approval"

[[tool_rules]]
id = "tool-maintenance"
command_roots = ["python", "uv", "pytest", "ruff", "rg"]
action = "allow"
arg_deny_regex = []

[[handoff_rules]]
id = "handoff-allow"
from_roles = []
to_roles = []
action = "allow"

[[memory_scope_rules]]
id = "memory-allow"
scopes = ["session", "case"]
producer_roles = []
visibilities = ["private", "team"]
action = "allow"

[pii_rules]
patterns = []
""",
        encoding="utf-8",
    )


def _memory_manager(tmp_path: Path) -> MemoryManager:
    return MemoryManager(
        enabled=True,
        store=PersistentMemoryStore(db_path=tmp_path / "memory.sqlite3"),
        gate=SalienceGate(
            threshold=0.0,
            decay=1.0,
            task_bonus=0.0,
            expert_bonus=0.0,
            spike_reduction=0.0,
            keyword_weights={},
        ),
        max_rows=5000,
        ttl_days=30,
    )


def _config(tmp_path: Path, policy_path: Path) -> RuntimeConfig:
    cfg = RuntimeConfig.from_profile("default")
    return cfg.model_copy(
        update={
            "governance": cfg.governance.model_copy(
                update={
                    "policy_path": str(policy_path),
                    "approval_store_path": str(tmp_path / "approvals.sqlite3"),
                    "audit_dir": str(tmp_path / "audit"),
                }
            ),
            "memory": cfg.memory.model_copy(update={"db_path": str(tmp_path / "memory.sqlite3")}),
            "team": cfg.team.model_copy(
                update={
                    "artifact_dir": str(tmp_path / "team_jobs"),
                    "checkpoint_db_path": str(tmp_path / "checkpoints.sqlite3"),
                    "max_parallel_tasks": 2,
                }
            ),
        }
    )


def _spec() -> TeamSpec:
    return TeamSpec.model_validate(
        {
            "version": "1",
            "team": {
                "team_id": "team-bounded",
                "agents": [
                    {
                        "agent_id": "agent-intake",
                        "role": "Intake Agent",
                        "allowed_task_types": ["plan"],
                        "profile_name": "default",
                        "model_overrides": {},
                        "memory_scope_access": ["case"],
                        "tool_policy_profile": "default",
                        "approval_mode": "auto",
                    },
                    {
                        "agent_id": "agent-research",
                        "role": "Research Analyst Agent",
                        "allowed_task_types": ["research"],
                        "profile_name": "default",
                        "model_overrides": {},
                        "memory_scope_access": ["case"],
                        "tool_policy_profile": "default",
                        "approval_mode": "auto",
                    },
                ],
                "supervisor_policy": "sequential_then_parallel",
                "handoff_rules": [
                    {
                        "from_role": "Intake Agent",
                        "to_role": "Research Analyst Agent",
                        "required": True,
                    }
                ],
                "termination_rules": {
                    "max_tasks": 8,
                    "max_retries": 1,
                    "max_handoff_depth": 8,
                },
            },
            "tasks": [
                {
                    "task_id": "task-intake",
                    "title": "intake",
                    "task_type": "plan",
                    "role": "Intake Agent",
                    "depends_on": [],
                    "input_template": "{{request}}",
                },
                {
                    "task_id": "task-research",
                    "title": "research",
                    "task_type": "research",
                    "role": "Research Analyst Agent",
                    "depends_on": ["task-intake"],
                    "input_template": "Produce research notes.",
                },
            ],
        }
    )


def _routed_spec() -> TeamSpec:
    return TeamSpec.model_validate(
        {
            "version": "1",
            "team": {
                "team_id": "team-routed",
                "agents": [
                    {
                        "agent_id": "agent-intake",
                        "role": "Intake Agent",
                        "allowed_task_types": ["plan"],
                        "profile_name": "default",
                        "model_overrides": {},
                        "memory_scope_access": ["case"],
                        "tool_policy_profile": "default",
                        "approval_mode": "auto",
                    }
                ],
                "supervisor_policy": "sequential_then_parallel",
                "handoff_rules": [],
                "termination_rules": {
                    "max_tasks": 4,
                    "max_retries": 1,
                    "max_handoff_depth": 4,
                },
            },
            "tasks": [
                {
                    "task_id": "task-intake",
                    "title": "intake",
                    "task_type": "plan",
                    "role": "Intake Agent",
                    "depends_on": [],
                    "input_template": "{{request}}",
                }
            ],
        }
    )


def test_shared_memory_target_conflict_rejects_second_write(tmp_path: Path) -> None:
    manager = _memory_manager(tmp_path)
    first = manager.maybe_write_scoped(
        session_id="job-1",
        task_type="plan",
        user_input="a",
        assistant_output="one",
        scope="case",
        team_id="team-1",
        case_id="case-1",
        job_id="job-1",
        producer_agent_id="agent-a",
        producer_role="Intake Agent",
        visibility="team",
        memory_target="shared/summary",
        expected_state_version=0,
    )
    second = manager.maybe_write_scoped(
        session_id="job-1",
        task_type="plan",
        user_input="b",
        assistant_output="two",
        scope="case",
        team_id="team-1",
        case_id="case-1",
        job_id="job-1",
        producer_agent_id="agent-b",
        producer_role="Policy/Compliance Agent",
        visibility="team",
        memory_target="shared/summary",
        expected_state_version=0,
    )

    assert first.written is True
    assert first.committed_state_version == 1
    assert second.written is False
    assert second.conflict_detected is True
    assert second.reason == "memory_conflict"
    assert second.committed_state_version == 1


def test_duplicate_resume_claim_is_suppressed(tmp_path: Path) -> None:
    policy_path = tmp_path / "policy.toml"
    _policy(policy_path)
    runtime = GovernanceRuntime(config=_config(tmp_path, policy_path))
    decision, ticket = runtime.evaluate_task(
        run_id="job-source",
        task_type="research",
        user_input="need approval",
    )
    assert decision.action.value == "require_approval"
    assert ticket is not None

    contract = {
        "task_run_id": "job-source:task-research:attempt-1",
        "task_attempt": 1,
        "target_kind": "task",
        "target_ref": "research",
        "canonical_task_input": "need approval",
        "resolved_memory_refs": [],
        "resolved_memory_fingerprint": None,
        "action_payload_hash": runtime.task_action_hash(
            task_type="research", user_input="need approval"
        ),
        "policy_input_hash": "policy-input",
        "causal_ancestry": [],
        "branch_id": "branch:task-research",
        "branch_parent": None,
    }
    predicted_snapshot_hash = runtime._hash_payload(
        {**ticket.snapshot, "execution_contract": contract}
    )  # noqa: SLF001
    resume_token_ref = build_resume_token_ref(
        source_job_id="job-source",
        task_run_id=contract["task_run_id"],
        approval_id=ticket.approval_id,
        snapshot_hash=predicted_snapshot_hash,
        target_kind="task",
    )
    execution_contract_hash = build_execution_contract_hash(
        resume_token_ref=resume_token_ref,
        action_hash=contract["action_payload_hash"],
        policy_hash=runtime.policy_hash,
        contract=contract,
    )
    attach = runtime.attach_execution_contract(
        approval_id=ticket.approval_id,
        execution_contract=contract,
        execution_contract_hash=execution_contract_hash,
    )
    assert attach.error_code is None
    assert (
        runtime.decide_approval(
            approval_id=ticket.approval_id, approve=True, actor="ops", reason="ok"
        ).error_code
        is None
    )
    assert runtime.execute_approval(approval_id=ticket.approval_id).error_code is None

    claimed = runtime.prepare_resume_approval(
        approval_id=ticket.approval_id,
        run_id="job-resume-a",
        task_run_id="job-resume-a:task-research:attempt-1",
        target_kind="task",
        execution_contract_hash=execution_contract_hash,
    )
    duplicate = runtime.prepare_resume_approval(
        approval_id=ticket.approval_id,
        run_id="job-resume-b",
        task_run_id="job-resume-b:task-research:attempt-1",
        target_kind="task",
        execution_contract_hash=execution_contract_hash,
    )

    assert claimed.error_code is None
    assert duplicate.error_code == "RESUME_DUPLICATE_SUPPRESSED"


def test_attach_execution_contract_self_heals_hash_from_snapshot(tmp_path: Path) -> None:
    policy_path = tmp_path / "policy.toml"
    _policy(policy_path)
    runtime = GovernanceRuntime(config=_config(tmp_path, policy_path))
    decision, ticket = runtime.evaluate_task(
        run_id="job-source",
        task_type="research",
        user_input="need approval",
    )
    assert decision.action.value == "require_approval"
    assert ticket is not None

    contract = {
        "task_run_id": "job-source:task-research:attempt-1",
        "task_attempt": 1,
        "target_kind": "task",
        "target_ref": "research",
        "canonical_task_input": "need approval",
        "resolved_memory_refs": [],
        "resolved_memory_fingerprint": None,
        "action_payload_hash": runtime.task_action_hash(
            task_type="research", user_input="need approval"
        ),
        "policy_input_hash": "policy-input",
        "causal_ancestry": [],
        "branch_id": "branch:task-research",
        "branch_parent": None,
    }
    predicted_snapshot_hash = runtime._hash_payload(  # noqa: SLF001
        {**ticket.snapshot, "execution_contract": contract}
    )
    resume_token_ref = build_resume_token_ref(
        source_job_id="job-source",
        task_run_id=contract["task_run_id"],
        approval_id=ticket.approval_id,
        snapshot_hash=predicted_snapshot_hash,
        target_kind="task",
    )
    canonical_contract_hash = build_execution_contract_hash(
        resume_token_ref=resume_token_ref,
        action_hash=contract["action_payload_hash"],
        policy_hash=runtime.policy_hash,
        contract=contract,
    )

    attach = runtime.attach_execution_contract(
        approval_id=ticket.approval_id,
        execution_contract=contract,
        execution_contract_hash="wrong-hash",
    )
    assert attach.error_code is None
    assert attach.ticket is not None
    assert attach.ticket.execution_contract_hash == canonical_contract_hash


def test_stale_snapshot_detected_when_memory_context_changes(tmp_path: Path) -> None:
    policy_path = tmp_path / "policy.toml"
    _policy(policy_path)
    cfg = _config(tmp_path, policy_path)
    runtime = GovernanceRuntime(config=cfg)
    memory_manager = _memory_manager(tmp_path)
    orchestrator = ApprovalAwareConcurrencyOrchestrator(runtime, memory_manager)
    supervisor = TeamSupervisor(orchestrator=orchestrator, config=cfg)
    spec = _spec()

    blocked = supervisor.run(
        spec=spec,
        request="bounded concurrency request",
        case_id="case-1",
        job_id="job-source",
    )
    approval_id = next(
        event.approval_id for event in blocked.events if event.event == "approval_requested"
    )
    assert (
        runtime.decide_approval(
            approval_id=approval_id, approve=True, actor="ops", reason="ok"
        ).error_code
        is None
    )
    assert runtime.execute_approval(approval_id=approval_id).error_code is None

    memory_manager.maybe_write_scoped(
        session_id="job-resume",
        task_type="plan",
        user_input="bounded concurrency request",
        assistant_output="ok::plan::seed::bounded concurrency request",
        scope="case",
        team_id=spec.team.team_id,
        case_id="case-1",
        job_id="job-resume",
        producer_agent_id="seed-agent",
        producer_role="Intake Agent",
        visibility="team",
    )

    resumed = supervisor.run(
        spec=spec,
        request="bounded concurrency request",
        case_id="case-1",
        job_id="job-resume",
        approval_overrides={"task-research": {"task": approval_id}},
    )

    research = next(task for task in resumed.tasks if task.task_id == "task-research")
    assert research.status.value == "escalated"
    assert research.reason_code == "STALE_APPROVAL_SNAPSHOT"
    assert any(event.event == "approval_stale" for event in resumed.events)


def test_live_routed_approval_resume_completes_without_false_stale(tmp_path: Path) -> None:
    policy_path = tmp_path / "policy.toml"
    _policy(policy_path)
    cfg = _config(tmp_path, policy_path)
    runtime = GovernanceRuntime(config=cfg)
    supervisor = TeamSupervisor(
        orchestrator=RoutedResearchOrchestrator(runtime, _memory_manager(tmp_path)),
        config=cfg,
    )
    spec = _routed_spec()

    blocked = supervisor.run(
        spec=spec,
        request="route this through research",
        case_id="case-routed",
        job_id="job-routed-blocked",
    )
    approval_id = next(
        event.approval_id for event in blocked.events if event.event == "approval_requested"
    )
    assert blocked.job.status.value == "blocked"
    assert approval_id is not None
    assert (
        runtime.decide_approval(
            approval_id=approval_id,
            approve=True,
            actor="ops",
            reason="ok",
        ).error_code
        is None
    )
    assert runtime.execute_approval(approval_id=approval_id).error_code is None

    resumed = supervisor.run(
        spec=spec,
        request="route this through research",
        case_id="case-routed",
        job_id="job-routed-resume",
        approval_overrides={"task-intake": {"task": approval_id}},
    )

    assert resumed.job.status.value == "completed"
    assert any(event.event == "approval_consumed" for event in resumed.events)
    assert not any(event.event == "approval_stale" for event in resumed.events)
