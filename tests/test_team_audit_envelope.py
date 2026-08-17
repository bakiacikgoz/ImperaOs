from __future__ import annotations

import json
from pathlib import Path

from imperaos.governance.runtime import GovernanceRuntime
from imperaos.runtime.config import RuntimeConfig
from imperaos.schemas.models import OrchestratorResult
from imperaos.team.models import TeamSpec
from imperaos.team.replay import replay_job
from imperaos.team.supervisor import TeamSupervisor


class _EnvelopeOrchestrator:
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
            trace_id="trace-envelope",
            metrics={"router_reason_code": "RULE_ROUTE"},
        )


def test_team_audit_envelope_contains_policy_and_runtime_hashes(tmp_path: Path) -> None:
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
    supervisor = TeamSupervisor(orchestrator=_EnvelopeOrchestrator(runtime), config=cfg)

    spec = TeamSpec.model_validate(
        {
            "version": "1",
            "team": {
                "team_id": "team-envelope",
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
                "supervisor_policy": "sequential_then_parallel",
                "handoff_rules": [],
                "termination_rules": {
                    "max_tasks": 8,
                    "max_retries": 1,
                    "max_handoff_depth": 8,
                },
            },
            "tasks": [],
        }
    )

    result = supervisor.run(spec=spec, request="hello", case_id="case-1", job_id="job-1")
    assert result.audit_envelope_path is not None
    envelope_path = Path(result.audit_envelope_path)
    envelope = json.loads(envelope_path.read_text(encoding="utf-8"))

    assert envelope["policy_bundle_id"]
    assert len(envelope["policy_bundle_hash"]) == 64
    assert len(envelope["runtime_config_hash"]) == 64
    assert len(envelope["integrity"]["hash"]) == 64
    assert envelope["event_schema_version"] == "3"
    assert envelope["consistency"]["verified"] is True
    assert envelope["event_count"] >= 1
    assert envelope["trace_refs"] == ["trace-envelope"]


def test_team_audit_envelope_signature_when_key_configured(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("IMPERAOS_AUDIT_SIGNING_KEY", "test-signing-key")
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
    supervisor = TeamSupervisor(orchestrator=_EnvelopeOrchestrator(runtime), config=cfg)

    spec = TeamSpec.model_validate(
        {
            "version": "1",
            "team": {
                "team_id": "team-envelope",
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
                "supervisor_policy": "sequential_then_parallel",
                "handoff_rules": [],
                "termination_rules": {
                    "max_tasks": 8,
                    "max_retries": 1,
                    "max_handoff_depth": 8,
                },
            },
            "tasks": [],
        }
    )

    result = supervisor.run(spec=spec, request="hello", case_id="case-1", job_id="job-sign")
    assert result.audit_envelope_path is not None
    envelope = json.loads(Path(result.audit_envelope_path).read_text(encoding="utf-8"))

    signature = envelope["integrity"]["signature"]
    assert isinstance(signature, str)
    assert len(signature) == 64


def test_team_replay_verify_detects_tampered_event_sequence(tmp_path: Path) -> None:
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
    supervisor = TeamSupervisor(orchestrator=_EnvelopeOrchestrator(runtime), config=cfg)

    spec = TeamSpec.model_validate(
        {
            "version": "1",
            "team": {
                "team_id": "team-envelope",
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
                "supervisor_policy": "sequential_then_parallel",
                "handoff_rules": [],
                "termination_rules": {
                    "max_tasks": 8,
                    "max_retries": 1,
                    "max_handoff_depth": 8,
                },
            },
            "tasks": [],
        }
    )

    result = supervisor.run(spec=spec, request="hello", case_id="case-1", job_id="job-tamper")
    events_path = Path(cfg.team.artifact_dir) / "job-tamper" / "events.jsonl"
    lines = events_path.read_text(encoding="utf-8").splitlines()
    tampered = json.loads(lines[0])
    tampered["event_seq"] = 99
    lines[0] = json.dumps(tampered, ensure_ascii=False)
    events_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    replay = replay_job(result.job.job_id, root_dir=cfg.team.artifact_dir, verify=True)
    assert replay["verified"] is False
    assert any("event_seq mismatch" in item for item in replay["errors"])


def test_team_replay_verify_detects_missing_causal_ref(tmp_path: Path) -> None:
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
    supervisor = TeamSupervisor(orchestrator=_EnvelopeOrchestrator(runtime), config=cfg)

    spec = TeamSpec.model_validate(
        {
            "version": "1",
            "team": {
                "team_id": "team-envelope",
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
                "supervisor_policy": "sequential_then_parallel",
                "handoff_rules": [],
                "termination_rules": {
                    "max_tasks": 8,
                    "max_retries": 1,
                    "max_handoff_depth": 8,
                },
            },
            "tasks": [],
        }
    )

    result = supervisor.run(spec=spec, request="hello", case_id="case-1", job_id="job-causal")
    events_path = Path(cfg.team.artifact_dir) / "job-causal" / "events.jsonl"
    lines = events_path.read_text(encoding="utf-8").splitlines()
    tampered_index = next(
        idx
        for idx, line in enumerate(lines)
        if json.loads(line).get("event") in {"task_assigned", "task_started", "task_completed"}
    )
    tampered = json.loads(lines[tampered_index])
    tampered["causal_ref"] = None
    lines[tampered_index] = json.dumps(tampered, ensure_ascii=False)
    events_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    replay = replay_job(result.job.job_id, root_dir=cfg.team.artifact_dir, verify=True)
    assert replay["verified"] is False
    assert any("missing causal_ref" in item for item in replay["errors"])
