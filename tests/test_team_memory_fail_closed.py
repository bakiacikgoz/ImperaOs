from __future__ import annotations

from pathlib import Path

from imperaos.governance.runtime import GovernanceRuntime
from imperaos.runtime.config import RuntimeConfig
from imperaos.schemas.models import OrchestratorResult
from imperaos.team.models import TeamSpec
from imperaos.team.supervisor import TeamSupervisor

DENY_MEMORY_POLICY = """
policy_schema_version = "1.0"
policy_version = "team-deny-memory"
web_egress = "deny"

[[task_rules]]
id = "task-chat-allow"
task_types = ["chat", "plan", "research", "code", "mixed"]
action = "allow"

[[tool_rules]]
id = "tool-python"
command_roots = ["python", "uv", "pytest", "ruff", "rg"]
action = "allow"
arg_deny_regex = []

[[memory_scope_rules]]
id = "deny-case"
scopes = ["case"]
producer_roles = []
visibilities = ["team"]
action = "deny"

[[handoff_rules]]
id = "allow-all"
from_roles = []
to_roles = []
action = "allow"

[pii_rules]
patterns = []
"""


class FakeTeamOrchestrator:
    def __init__(self, runtime: GovernanceRuntime):
        self.governance_runtime = runtime
        self._memory_manager = None

    def process(
        self,
        user_input: str,
        session_context: dict[str, str] | None = None,
        use_router: bool = True,
    ) -> OrchestratorResult:
        del user_input, session_context, use_router
        return OrchestratorResult(
            final_text="ok",
            used_path="llm_only",
            fallback_events=[],
            trace_id="trace-1",
            metrics={"router_reason_code": "RULE_ROUTE"},
        )


class RecordingMemoryManager:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []
        self.read_calls: list[dict[str, str]] = []

    def maybe_write_scoped(self, **kwargs):
        self.calls.append(
            {
                "scope": str(kwargs["scope"]),
                "visibility": str(kwargs["visibility"]),
                "producer_role": str(kwargs["producer_role"]),
            }
        )

        class Result:
            written = True
            reason = "ok"
            record_id = 1
            salience_score = 0.9

        return Result()

    def context_snippets_scoped(self, query: str, **kwargs):
        self.read_calls.append(
            {
                "query": query,
                "scope": str(kwargs["scope"]),
                "visibility": str(kwargs["visibility"]),
            }
        )
        return [f"memory-hit::{query}"]


def test_team_runtime_blocks_on_memory_scope_deny(tmp_path: Path) -> None:
    policy_path = tmp_path / "policy.toml"
    policy_path.write_text(DENY_MEMORY_POLICY, encoding="utf-8")

    cfg = RuntimeConfig.from_profile("default")
    cfg = cfg.model_copy(
        update={
            "governance": cfg.governance.model_copy(
                update={
                    "policy_path": str(policy_path),
                    "approval_store_path": str(tmp_path / "approvals.sqlite3"),
                    "audit_dir": str(tmp_path / "audit"),
                }
            ),
            "team": cfg.team.model_copy(
                update={
                    "artifact_dir": str(tmp_path / "team_jobs"),
                    "checkpoint_db_path": str(tmp_path / "checkpoints.sqlite3"),
                }
            ),
        }
    )
    runtime = GovernanceRuntime(config=cfg)
    orchestrator = FakeTeamOrchestrator(runtime)
    supervisor = TeamSupervisor(orchestrator=orchestrator, config=cfg)

    spec = TeamSpec.model_validate(
        {
            "version": "1",
            "team": {
                "team_id": "team-deny",
                "agents": [
                    {
                        "agent_id": "agent-intake",
                        "role": "Intake Agent",
                        "allowed_task_types": ["chat", "plan"],
                        "profile_name": "balanced",
                        "model_overrides": {},
                        "memory_scope_access": ["case"],
                        "tool_policy_profile": "default",
                        "approval_mode": "auto",
                    }
                ],
                "supervisor_policy": "sequential_then_parallel",
                "handoff_rules": [],
                "termination_rules": {
                    "max_tasks": 8,
                    "max_retries": 1,
                    "max_handoff_depth": 8,
                },
            },
            "tasks": [
                {
                    "task_id": "task-1",
                    "title": "only",
                    "task_type": "chat",
                    "role": "Intake Agent",
                    "depends_on": [],
                    "input_template": "{{request}}",
                }
            ],
        }
    )

    result = supervisor.run(spec=spec, request="hello", case_id="case-1", job_id="job-1")

    assert result.job.status.value == "blocked"
    assert any(task.reason_code == "MEMORY_SCOPE_DENY" for task in result.tasks)


def test_team_runtime_uses_declared_session_memory_scope(tmp_path: Path) -> None:
    cfg = RuntimeConfig.from_profile("default")
    cfg = cfg.model_copy(
        update={
            "governance": cfg.governance.model_copy(
                update={
                    "approval_store_path": str(tmp_path / "approvals.sqlite3"),
                    "audit_dir": str(tmp_path / "audit"),
                }
            ),
            "team": cfg.team.model_copy(
                update={
                    "artifact_dir": str(tmp_path / "team_jobs"),
                    "checkpoint_db_path": str(tmp_path / "checkpoints.sqlite3"),
                }
            ),
        }
    )
    runtime = GovernanceRuntime(config=cfg)
    orchestrator = FakeTeamOrchestrator(runtime)
    orchestrator._memory_manager = RecordingMemoryManager()
    supervisor = TeamSupervisor(orchestrator=orchestrator, config=cfg)

    spec = TeamSpec.model_validate(
        {
            "version": "1",
            "team": {
                "team_id": "team-session",
                "agents": [
                    {
                        "agent_id": "agent-review",
                        "role": "Reviewer/QA Agent",
                        "allowed_task_types": ["chat"],
                        "profile_name": "balanced",
                        "model_overrides": {},
                        "memory_scope_access": ["session"],
                        "tool_policy_profile": "default",
                        "approval_mode": "auto",
                    }
                ],
                "supervisor_policy": "sequential_then_parallel",
                "handoff_rules": [],
                "termination_rules": {
                    "max_tasks": 8,
                    "max_retries": 1,
                    "max_handoff_depth": 8,
                },
            },
            "tasks": [
                {
                    "task_id": "task-1",
                    "title": "review",
                    "task_type": "chat",
                    "role": "Reviewer/QA Agent",
                    "depends_on": [],
                    "input_template": "{{request}}",
                }
            ],
        }
    )

    result = supervisor.run(spec=spec, request="hello", case_id="case-1", job_id="job-2")

    assert result.job.status.value == "completed"
    assert result.tasks[0].requested_scope == "session"
    assert result.tasks[0].requested_visibility == "private"
    assert orchestrator._memory_manager.calls == [
        {
            "scope": "session",
            "visibility": "private",
            "producer_role": "Reviewer/QA Agent",
        }
    ]


def test_team_runtime_emits_memory_read_events_for_dependent_tasks(tmp_path: Path) -> None:
    cfg = RuntimeConfig.from_profile("default")
    cfg = cfg.model_copy(
        update={
            "governance": cfg.governance.model_copy(
                update={
                    "approval_store_path": str(tmp_path / "approvals.sqlite3"),
                    "audit_dir": str(tmp_path / "audit"),
                }
            ),
            "team": cfg.team.model_copy(
                update={
                    "artifact_dir": str(tmp_path / "team_jobs"),
                    "checkpoint_db_path": str(tmp_path / "checkpoints.sqlite3"),
                }
            ),
        }
    )
    runtime = GovernanceRuntime(config=cfg)
    orchestrator = FakeTeamOrchestrator(runtime)
    orchestrator._memory_manager = RecordingMemoryManager()
    supervisor = TeamSupervisor(orchestrator=orchestrator, config=cfg)

    spec = TeamSpec.model_validate(
        {
            "version": "1",
            "team": {
                "team_id": "team-memory-read",
                "agents": [
                    {
                        "agent_id": "agent-intake",
                        "role": "Intake Agent",
                        "allowed_task_types": ["plan"],
                        "profile_name": "balanced",
                        "model_overrides": {},
                        "memory_scope_access": ["case"],
                        "tool_policy_profile": "default",
                        "approval_mode": "auto",
                    },
                    {
                        "agent_id": "agent-review",
                        "role": "Reviewer/QA Agent",
                        "allowed_task_types": ["chat"],
                        "profile_name": "balanced",
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
                        "to_role": "Reviewer/QA Agent",
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
                    "task_id": "task-1",
                    "title": "intake",
                    "task_type": "plan",
                    "role": "Intake Agent",
                    "depends_on": [],
                    "input_template": "{{request}}",
                },
                {
                    "task_id": "task-2",
                    "title": "review",
                    "task_type": "chat",
                    "role": "Reviewer/QA Agent",
                    "depends_on": ["task-1"],
                    "input_template": "Review intake output.",
                },
            ],
        }
    )

    result = supervisor.run(spec=spec, request="hello", case_id="case-1", job_id="job-read")

    assert result.job.status.value == "completed"
    assert any(event.event == "memory_read_attempt" for event in result.events)
    assert any(event.event == "memory_read_succeeded" for event in result.events)
    assert orchestrator._memory_manager.read_calls == [
        {
            "query": "ok",
            "scope": "case",
            "visibility": "team",
        }
    ]
