from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from imperaos.cli import app
from imperaos.governance.runtime import GovernanceRuntime
from imperaos.runtime.config import RuntimeConfig
from imperaos.runtime.platform import current_platform
from imperaos.schemas.models import OrchestratorResult

runner = CliRunner()


class FakeTeamOrchestrator:
    governance_runtime = None
    _memory_manager = None

    def process(
        self,
        user_input: str,
        session_context: dict[str, str] | None = None,
        use_router: bool = True,
    ) -> OrchestratorResult:
        del user_input, session_context, use_router
        return OrchestratorResult(
            final_text="team-ok",
            used_path="llm_only",
            fallback_events=[],
            trace_id="trace-team",
            metrics={"router_reason_code": "RULE_ROUTE"},
        )


class ApprovalAwareFakeTeamOrchestrator:
    def __init__(self, runtime: GovernanceRuntime):
        self.governance_runtime = runtime
        self._memory_manager = None
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
        override_id = session_context.get("governance_approval_id")
        decision, ticket = self.governance_runtime.evaluate_task(
            run_id=run_id,
            task_type="chat",
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
            final_text="team-ok-after-resume",
            used_path="llm_only",
            fallback_events=[],
            trace_id=f"trace-{self._counter}",
            metrics={"router_reason_code": "RULE_ROUTE"},
        )


def _write_spec(path: Path) -> None:
    payload = {
        "version": "1",
        "team": {
            "team_id": "team-test",
            "supervisor_policy": "sequential_then_parallel",
            "agents": [
                {
                    "agent_id": "agent-intake",
                    "role": "Intake Agent",
                    "allowed_task_types": ["chat", "plan"],
                    "profile_name": "balanced",
                    "model_overrides": {},
                    "memory_scope_access": ["session", "case"],
                    "tool_policy_profile": "default",
                    "approval_mode": "auto",
                }
            ],
            "handoff_rules": [],
            "termination_rules": {
                "max_tasks": 8,
                "max_retries": 1,
                "max_handoff_depth": 8,
            },
        },
        "tasks": [],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _write_task_approval_policy(path: Path) -> None:
    payload = """
policy_schema_version = "1.0"
policy_version = "team-task-approval"
web_egress = "deny"

[[task_rules]]
id = "task-chat-approval"
task_types = ["chat"]
action = "require_approval"

[[tool_rules]]
id = "tool-python"
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
scopes = ["session", "team", "case"]
producer_roles = []
visibilities = ["private", "team", "case"]
action = "allow"

[pii_rules]
patterns = []
"""
    path.write_text(payload, encoding="utf-8")


def test_team_validate_and_run(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    spec_path = tmp_path / "team.json"
    _write_spec(spec_path)

    monkeypatch.setattr(
        "imperaos.cli._build_orchestrator",
        lambda *a, **k: FakeTeamOrchestrator(),
    )

    validate = runner.invoke(app, ["team", "validate", "--spec", str(spec_path), "--json"])
    assert validate.exit_code == 0
    assert '"status": "ok"' in validate.stdout

    run = runner.invoke(
        app,
        [
            "team",
            "run",
            "--spec",
            str(spec_path),
            "--once",
            "short request",
            "--json",
        ],
    )
    assert run.exit_code == 0
    payload = json.loads(run.stdout)
    assert payload["job"]["status"] == "completed"
    checkpoint_db = tmp_path / ".imperaos" / "team" / "checkpoints.sqlite3"
    assert checkpoint_db.exists()
    with sqlite3.connect(checkpoint_db) as conn:
        row = conn.execute(
            "SELECT status FROM team_checkpoints WHERE job_id = ?",
            (payload["job"]["job_id"],),
        ).fetchone()
    assert row is not None
    assert row[0] == "completed"

    status = runner.invoke(app, ["team", "status", "--job-id", payload["job"]["job_id"], "--json"])
    assert status.exit_code == 0
    status_payload = json.loads(status.stdout)
    assert status_payload["job"]["team_id"] == "team-test"

    replay = runner.invoke(app, ["team", "replay", "--job-id", payload["job"]["job_id"]])
    assert replay.exit_code == 0
    replay_payload = json.loads(replay.stdout)
    assert replay_payload["event_count"] >= 1


def test_team_init_produces_valid_yaml(tmp_path: Path) -> None:
    output = tmp_path / "team.yaml"
    init = runner.invoke(app, ["team", "init", "--output", str(output)])
    assert init.exit_code == 0
    validate = runner.invoke(app, ["team", "validate", "--spec", str(output), "--json"])
    assert validate.exit_code == 0


def test_team_init_regulated_template_produces_valid_yaml(tmp_path: Path) -> None:
    output = tmp_path / "team-regulated.yaml"
    init = runner.invoke(
        app,
        ["team", "init", "--output", str(output), "--template", "regulated"],
    )
    assert init.exit_code == 0
    validate = runner.invoke(app, ["team", "validate", "--spec", str(output), "--json"])
    assert validate.exit_code == 0


def test_team_resume_replays_approved_task_gate(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    spec_path = tmp_path / "team.json"
    policy_path = tmp_path / "policy.toml"
    _write_spec(spec_path)
    _write_task_approval_policy(policy_path)

    cfg = RuntimeConfig.from_profile("default").model_copy(
        update={
            "governance": RuntimeConfig.from_profile("default").governance.model_copy(
                update={
                    "policy_path": str(policy_path),
                    "approval_store_path": str(tmp_path / "approvals.sqlite3"),
                    "audit_dir": str(tmp_path / "audit"),
                }
            ),
            "team": RuntimeConfig.from_profile("default").team.model_copy(
                update={
                    "artifact_dir": str(tmp_path / "team_jobs"),
                    "checkpoint_db_path": str(tmp_path / "checkpoints.sqlite3"),
                }
            ),
        }
    )
    runtime = GovernanceRuntime(config=cfg)

    monkeypatch.setattr(
        "imperaos.cli.resolve_runtime_config",
        lambda *a, **k: (cfg, {}),
    )
    monkeypatch.setattr(
        "imperaos.cli._build_orchestrator",
        lambda *a, **k: ApprovalAwareFakeTeamOrchestrator(runtime),
    )

    first_run = runner.invoke(
        app,
        [
            "team",
            "run",
            "--spec",
            str(spec_path),
            "--once",
            "short request",
            "--json",
        ],
    )
    assert first_run.exit_code == 0
    first_payload = json.loads(first_run.stdout)
    assert first_payload["job"]["status"] == "blocked"

    approval_id = runtime.approval_store.list_pending(workspace_id="default")[0].approval_id
    approval = runtime.decide_approval(
        approval_id=approval_id,
        approve=True,
        actor="tester",
        reason="approved",
    )
    assert approval.error_code is None
    executed = runtime.execute_approval(approval_id=approval_id)
    assert executed.error_code is None

    resume = runner.invoke(
        app,
        [
            "team",
            "resume",
            "--spec",
            str(spec_path),
            "--job-id",
            first_payload["job"]["job_id"],
            "--root-dir",
            str(tmp_path / "team_jobs"),
            "--json",
        ],
    )
    assert resume.exit_code == 0
    resume_payload = json.loads(resume.stdout)
    assert resume_payload["job"]["status"] == "completed"
    assert any(item["target"] == "task" for item in resume_payload["resolved_approvals"])


def test_team_resume_rejects_approved_but_not_executed_ticket(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    spec_path = tmp_path / "team.json"
    policy_path = tmp_path / "policy.toml"
    _write_spec(spec_path)
    _write_task_approval_policy(policy_path)

    cfg = RuntimeConfig.from_profile("default").model_copy(
        update={
            "governance": RuntimeConfig.from_profile("default").governance.model_copy(
                update={
                    "policy_path": str(policy_path),
                    "approval_store_path": str(tmp_path / "approvals.sqlite3"),
                    "audit_dir": str(tmp_path / "audit"),
                }
            ),
            "team": RuntimeConfig.from_profile("default").team.model_copy(
                update={
                    "artifact_dir": str(tmp_path / "team_jobs"),
                    "checkpoint_db_path": str(tmp_path / "checkpoints.sqlite3"),
                }
            ),
        }
    )
    runtime = GovernanceRuntime(config=cfg)

    monkeypatch.setattr("imperaos.cli.resolve_runtime_config", lambda *a, **k: (cfg, {}))
    monkeypatch.setattr(
        "imperaos.cli._build_orchestrator",
        lambda *a, **k: ApprovalAwareFakeTeamOrchestrator(runtime),
    )

    first_run = runner.invoke(
        app,
        [
            "team",
            "run",
            "--spec",
            str(spec_path),
            "--once",
            "short request",
            "--json",
        ],
    )
    assert first_run.exit_code == 0
    first_payload = json.loads(first_run.stdout)

    approval_id = runtime.approval_store.list_pending(workspace_id="default")[0].approval_id
    approval = runtime.decide_approval(
        approval_id=approval_id,
        approve=True,
        actor="tester",
        reason="approved",
    )
    assert approval.error_code is None

    resume = runner.invoke(
        app,
        [
            "team",
            "resume",
            "--spec",
            str(spec_path),
            "--job-id",
            first_payload["job"]["job_id"],
            "--root-dir",
            str(tmp_path / "team_jobs"),
            "--json",
        ],
    )
    assert resume.exit_code == 1
    assert "no executed approvals found for resume" in resume.stdout


def test_team_list_returns_jobs_and_since_filter(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    root = tmp_path / ".imperaos" / "team" / "jobs"
    root.mkdir(parents=True, exist_ok=True)

    older = root / "job-old"
    older.mkdir(parents=True, exist_ok=True)
    (older / "status.json").write_text(
        json.dumps(
            {
                "job": {
                    "job_id": "job-old",
                    "case_id": "case-old",
                    "team_id": "team-test",
                    "request": "older",
                    "status": "completed",
                    "created_at": "2026-03-01T10:00:00Z",
                    "finished_at": "2026-03-01T10:05:00Z",
                },
                "audit_envelope_path": str(older / "audit_envelope.json"),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    recent = root / "job-new"
    recent.mkdir(parents=True, exist_ok=True)
    (recent / "status.json").write_text(
        json.dumps(
            {
                "job": {
                    "job_id": "job-new",
                    "case_id": "case-new",
                    "team_id": "team-test",
                    "request": "recent",
                    "status": "running",
                    "created_at": "2026-03-03T18:00:00Z",
                    "finished_at": None,
                },
                "audit_envelope_path": str(recent / "audit_envelope.json"),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    listed = runner.invoke(app, ["team", "list", "--root-dir", str(root), "--json"])
    assert listed.exit_code == 0
    listed_payload = json.loads(listed.stdout)
    assert listed_payload["contract_version"] == "3.0"
    assert listed_payload["count"] == 2
    assert [item["job_id"] for item in listed_payload["items"]] == ["job-new", "job-old"]

    filtered = runner.invoke(
        app,
        [
            "team",
            "list",
            "--root-dir",
            str(root),
            "--since",
            "2026-03-03T00:00:00Z",
            "--json",
        ],
    )
    assert filtered.exit_code == 0
    filtered_payload = json.loads(filtered.stdout)
    assert filtered_payload["count"] == 1
    assert filtered_payload["items"][0]["job_id"] == "job-new"


def test_team_replay_verify_reports_verified(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    spec_path = tmp_path / "team.json"
    _write_spec(spec_path)

    monkeypatch.setattr(
        "imperaos.cli._build_orchestrator",
        lambda *a, **k: FakeTeamOrchestrator(),
    )

    run = runner.invoke(
        app,
        [
            "team",
            "run",
            "--spec",
            str(spec_path),
            "--once",
            "short request",
            "--json",
        ],
    )
    assert run.exit_code == 0
    payload = json.loads(run.stdout)

    replay = runner.invoke(
        app,
        ["team", "replay", "--job-id", payload["job"]["job_id"], "--verify", "--json"],
    )
    assert replay.exit_code == 0
    replay_payload = json.loads(replay.stdout)
    assert replay_payload["contract_version"] == "3.0"
    assert replay_payload["verified"] is True
    assert replay_payload["checks"]["event_count"] >= 1
    assert isinstance(replay_payload["trace_refs"], list)


def test_team_validate_rejects_unknown_tool_policy_profile(tmp_path: Path) -> None:
    spec_path = tmp_path / "team.json"
    payload = {
        "version": "1",
        "team": {
            "team_id": "team-invalid",
            "supervisor_policy": "sequential_then_parallel",
            "agents": [
                {
                    "agent_id": "agent-intake",
                    "role": "Intake Agent",
                    "allowed_task_types": ["chat"],
                    "profile_name": "balanced",
                    "model_overrides": {},
                    "memory_scope_access": ["session"],
                    "tool_policy_profile": "missing-profile",
                    "approval_mode": "auto",
                }
            ],
            "handoff_rules": [],
            "termination_rules": {"max_tasks": 8, "max_retries": 1, "max_handoff_depth": 8},
        },
        "tasks": [],
    }
    spec_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    validate = runner.invoke(app, ["team", "validate", "--spec", str(spec_path), "--json"])
    assert validate.exit_code == 1
    result = json.loads(validate.stdout)
    assert result["status"] == "invalid"
    assert any("tool_policy_profile" in item for item in result["errors"])


def test_team_run_accepts_explicit_job_id(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    spec_path = tmp_path / "team.json"
    _write_spec(spec_path)

    monkeypatch.setattr(
        "imperaos.cli._build_orchestrator",
        lambda *a, **k: FakeTeamOrchestrator(),
    )

    run = runner.invoke(
        app,
        [
            "team",
            "run",
            "--spec",
            str(spec_path),
            "--once",
            "short request",
            "--job-id",
            "job-ui-custom",
            "--json",
        ],
    )
    assert run.exit_code == 0
    payload = json.loads(run.stdout)
    assert payload["job"]["job_id"] == "job-ui-custom"
    assert (tmp_path / ".imperaos" / "team" / "jobs" / "job-ui-custom" / "status.json").exists()


def test_operator_capabilities_exposes_workspace_parity_flags() -> None:
    result = runner.invoke(app, ["operator", "capabilities", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["contractVersion"] == "3.0"
    assert payload["features"]["operatorWorkflowParity"] is True
    assert payload["features"]["enterpriseOpsParity"] is True
    computer_use = payload["features"]["computerUsePilot"]
    if current_platform().label == "windows":
        assert computer_use["enabled"] is False
        assert computer_use["reasonCode"] == "WINDOWS_COMPUTER_USE_NOT_QUALIFIED"
        assert computer_use["adapterStatus"] == "windows_scaffold"
    else:
        assert computer_use["scope"] == "browser+desktop+file"
        assert computer_use["adapterStatus"] == "safari_applescript"
    assert payload["commands"]["teamSubmit"] is True
    assert payload["commands"]["teamResumeSubmit"] is True
    assert payload["commands"]["computerUseSubmit"] is True
    assert payload["commands"]["computerUsePause"] is True
    assert payload["commands"]["computerUseResume"] is True
    assert payload["commands"]["computerUseStop"] is True
    assert "balanced" in payload["profiles"]
