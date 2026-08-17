from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from imperaos.enterprise.signing import write_signed_json
from imperaos.governance.runtime import build_governance_runtime
from imperaos.memory.manager import MemoryManager
from imperaos.memory.persistent_store import PersistentMemoryStore
from imperaos.memory.salience_gate import SalienceGate
from imperaos.runtime.config import RuntimeConfig
from imperaos.schemas.models import OrchestratorResult
from imperaos.team.continuation import (
    ResumeContinuationError,
    derive_resume_continuation_state,
)
from imperaos.team.memory_scope import validate_memory_access
from imperaos.team.models import TeamSpec
from imperaos.team.replay import load_events, replay_job
from imperaos.team.supervisor import TeamSupervisor
from imperaos.team.validation import validate_team_spec


class PilotGateFailure(RuntimeError):
    def __init__(self, error_code: str, message: str):
        super().__init__(message)
        self.error_code = error_code
        self.message = message


class DeterministicPilotOrchestrator:
    def __init__(self, config: RuntimeConfig):
        self.governance_runtime = build_governance_runtime(config)
        self._memory_manager = _build_memory_manager(config)

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
            or "pilot-job"
        )
        task_type = str(session_context.get("task_type") or "chat")
        override_id = session_context.get("governance_approval_id")
        trace_seed = _short_hash({"task_type": task_type, "input": user_input})

        if self.governance_runtime is not None:
            decision, ticket = self.governance_runtime.evaluate_task(
                run_id=run_id,
                task_type=task_type,
                user_input=user_input,
                override_approval_id=override_id,
                execution_contract_hash=session_context.get("governance_execution_contract_hash"),
                resume_token_ref=session_context.get("governance_resume_token_ref"),
            )
            if decision.action.value == "require_approval":
                return OrchestratorResult(
                    final_text="approval-required",
                    used_path="governance_pending",
                    fallback_events=["approval_pending"],
                    trace_id=f"trace-pilot-{task_type}-{trace_seed}",
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
                    trace_id=f"trace-pilot-{task_type}-{trace_seed}",
                    metrics={"governance_reason_code": decision.reason_code},
                )

        return OrchestratorResult(
            final_text=(
                f"pilot::{task_type}::{trace_seed}::"
                f"pilot-shared-context::{_compact_text(user_input)}"
            ),
            used_path="llm_only",
            fallback_events=[],
            trace_id=f"trace-pilot-{task_type}-{trace_seed}",
            metrics={"router_reason_code": "RULE_ROUTE", "task_type": task_type},
        )

    def process_fast_chat(
        self,
        user_input: str,
        session_context: dict[str, str] | None = None,
        stream: bool = False,
        candidate_reason: str | None = None,
        on_token=None,
    ) -> OrchestratorResult:
        del stream, candidate_reason, on_token
        return self.process(user_input, session_context=session_context, use_router=True)


def build_deterministic_pilot_orchestrator(config: RuntimeConfig) -> DeterministicPilotOrchestrator:
    return DeterministicPilotOrchestrator(config)


def run_pilot_check(
    *,
    spec: TeamSpec,
    config: RuntimeConfig,
    mode: str,
    root_dir: str | Path,
    live_orchestrator_builder: Callable[[RuntimeConfig], Any] | None = None,
) -> dict[str, Any]:
    normalized_mode = mode.strip().lower()
    if normalized_mode not in {"deterministic", "live-provider"}:
        raise PilotGateFailure("INVALID_INPUT", f"unsupported pilot-check mode: {mode}")

    scenario_id = f"pilot-gate-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
    pilot_root = Path(root_dir) / scenario_id
    pilot_root.mkdir(parents=True, exist_ok=True)
    runtime_config = _pilot_runtime_config(
        config,
        pilot_root,
        deterministic=normalized_mode == "deterministic",
    )
    active_policy_profile = Path(runtime_config.governance.policy_path).stem or None
    validation_errors = validate_team_spec(spec, active_policy_profile=active_policy_profile)
    if validation_errors:
        raise PilotGateFailure(
            "TEAM_SPEC_INVALID",
            f"pilot smoke spec failed validation: {'; '.join(validation_errors)}",
        )

    orchestrator_builder: Callable[[RuntimeConfig], Any]
    if normalized_mode == "deterministic":
        orchestrator_builder = build_deterministic_pilot_orchestrator
    else:
        if live_orchestrator_builder is None:
            raise PilotGateFailure(
                "INVALID_INPUT",
                "live-provider mode requires a live orchestrator builder",
            )
        orchestrator_builder = live_orchestrator_builder

    validation_runs = _run_validation_probes(spec, active_policy_profile=active_policy_profile)
    positive_a = _run_positive_smoke(
        name="positive-smoke-a",
        spec=spec,
        config=runtime_config,
        orchestrator_builder=orchestrator_builder,
    )
    clean_replays = list(positive_a["clean_replays"])
    scenario_runs: list[dict[str, Any]] = [*validation_runs, positive_a["summary"]]

    determinism_check: dict[str, Any]
    warnings: list[str] = []
    if normalized_mode == "deterministic":
        positive_b = _run_positive_smoke(
            name="positive-smoke-b",
            spec=spec,
            config=runtime_config,
            orchestrator_builder=orchestrator_builder,
        )
        clean_replays.extend(positive_b["clean_replays"])
        scenario_runs.append(positive_b["summary"])
        same_digest = positive_a["graph_digest"] == positive_b["graph_digest"]
        determinism_check = {
            "status": "pass" if same_digest else "fail",
            "digest_a": positive_a["graph_digest"],
            "digest_b": positive_b["graph_digest"],
        }
    else:
        determinism_check = {
            "status": "report_only",
            "digest_a": positive_a["graph_digest"],
            "digest_b": None,
        }
        warnings.append("determinism digest comparison is report-only in live-provider mode")

    tamper_probe = _run_tamper_probe(
        name="tamper-probe",
        jobs_root=Path(runtime_config.team.artifact_dir),
        source_job_id=positive_a["resume_job_id"],
    )
    scenario_runs.append(tamper_probe)
    reuse_probe = _run_reuse_probe(
        name="reuse-probe",
        spec=spec,
        config=runtime_config,
        orchestrator_builder=orchestrator_builder,
        source_job_id=positive_a["blocked_job_id"],
    )
    scenario_runs.append(reuse_probe)
    scope_probe = _run_scope_probe(name="scope-probe")
    scenario_runs.append(scope_probe)

    counters = _build_counters(
        scenario_runs=scenario_runs,
        clean_replays=clean_replays,
    )
    checks = _build_checks(
        positive_a=positive_a,
        validation_runs=validation_runs,
        tamper_probe=tamper_probe,
        reuse_probe=reuse_probe,
        scope_probe=scope_probe,
        counters=counters,
        determinism_check=determinism_check,
    )
    blocking_errors = _collect_blocking_errors(
        checks=checks,
        counters=counters,
        scenario_runs=scenario_runs,
    )
    overall_status = "pass" if not blocking_errors else "fail"

    job_ids = _unique_strings(
        job_id
        for item in scenario_runs
        for job_id in item.get("job_ids", [])
        if isinstance(job_id, str)
    )
    artifacts = {
        "pilot_root": str(pilot_root),
        "jobs_root": str(runtime_config.team.artifact_dir),
        "approval_store_path": str(runtime_config.governance.approval_store_path),
        "memory_db_path": str(runtime_config.memory.db_path),
        "trace_dir": str(runtime_config.trace_dir),
        "job_dirs": {
            job_id: str(Path(runtime_config.team.artifact_dir) / job_id)
            for job_id in job_ids
        },
    }

    return {
        "schema_version": "1",
        "generated_at": _now_iso(),
        "profile": runtime_config.profile_name,
        "mode": normalized_mode,
        "overall_status": overall_status,
        "failure_class": (
            "none"
            if overall_status == "pass"
            else "runtime_bug"
            if normalized_mode == "live-provider"
            else "gate_failure"
        ),
        "provider_retry_count": 0,
        "bounded_concurrency_status": (
            "pass"
            if counters.get("stale_approval_count", 0) == 0
            and counters.get("memory_conflict_count", 0) == 0
            else "fail"
        ),
        "scenario_id": scenario_id,
        "job_ids": job_ids,
        "checks": checks,
        "counters": counters,
        "blocking_errors": blocking_errors,
        "warnings": warnings,
        "artifacts": artifacts,
        "scenario_runs": scenario_runs,
    }


def write_pilot_report(
    path: str | Path,
    payload: dict[str, Any],
    *,
    config: RuntimeConfig | None = None,
) -> str:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    return write_signed_json(
        path=destination,
        artifact="team_pilot_report",
        data=payload,
        config=config,
        purpose="team-pilot-report",
        status="ok" if payload.get("overall_status") == "pass" else "error",
    )


def _run_positive_smoke(
    *,
    name: str,
    spec: TeamSpec,
    config: RuntimeConfig,
    orchestrator_builder: Callable[[RuntimeConfig], Any],
) -> dict[str, Any]:
    request = (
        "Pilot gate smoke request: build a controlled rollout summary with research evidence, "
        "compliance constraints, and a final reviewer synthesis."
    )
    blocked_job_id = f"{name}-blocked"
    resume_job_id = f"{name}-resume"
    case_id = f"{name}-case"

    blocked_result = TeamSupervisor(
        orchestrator=orchestrator_builder(config),
        config=config,
    ).run(
        spec=spec,
        request=request,
        case_id=case_id,
        job_id=blocked_job_id,
    )
    if blocked_result.job.status.value != "blocked":
        raise PilotGateFailure(
            "PILOT_SMOKE_EXPECTED_BLOCKED",
            f"{name} did not block for approval; got status={blocked_result.job.status.value}",
        )

    blocked_events = load_events(blocked_job_id, root_dir=config.team.artifact_dir)
    blocked_orchestrator = orchestrator_builder(config)
    governance_runtime = getattr(blocked_orchestrator, "governance_runtime", None)
    if governance_runtime is None:
        raise PilotGateFailure("GOVERNANCE_UNAVAILABLE", "pilot smoke requires governance runtime")

    approval_ids = _requested_approval_ids(blocked_events)
    if not approval_ids:
        raise PilotGateFailure(
            "APPROVAL_NOT_REQUESTED",
            f"{name} did not emit approval_requested for the restricted smoke path",
        )

    approved_ids: list[str] = []
    executed_ids: list[str] = []
    observed_error_codes: list[str] = []
    for approval_id in approval_ids:
        decision = governance_runtime.decide_approval(
            approval_id=approval_id,
            approve=True,
            actor="pilot-gate",
            reason=f"approved during {name}",
        )
        if decision.error_code is not None:
            observed_error_codes.append(decision.error_code)
            continue
        approved_ids.append(approval_id)
        execution = governance_runtime.execute_approval(approval_id=approval_id)
        if execution.error_code is not None:
            observed_error_codes.append(execution.error_code)
            continue
        executed_ids.append(approval_id)

    resume_payload = _resume_from_source_job(
        spec=spec,
        config=config,
        orchestrator_builder=orchestrator_builder,
        source_job_id=blocked_job_id,
        resume_job_id=resume_job_id,
        source_events=blocked_events,
        request=request,
        case_id=case_id,
    )
    resumed_result = resume_payload["result"]
    if resumed_result.job.status.value != "completed":
        raise PilotGateFailure(
            "PILOT_SMOKE_EXPECTED_COMPLETED",
            f"{name} resume did not complete; got status={resumed_result.job.status.value}",
        )

    resumed_events = load_events(resume_job_id, root_dir=config.team.artifact_dir)
    blocked_replay = replay_job(blocked_job_id, root_dir=config.team.artifact_dir, verify=True)
    resume_replay = replay_job(resume_job_id, root_dir=config.team.artifact_dir, verify=True)
    graph_digest = _graph_digest([blocked_events, resumed_events])
    consumed_ids = _consumed_approval_ids(resumed_events)

    return {
        "graph_digest": graph_digest,
        "blocked_job_id": blocked_job_id,
        "resume_job_id": resume_job_id,
        "clean_replays": [blocked_replay, resume_replay],
        "summary": {
            "name": name,
            "status": "pass",
            "job_ids": [blocked_job_id, resume_job_id],
            "graph_digest": graph_digest,
            "expected_failure": False,
            "observed_error_codes": observed_error_codes,
            "replay_verified": (
                bool(blocked_replay.get("verified"))
                and bool(resume_replay.get("verified"))
            ),
            "approvals_requested": len(approval_ids),
            "approvals_approved": len(approved_ids),
            "approvals_executed": len(executed_ids),
            "approvals_consumed": len(consumed_ids),
            "artifacts": {
                "blocked_job_dir": str(Path(config.team.artifact_dir) / blocked_job_id),
                "resume_job_dir": str(Path(config.team.artifact_dir) / resume_job_id),
                "blocked_audit_envelope": blocked_result.audit_envelope_path,
                "resume_audit_envelope": resumed_result.audit_envelope_path,
            },
        },
    }


def _resume_from_source_job(
    *,
    spec: TeamSpec,
    config: RuntimeConfig,
    orchestrator_builder: Callable[[RuntimeConfig], Any],
    source_job_id: str,
    resume_job_id: str,
    source_events: list[dict[str, Any]],
    request: str,
    case_id: str,
) -> dict[str, Any]:
    orchestrator = orchestrator_builder(config)
    governance_runtime = getattr(orchestrator, "governance_runtime", None)
    overrides, resolved = _collect_resume_overrides(
        events=source_events,
        governance_runtime=governance_runtime,
    )
    if not overrides:
        raise PilotGateFailure(
            "NO_EXECUTED_APPROVALS",
            f"no executed approvals found for resume source job {source_job_id}",
        )
    try:
        continuation_state = derive_resume_continuation_state(
            spec=spec,
            source_job_id=source_job_id,
            root_dir=config.team.artifact_dir,
            source_events=source_events,
        )
    except ResumeContinuationError as exc:
        raise PilotGateFailure(exc.code, str(exc)) from exc

    result = TeamSupervisor(orchestrator=orchestrator, config=config).run(
        spec=spec,
        request=request,
        case_id=case_id,
        job_id=resume_job_id,
        approval_overrides=overrides,
        continuation_state=continuation_state,
    )
    return {"result": result, "resolved": resolved}


def _run_tamper_probe(*, name: str, jobs_root: Path, source_job_id: str) -> dict[str, Any]:
    source_dir = jobs_root / source_job_id
    tampered_job_id = f"{source_job_id}-tampered"
    tampered_dir = jobs_root / tampered_job_id
    shutil.copytree(source_dir, tampered_dir)

    events_path = tampered_dir / "events.jsonl"
    lines = events_path.read_text(encoding="utf-8").splitlines()
    if not lines:
        raise PilotGateFailure("PILOT_TAMPER_MISSING_EVENTS", f"{name} source job has no events")
    tampered = json.loads(lines[0])
    tampered["event_seq"] = int(tampered.get("event_seq") or 0) + 97
    lines[0] = json.dumps(tampered, ensure_ascii=False)
    events_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    replay = replay_job(tampered_job_id, root_dir=jobs_root, verify=True)
    return {
        "name": name,
        "status": "pass" if not replay.get("verified") else "fail",
        "job_ids": [tampered_job_id],
        "graph_digest": None,
        "expected_failure": True,
        "observed_error_codes": list(replay.get("errors") or []),
        "replay_verified": bool(replay.get("verified")),
        "artifacts": {"tampered_job_dir": str(tampered_dir)},
    }


def _run_reuse_probe(
    *,
    name: str,
    spec: TeamSpec,
    config: RuntimeConfig,
    orchestrator_builder: Callable[[RuntimeConfig], Any],
    source_job_id: str,
) -> dict[str, Any]:
    source_events = load_events(source_job_id, root_dir=config.team.artifact_dir)
    try:
        _resume_from_source_job(
            spec=spec,
            config=config,
            orchestrator_builder=orchestrator_builder,
            source_job_id=source_job_id,
            resume_job_id=f"{source_job_id}-reuse-attempt",
            source_events=source_events,
            request="reuse probe",
            case_id=f"{source_job_id}-case",
        )
    except PilotGateFailure as exc:
        return {
            "name": name,
            "status": "pass" if exc.error_code == "NO_EXECUTED_APPROVALS" else "fail",
            "job_ids": [],
            "graph_digest": None,
            "expected_failure": True,
            "observed_error_codes": [exc.error_code],
            "replay_verified": False,
        }

    return {
        "name": name,
        "status": "fail",
        "job_ids": [f"{source_job_id}-reuse-attempt"],
        "graph_digest": None,
        "expected_failure": True,
        "observed_error_codes": ["APPROVAL_REUSE_UNEXPECTED_SUCCESS"],
        "replay_verified": False,
    }


def _run_scope_probe(*, name: str) -> dict[str, Any]:
    validation = validate_memory_access(
        declared_scopes=["session"],
        requested_scope="case",
        requested_visibility="team",
    )
    return {
        "name": name,
        "status": "pass" if not validation.allowed else "fail",
        "job_ids": [],
        "graph_digest": None,
        "expected_failure": True,
        "observed_error_codes": [validation.reason_code],
        "replay_verified": False,
        "scope_probe": {
            "declared_scopes": ["session"],
            "requested_scope": "case",
            "requested_visibility": "team",
        },
    }


def _run_validation_probes(
    spec: TeamSpec,
    *,
    active_policy_profile: str | None,
) -> list[dict[str, Any]]:
    base_payload = spec.model_dump(mode="python")

    unknown_profile_payload = json.loads(json.dumps(base_payload, ensure_ascii=False))
    unknown_profile_payload["team"]["agents"][0]["tool_policy_profile"] = "missing-profile"
    unknown_profile_errors = validate_team_spec(
        TeamSpec.model_validate(unknown_profile_payload),
        active_policy_profile=active_policy_profile,
    )

    missing_handoff_payload = json.loads(json.dumps(base_payload, ensure_ascii=False))
    rules = list(missing_handoff_payload["team"].get("handoff_rules") or [])
    if rules:
        rules.pop()
    missing_handoff_payload["team"]["handoff_rules"] = rules
    missing_handoff_errors = validate_team_spec(
        TeamSpec.model_validate(missing_handoff_payload),
        active_policy_profile=active_policy_profile,
    )

    return [
        {
            "name": "validation-unknown-tool-policy-profile",
            "status": (
                "pass"
                if any("tool_policy_profile" in item for item in unknown_profile_errors)
                else "fail"
            ),
            "job_ids": [],
            "graph_digest": None,
            "expected_failure": True,
            "observed_error_codes": unknown_profile_errors,
            "replay_verified": False,
        },
        {
            "name": "validation-missing-handoff-coverage",
            "status": "pass"
            if any("not covered by team.handoff_rules" in item for item in missing_handoff_errors)
            else "fail",
            "job_ids": [],
            "graph_digest": None,
            "expected_failure": True,
            "observed_error_codes": missing_handoff_errors,
            "replay_verified": False,
        },
    ]


def _build_counters(
    *,
    scenario_runs: list[dict[str, Any]],
    clean_replays: list[dict[str, Any]],
) -> dict[str, int]:
    total_events = sum(int(item.get("event_count") or 0) for item in clean_replays)
    replay_pass_count = sum(1 for item in clean_replays if item.get("verified"))
    replay_fail_count = len(clean_replays) - replay_pass_count
    duplicate_event_seq_count = sum(
        int(item.get("consistency", {}).get("duplicate_event_seq_count") or 0)
        for item in clean_replays
    )
    non_contiguous_event_seq_count = sum(
        int(item.get("consistency", {}).get("non_contiguous_event_seq_count") or 0)
        for item in clean_replays
    )
    missing_causal_ref_count = sum(
        int(item.get("consistency", {}).get("missing_causal_ref_count") or 0)
        for item in clean_replays
    )
    missing_terminal_task_count = sum(
        int(item.get("consistency", {}).get("missing_terminal_task_count") or 0)
        for item in clean_replays
    )
    payload_hash_mismatch_count = sum(
        int(item.get("consistency", {}).get("payload_hash_mismatch_count") or 0)
        for item in clean_replays
    )

    approvals_requested = sum(int(item.get("approvals_requested") or 0) for item in scenario_runs)
    approvals_approved = sum(int(item.get("approvals_approved") or 0) for item in scenario_runs)
    approvals_executed = sum(int(item.get("approvals_executed") or 0) for item in scenario_runs)
    approvals_consumed = sum(int(item.get("approvals_consumed") or 0) for item in scenario_runs)
    consumed_without_executed_count = max(approvals_consumed - approvals_executed, 0)
    approval_reuse_attempts = sum(1 for item in scenario_runs if item.get("name") == "reuse-probe")
    approval_reuse_unexpected_success_count = sum(
        1
        for item in scenario_runs
        if item.get("name") == "reuse-probe" and item.get("status") != "pass"
    )
    tamper_verify_unexpected_pass_count = sum(
        1
        for item in scenario_runs
        if item.get("name") == "tamper-probe" and item.get("status") != "pass"
    )
    scope_violation_count = sum(1 for item in scenario_runs if item.get("name") == "scope-probe")
    scope_violation_unexpected_success_count = sum(
        1
        for item in scenario_runs
        if item.get("name") == "scope-probe" and item.get("status") != "pass"
    )

    all_job_ids = _unique_strings(
        job_id
        for item in scenario_runs
        for job_id in item.get("job_ids", [])
        if isinstance(job_id, str)
    )
    all_events = []
    event_lists = []
    root_hint = None
    for item in scenario_runs:
        artifacts = item.get("artifacts") or {}
        if isinstance(artifacts, dict):
            blocked_dir = artifacts.get("blocked_job_dir") or artifacts.get("resume_job_dir")
            if isinstance(blocked_dir, str):
                root_hint = str(Path(blocked_dir).parent)
                break
    if root_hint:
        for job_id in all_job_ids:
            event_lists.append(load_events(job_id, root_dir=root_hint))
    for events in event_lists:
        all_events.extend(events)

    safe_abort_count = sum(1 for item in all_events if str(item.get("event") or "") == "safe_abort")
    retry_count = sum(1 for item in all_events if str(item.get("event") or "") == "task_retry")
    memory_read_count = sum(
        1 for item in all_events if str(item.get("event") or "") == "memory_read_succeeded"
    )
    memory_write_count = sum(
        1 for item in all_events if str(item.get("event") or "") == "memory_write_succeeded"
    )
    handoff_count = sum(1 for item in all_events if str(item.get("event") or "") == "handoff")
    stale_approval_count = sum(
        1 for item in all_events if str(item.get("event") or "") == "approval_stale"
    )
    stale_resume_count = sum(
        1
        for item in all_events
        if str(item.get("event") or "") in {"approval_stale", "resume_duplicate_suppressed"}
    )
    resume_duplicate_suppressed_count = sum(
        1
        for item in all_events
        if str(item.get("event") or "") == "resume_duplicate_suppressed"
    )
    memory_conflict_count = sum(
        1
        for item in all_events
        if str(item.get("event") or "") == "memory_conflict_rejected"
    )
    serialized_due_to_policy_count = sum(
        1 for item in all_events if bool(item.get("serialized_due_to_policy"))
    )
    fallback_mode_count = sum(
        1 for item in all_events if str(item.get("event") or "") == "fallback_mode_applied"
    )
    resume_frontier_count = sum(
        1 for item in all_events if str(item.get("event") or "") == "team.resume.frontier_loaded"
    )
    resume_root_restart_count = sum(
        int((item.get("data") or {}).get("resume_root_restart_count") or 0)
        for item in all_events
        if str(item.get("event") or "") == "team.resume.continuation_selected"
    )
    approval_carry_forward_count = sum(
        1
        for item in all_events
        if str(item.get("event") or "") == "team.resume.approval_carry_forwarded"
    )
    resume_lineage_mismatch_count = sum(
        1 for item in all_events if str(item.get("event") or "") == "team.resume.lineage_mismatch"
    )
    invalid_frontier_count = sum(
        1 for item in all_events if str(item.get("event") or "") == "team.resume.invalid_frontier"
    )

    return {
        "total_events": total_events,
        "duplicate_event_seq_count": duplicate_event_seq_count,
        "non_contiguous_event_seq_count": non_contiguous_event_seq_count,
        "missing_causal_ref_count": missing_causal_ref_count,
        "missing_terminal_task_count": missing_terminal_task_count,
        "approvals_created": approvals_requested,
        "approvals_approved": approvals_approved,
        "approvals_executed": approvals_executed,
        "approvals_consumed": approvals_consumed,
        "consumed_without_executed_count": consumed_without_executed_count,
        "approval_reuse_attempts": approval_reuse_attempts,
        "approval_reuse_unexpected_success_count": approval_reuse_unexpected_success_count,
        "replay_verify_pass_count": replay_pass_count,
        "replay_verify_fail_count": replay_fail_count,
        "tamper_verify_unexpected_pass_count": tamper_verify_unexpected_pass_count,
        "trace_hash_mismatch_count": payload_hash_mismatch_count,
        "scope_violation_count": scope_violation_count,
        "scope_violation_unexpected_success_count": scope_violation_unexpected_success_count,
        "safe_abort_count": safe_abort_count,
        "retry_count": retry_count,
        "memory_read_count": memory_read_count,
        "memory_write_count": memory_write_count,
        "handoff_count": handoff_count,
        "stale_approval_count": stale_approval_count,
        "stale_resume_count": stale_resume_count,
        "resume_duplicate_suppressed_count": resume_duplicate_suppressed_count,
        "memory_conflict_count": memory_conflict_count,
        "serialized_due_to_policy_count": serialized_due_to_policy_count,
        "fallback_mode_count": fallback_mode_count,
        "resume_frontier_count": resume_frontier_count,
        "resume_root_restart_count": resume_root_restart_count,
        "approval_carry_forward_count": approval_carry_forward_count,
        "resume_lineage_mismatch_count": resume_lineage_mismatch_count,
        "invalid_frontier_count": invalid_frontier_count,
    }


def _build_checks(
    *,
    positive_a: dict[str, Any],
    validation_runs: list[dict[str, Any]],
    tamper_probe: dict[str, Any],
    reuse_probe: dict[str, Any],
    scope_probe: dict[str, Any],
    counters: dict[str, int],
    determinism_check: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    positive_summary = positive_a["summary"]
    validation_ok = all(item.get("status") == "pass" for item in validation_runs)
    clean_replays_ok = all(item.get("verified") for item in positive_a["clean_replays"])

    approval_lifecycle_ok = (
        positive_summary.get("approvals_requested", 0) > 0
        and positive_summary.get("approvals_requested")
        == positive_summary.get("approvals_approved")
        and positive_summary.get("approvals_approved")
        == positive_summary.get("approvals_executed")
        and positive_summary.get("approvals_executed")
        == positive_summary.get("approvals_consumed")
        and reuse_probe.get("status") == "pass"
        and counters["consumed_without_executed_count"] == 0
    )
    audit_ok = (
        clean_replays_ok
        and counters["duplicate_event_seq_count"] == 0
        and counters["non_contiguous_event_seq_count"] == 0
        and counters["missing_causal_ref_count"] == 0
        and counters["missing_terminal_task_count"] == 0
        and counters["safe_abort_count"] > 0
    )
    replay_ok = (
        clean_replays_ok
        and tamper_probe.get("status") == "pass"
        and counters["trace_hash_mismatch_count"] == 0
    )
    scope_ok = (
        scope_probe.get("status") == "pass"
        and counters["scope_violation_unexpected_success_count"] == 0
    )
    handoff_ok = (
        validation_ok
        and counters["handoff_count"] > 0
        and counters["trace_hash_mismatch_count"] == 0
        and any(
            item.get("name") == "validation-missing-handoff-coverage"
            and item.get("status") == "pass"
            for item in validation_runs
        )
    )
    policy_ok = (
        validation_ok
        and positive_summary.get("approvals_requested", 0) > 0
        and any(
            item.get("name") == "validation-unknown-tool-policy-profile"
            and item.get("status") == "pass"
            for item in validation_runs
        )
    )
    bounded_concurrency_ok = (
        counters["stale_approval_count"] == 0
        and counters["memory_conflict_count"] == 0
        and counters["resume_duplicate_suppressed_count"] == 0
    )

    return {
        "approval_lifecycle": {
            "status": "pass" if approval_lifecycle_ok else "fail",
            "requested": positive_summary.get("approvals_requested", 0),
            "approved": positive_summary.get("approvals_approved", 0),
            "executed": positive_summary.get("approvals_executed", 0),
            "consumed": positive_summary.get("approvals_consumed", 0),
        },
        "audit_completeness": {
            "status": "pass" if audit_ok else "fail",
            "safe_abort_count": counters["safe_abort_count"],
            "missing_causal_ref_count": counters["missing_causal_ref_count"],
            "missing_terminal_task_count": counters["missing_terminal_task_count"],
        },
        "replay_integrity": {
            "status": "pass" if replay_ok else "fail",
            "clean_replay_passes": counters["replay_verify_pass_count"],
            "clean_replay_failures": counters["replay_verify_fail_count"],
            "tamper_probe_status": tamper_probe.get("status"),
        },
        "scope_isolation": {
            "status": "pass" if scope_ok else "fail",
            "probe_status": scope_probe.get("status"),
            "scope_violation_unexpected_success_count": counters[
                "scope_violation_unexpected_success_count"
            ],
        },
        "handoff_contract": {
            "status": "pass" if handoff_ok else "fail",
            "handoff_count": counters["handoff_count"],
            "validation_probe_status": next(
                (
                    item.get("status")
                    for item in validation_runs
                    if item.get("name") == "validation-missing-handoff-coverage"
                ),
                "fail",
            ),
        },
        "policy_profile_enforcement": {
            "status": "pass" if policy_ok else "fail",
            "approval_count": positive_summary.get("approvals_requested", 0),
            "validation_probe_status": next(
                (
                    item.get("status")
                    for item in validation_runs
                    if item.get("name") == "validation-unknown-tool-policy-profile"
                ),
                "fail",
            ),
        },
        "bounded_concurrency": {
            "status": "pass" if bounded_concurrency_ok else "fail",
            "stale_approval_count": counters["stale_approval_count"],
            "memory_conflict_count": counters["memory_conflict_count"],
            "resume_duplicate_suppressed_count": counters[
                "resume_duplicate_suppressed_count"
            ],
            "serialized_due_to_policy_count": counters["serialized_due_to_policy_count"],
            "fallback_mode_count": counters["fallback_mode_count"],
        },
        "determinism": determinism_check,
    }


def _collect_blocking_errors(
    *,
    checks: dict[str, dict[str, Any]],
    counters: dict[str, int],
    scenario_runs: list[dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    for name, payload in checks.items():
        status = str(payload.get("status") or "")
        if status == "fail":
            errors.append(f"check_failed:{name}")

    if counters["consumed_without_executed_count"] > 0:
        errors.append("consumed_without_executed")
    if counters["approval_reuse_unexpected_success_count"] > 0:
        errors.append("approval_reuse_unexpected_success")
    if counters["tamper_verify_unexpected_pass_count"] > 0:
        errors.append("tamper_verify_unexpected_pass")
    if counters["duplicate_event_seq_count"] > 0 or counters["non_contiguous_event_seq_count"] > 0:
        errors.append("event_sequence_mismatch")
    if counters["missing_causal_ref_count"] > 0:
        errors.append("missing_causal_ref")
    if counters["missing_terminal_task_count"] > 0:
        errors.append("missing_terminal_task")
    if counters["scope_violation_unexpected_success_count"] > 0:
        errors.append("scope_violation_unexpected_success")
    if counters["replay_verify_fail_count"] > 0:
        errors.append("clean_replay_failed")
    if counters["stale_approval_count"] > 0:
        errors.append("stale_approval_detected")
    if counters["memory_conflict_count"] > 0:
        errors.append("memory_conflict_detected")
    for item in scenario_runs:
        if item.get("expected_failure") and item.get("status") == "fail":
            errors.append(f"expected_failure_probe_failed:{item.get('name')}")
    return errors


def _collect_resume_overrides(
    *,
    events: list[dict[str, Any]],
    governance_runtime,
) -> tuple[dict[str, dict[str, str]], list[dict[str, str]]]:
    if governance_runtime is None:
        return {}, []
    governance_runtime.approval_store.expire_pending()

    overrides: dict[str, dict[str, str]] = {}
    resolved: list[dict[str, str]] = []
    for item in events:
        if str(item.get("event") or "") != "approval_requested":
            continue
        task_id = str(item.get("task_id") or "").strip()
        data = item.get("data")
        if not isinstance(data, dict):
            continue
        approval_id = str(data.get("approval_id") or "").strip()
        if not task_id or not approval_id:
            continue
        target = _normalize_resume_target(str(data.get("target") or "handoff"))
        ticket = governance_runtime.get_approval(approval_id)
        if ticket is None:
            continue
        if ticket.status.value != "executed":
            continue
        if ticket.execution_status.value != "executed":
            continue
        if ticket.consumed_at is not None or ticket.consumed_by_job_id is not None:
            continue
        overrides.setdefault(task_id, {})[target] = approval_id
        resolved.append(
            {
                "task_id": task_id,
                "target": target,
                "approval_id": approval_id,
                "status": ticket.status.value,
            }
        )
    return overrides, resolved


def _normalize_resume_target(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in {"task", "handoff", "memory_write"}:
        return normalized
    return "handoff"


def _requested_approval_ids(events: list[dict[str, Any]]) -> list[str]:
    values: list[str] = []
    for item in events:
        if str(item.get("event") or "") != "approval_requested":
            continue
        data = item.get("data")
        if not isinstance(data, dict):
            continue
        approval_id = str(data.get("approval_id") or "").strip()
        if approval_id:
            values.append(approval_id)
    return _unique_strings(values)


def _consumed_approval_ids(events: list[dict[str, Any]]) -> list[str]:
    values: list[str] = []
    for item in events:
        if str(item.get("event") or "") != "approval_consumed":
            continue
        data = item.get("data")
        if not isinstance(data, dict):
            continue
        approval_id = str(data.get("approval_id") or "").strip()
        if approval_id:
            values.append(approval_id)
    return _unique_strings(values)


def _graph_digest(event_groups: list[list[dict[str, Any]]]) -> str:
    normalized = sorted(
        (_normalize_event(item) for group in event_groups for item in group),
        key=lambda item: json.dumps(
            item,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ),
    )
    return _short_hash(normalized, length=24)


def _normalize_event(event: dict[str, Any]) -> dict[str, Any]:
    data = event.get("data")
    if not isinstance(data, dict):
        data = {}
    normalized_data = {
        key: data[key]
        for key in sorted(data.keys())
        if key
        in {
            "count",
            "depends_on",
            "from_role",
            "missing_dependency",
            "reason",
            "reason_code",
            "scope",
            "status",
            "target",
            "task_count",
            "task_type",
            "to_role",
            "visibility",
            "written",
        }
    }
    return {
        "event": event.get("event"),
        "task_id": event.get("task_id"),
        "task_attempt": event.get("task_attempt"),
        "role": event.get("role"),
        "phase": event.get("phase"),
        "status_before": event.get("status_before"),
        "status_after": event.get("status_after"),
        "data": normalized_data,
    }


def _pilot_runtime_config(
    config: RuntimeConfig,
    root_dir: Path,
    *,
    deterministic: bool,
) -> RuntimeConfig:
    return config.model_copy(
        update={
            "memory": config.memory.model_copy(
                update={"db_path": str(root_dir / "memory.sqlite3")}
            ),
            "governance": config.governance.model_copy(
                update={
                    "approval_store_path": str(root_dir / "approvals.sqlite3"),
                    "audit_dir": str(root_dir / "audit"),
                }
            ),
            "team": config.team.model_copy(
                update={
                    "artifact_dir": str(root_dir / "jobs"),
                    "checkpoint_db_path": str(root_dir / "checkpoints.sqlite3"),
                    "max_parallel_tasks": 1
                    if deterministic
                    else config.team.max_parallel_tasks,
                }
            ),
            "trace_dir": str(root_dir / "traces"),
        }
    )


def _build_memory_manager(config: RuntimeConfig) -> MemoryManager:
    store = (
        PersistentMemoryStore(db_path=config.memory.db_path)
        if config.enable_persistent_memory
        else None
    )
    gate = SalienceGate(
        threshold=config.memory.salience_threshold,
        decay=config.memory.salience_decay,
        task_bonus=config.memory.task_bonus,
        expert_bonus=config.memory.expert_bonus,
        spike_reduction=config.memory.spike_reduction,
        keyword_weights=config.memory.keyword_weights,
    )
    return MemoryManager(
        enabled=config.enable_persistent_memory,
        store=store,
        gate=gate,
        max_rows=config.memory.max_rows,
        ttl_days=config.memory_ttl_days,
        rank_salience_weight=config.memory.rank_salience_weight,
        rank_recency_weight=config.memory.rank_recency_weight,
    )


def _short_hash(payload: Any, *, length: int = 12) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:length]


def _compact_text(value: str, *, limit: int = 96) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3] + "..."


def _unique_strings(values) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        normalized = str(value).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
