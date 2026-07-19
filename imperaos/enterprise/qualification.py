from __future__ import annotations

import json
import platform
import threading
import time
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from imperaos import __version__
from imperaos.enterprise.observability import collect_metrics_snapshot
from imperaos.enterprise.signing import load_signed_artifact, write_signed_json
from imperaos.runtime.config import RuntimeConfig
from imperaos.team.continuation import derive_resume_continuation_state
from imperaos.team.models import TeamSpec
from imperaos.team.pilot_gate import (
    _build_counters,
    _collect_resume_overrides,
    _consumed_approval_ids,
    _graph_digest,
    _pilot_runtime_config,
    _requested_approval_ids,
    _resume_from_source_job,
    _run_reuse_probe,
    build_deterministic_pilot_orchestrator,
)
from imperaos.team.replay import load_events, load_job_status, load_task_runs, replay_job
from imperaos.team.supervisor import TeamSupervisor
from imperaos.team.validation import validate_team_spec

MIN_GREEN_SOAK_SECONDS = 21_600
MIN_EXTENDED_SOAK_SECONDS = 86_400
QUALIFICATION_REPORT_VERSION = "1"
REQUIRED_WORKLOADS = (
    "baseline_enterprise_flow",
    "approval_heavy_flow",
    "conflict_heavy_flow",
    "soak_6h_flow",
    "failure_injection_flow",
)
OPTIONAL_WORKLOADS = ("24h_soak_flow",)
ALL_WORKLOADS = REQUIRED_WORKLOADS + OPTIONAL_WORKLOADS


class QualificationFailure(RuntimeError):
    def __init__(self, error_code: str, message: str):
        super().__init__(message)
        self.error_code = error_code
        self.message = message


def _run_workload_capture(
    *,
    name: str,
    purpose: str,
    execution_mode: str,
    required_for_green: bool,
    support_classification: str,
    workload_root: Path,
    runner: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    workload_root.mkdir(parents=True, exist_ok=True)
    started = datetime.now(UTC)
    try:
        return runner()
    except Exception as exc:  # noqa: BLE001
        ended = datetime.now(UTC)
        error_code = str(getattr(exc, "error_code", "QUALIFICATION_WORKLOAD_FAILED"))
        failure_class = _classify_workload_failure(error_code)
        return {
            "name": name,
            "purpose": purpose,
            "start_time": _iso(started),
            "end_time": _iso(ended),
            "duration_seconds": max(1, int((ended - started).total_seconds())),
            "execution_mode": execution_mode,
            "required_for_green": required_for_green,
            "support_classification": "unsupported",
            "pass_fail": "fail",
            "task_count_total": 0,
            "task_count_success": 0,
            "task_count_failed": 0,
            "failure_class_breakdown": {failure_class: 1},
            "replay_verify_status": "not_run",
            "signing_verify_status": "not_run",
            "approval_latency_summary": {"count": 0},
            "provider_retry_count": 0,
            "stale_approval_count": 0,
            "stale_resume_count": 0,
            "resume_duplicate_suppressed_count": 0,
            "memory_conflict_count": 0,
            "serialized_due_to_policy_count": 0,
            "fallback_mode_count": 0,
            "operator_intervention_count": 0,
            "support_bundle_sufficient": False,
            "metrics_snapshot_sufficient": False,
            "unclear_errors": [str(exc)],
            "runbook_gaps": [],
            "notes": [str(exc)],
            "operational_followups": [
                f"{name} failed before evidence completion; inspect {workload_root}"
            ],
            "terminal_status": "failed",
            "terminal_job_id": None,
            "resume_round_count": 0,
            "approval_rounds": [],
            "artifacts": {"workload_root": str(workload_root)},
            "blocking_findings": [error_code],
            "residual_risks": [str(exc)],
            "evidence_verified": False,
        }


class _DelegatingOrchestrator:
    def __init__(
        self,
        delegate,
        *,
        sleep_for_tasks: set[str] | None = None,
        delay_seconds: float = 0.0,
        fail_once_tasks: dict[str, str] | None = None,
        shared_failures: set[str] | None = None,
        barrier_tasks: set[str] | None = None,
        barrier_size: int = 0,
    ):
        self._delegate = delegate
        self.governance_runtime = getattr(delegate, "governance_runtime", None)
        self._memory_manager = getattr(delegate, "_memory_manager", None)
        self._sleep_for_tasks = sleep_for_tasks or set()
        self._delay_seconds = max(delay_seconds, 0.0)
        self._fail_once_tasks = dict(fail_once_tasks or {})
        self._seen_failures = shared_failures if shared_failures is not None else set()
        self._barrier_tasks = barrier_tasks or set()
        self._barrier = (
            threading.Barrier(barrier_size)
            if self._barrier_tasks and barrier_size >= 2
            else None
        )

    def process(
        self,
        user_input: str,
        session_context: dict[str, str] | None = None,
        use_router: bool = True,
    ):
        task_id = str((session_context or {}).get("task_id") or "")
        self._wait_for_barrier(task_id)
        if task_id in self._sleep_for_tasks and self._delay_seconds > 0:
            time.sleep(self._delay_seconds)
        failure_code = self._fail_once_tasks.get(task_id)
        if failure_code and task_id not in self._seen_failures:
            self._seen_failures.add(task_id)
            raise RuntimeError(failure_code)
        return self._delegate.process(
            user_input,
            session_context=session_context,
            use_router=use_router,
        )

    def process_fast_chat(
        self,
        user_input: str,
        session_context: dict[str, str] | None = None,
        stream: bool = False,
        candidate_reason: str | None = None,
        on_token=None,
    ):
        task_id = str((session_context or {}).get("task_id") or "")
        self._wait_for_barrier(task_id)
        if task_id in self._sleep_for_tasks and self._delay_seconds > 0:
            time.sleep(self._delay_seconds)
        failure_code = self._fail_once_tasks.get(task_id)
        if failure_code and task_id not in self._seen_failures:
            self._seen_failures.add(task_id)
            raise RuntimeError(failure_code)
        if hasattr(self._delegate, "process_fast_chat"):
            return self._delegate.process_fast_chat(
                user_input,
                session_context=session_context,
                stream=stream,
                candidate_reason=candidate_reason,
                on_token=on_token,
            )
        return self._delegate.process(user_input, session_context=session_context, use_router=True)

    def _wait_for_barrier(self, task_id: str) -> None:
        if task_id not in self._barrier_tasks or self._barrier is None:
            return
        try:
            self._barrier.wait(timeout=1.0)
        except threading.BrokenBarrierError:
            return


def _classify_workload_failure(error_code: str) -> str:
    normalized = error_code.strip().upper()
    if normalized.startswith("PROVIDER_") or normalized in {"TIMEOUT", "TRANSIENT_FAILURE"}:
        return "provider_flake"
    if normalized.startswith("POLICY_") or "APPROVAL" in normalized:
        return "policy_issue"
    if normalized in {"INVALID_INPUT", "INVALID_PROFILE", "TEAM_SPEC_INVALID"}:
        return "environment_invalid"
    return "runtime_bug"


def run_qualification(
    *,
    config: RuntimeConfig,
    mode: str,
    soak_hours: float,
    output_root: str | Path,
    live_orchestrator_builder: Callable[[RuntimeConfig], Any] | None,
    deterministic_orchestrator_builder: Callable[[RuntimeConfig], Any] | None = None,
    baseline_spec_path: str | Path = "examples/team/enterprise_qualification.yaml",
    conflict_spec_path: str | Path = "examples/team/enterprise_conflict.yaml",
    workloads: list[str] | None = None,
    merge_from_report: str | Path | None = None,
) -> dict[str, Any]:
    normalized_mode = mode.strip().lower()
    if normalized_mode != "mixed":
        raise QualificationFailure(
            "INVALID_INPUT",
            f"unsupported qualification mode: {mode}; only 'mixed' is supported",
        )
    if config.profile_name != "enterprise":
        raise QualificationFailure(
            "INVALID_PROFILE",
            "qualification runner currently supports only the enterprise profile",
        )
    if soak_hours <= 0:
        raise QualificationFailure("INVALID_INPUT", "soak-hours must be greater than zero")

    deterministic_builder = (
        deterministic_orchestrator_builder or build_deterministic_pilot_orchestrator
    )
    if live_orchestrator_builder is None:
        raise QualificationFailure(
            "INVALID_INPUT",
            "qualification runner requires a live orchestrator builder for mixed mode",
        )

    selected_workloads = _normalize_workloads(workloads)
    is_subset_run = selected_workloads != list(ALL_WORKLOADS)
    if is_subset_run and merge_from_report is None:
        raise QualificationFailure(
            "QUALIFICATION_MERGE_REQUIRED",
            "subset qualification runs require --merge-from-report",
        )
    resolved_merge_from_report = (
        _resolve_merge_from_report_path(merge_from_report, config=config)
        if merge_from_report is not None
        else None
    )

    run_id = f"qualification-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
    run_root = Path(output_root) / run_id
    run_root.mkdir(parents=True, exist_ok=True)

    baseline_spec = _load_team_spec(baseline_spec_path)
    conflict_spec = _load_team_spec(conflict_spec_path)
    _validate_spec(baseline_spec, config=config)
    _validate_spec(conflict_spec, config=config)

    workloads_payload: list[dict[str, Any]] = []
    registry = _qualification_workload_registry(
        baseline_spec=baseline_spec,
        conflict_spec=conflict_spec,
        config=config,
        run_root=run_root,
        live_orchestrator_builder=live_orchestrator_builder,
        deterministic_builder=deterministic_builder,
        soak_hours=soak_hours,
    )
    for workload_name in selected_workloads:
        runner_meta = registry[workload_name]
        workloads_payload.append(
            _run_workload_capture(
                name=workload_name,
                purpose=runner_meta["purpose"],
                execution_mode=runner_meta["execution_mode"],
                required_for_green=bool(runner_meta["required_for_green"]),
                support_classification=str(runner_meta["support_classification"]),
                workload_root=run_root / workload_name,
                runner=runner_meta["runner"],
            )
        )
    workloads_payload = _publish_extended_soak_evidence(
        workloads_payload,
        run_root=run_root,
    )

    environment_summary = {
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "cwd": str(Path.cwd()),
        "mode": normalized_mode,
        "provider": config.llm_provider,
        "fallback_provider": config.fallback_provider,
        "trace_dir": config.trace_dir,
    }
    evaluation = evaluate_qualification_evidence(
        qualification_payload={
            "profile": config.profile_name,
            "workloads": workloads_payload,
            "minimum_green_soak_seconds": MIN_GREEN_SOAK_SECONDS,
        }
    )
    report = {
        "version": QUALIFICATION_REPORT_VERSION,
        "generated_at": _now_iso(),
        "runtime_version": __version__,
        "environment_summary": environment_summary,
        "profile": config.profile_name,
        "signing_mode": config.keys.provider,
        "identity_mode": config.identity.mode,
        "qualification_evidence_mode": normalized_mode,
        "minimum_green_soak_seconds": MIN_GREEN_SOAK_SECONDS,
        "qualification_status": evaluation["qualification_status"],
        "workloads": workloads_payload,
        "supported_profiles": evaluation["supported_profiles"],
        "conditional_profiles": evaluation["conditional_profiles"],
        "unsupported_profiles": evaluation["unsupported_profiles"],
        "blocking_findings": evaluation["blocking_findings"],
        "residual_risks": evaluation["residual_risks"],
        "recommended_status": evaluation["recommended_status"],
        "go_no_go": evaluation["go_no_go"],
        "operational_findings": evaluation["operational_findings"],
        "artifacts": {
            "run_root": str(run_root),
        },
    }
    if resolved_merge_from_report is not None:
        report = _merge_qualification_report(
            existing_report_path=resolved_merge_from_report,
            rerun_payload=report,
            rerun_names=selected_workloads,
            config=config,
        )
        report.setdefault("artifacts", {})
        report["artifacts"]["run_root"] = str(run_root)
        report["artifacts"]["merged_from_report"] = str(resolved_merge_from_report)
    return report


def _qualification_workload_registry(
    *,
    baseline_spec: TeamSpec,
    conflict_spec: TeamSpec,
    config: RuntimeConfig,
    run_root: Path,
    live_orchestrator_builder: Callable[[RuntimeConfig], Any],
    deterministic_builder: Callable[[RuntimeConfig], Any],
    soak_hours: float,
) -> dict[str, dict[str, Any]]:
    return {
        "baseline_enterprise_flow": {
            "purpose": (
                "Validate the low-risk enterprise path with approval, replay, "
                "signing, metrics, and support artifacts."
            ),
            "execution_mode": "live_provider",
            "required_for_green": True,
            "support_classification": "supported",
            "runner": lambda: _run_baseline_enterprise_flow(
                spec=baseline_spec,
                base_config=config,
                run_root=run_root,
                live_orchestrator_builder=live_orchestrator_builder,
            ),
        },
        "approval_heavy_flow": {
            "purpose": (
                "Stress the approval lifecycle, duplicate suppression, and stale snapshot "
                "handling."
            ),
            "execution_mode": "deterministic_controlled",
            "required_for_green": True,
            "support_classification": "conditional",
            "runner": lambda: _run_approval_heavy_flow(
                spec=baseline_spec,
                base_config=config,
                run_root=run_root,
                deterministic_orchestrator_builder=deterministic_builder,
            ),
        },
        "conflict_heavy_flow": {
            "purpose": "Validate shared-state conflict rejection and replayable conflict handling.",
            "execution_mode": "deterministic_controlled",
            "required_for_green": True,
            "support_classification": "conditional",
            "runner": lambda: _run_conflict_heavy_flow(
                spec=conflict_spec,
                base_config=config,
                run_root=run_root,
                deterministic_orchestrator_builder=deterministic_builder,
            ),
        },
        "soak_6h_flow": {
            "purpose": (
                "Validate replay, signing, and bounded-concurrency stability over "
                "sustained runtime."
            ),
            "execution_mode": "deterministic_controlled",
            "required_for_green": True,
            "support_classification": "supported",
            "runner": lambda: _run_soak_flow(
                spec=baseline_spec,
                base_config=config,
                run_root=run_root,
                deterministic_orchestrator_builder=deterministic_builder,
                soak_hours=soak_hours,
                name="soak_6h_flow",
                purpose=(
                    "Validate replay, signing, and bounded-concurrency "
                    "stability over sustained runtime."
                ),
                required_for_green=True,
                support_classification="supported",
            ),
        },
        "failure_injection_flow": {
            "purpose": (
                "Validate fail-closed behavior and failure classification across controlled faults."
            ),
            "execution_mode": "mixed",
            "required_for_green": True,
            "support_classification": "conditional",
            "runner": lambda: _run_failure_injection_flow(
                spec=baseline_spec,
                base_config=config,
                run_root=run_root,
                live_orchestrator_builder=live_orchestrator_builder,
                deterministic_orchestrator_builder=deterministic_builder,
            ),
        },
        "24h_soak_flow": {
            "purpose": "Extended soak evidence for GA RC sign-off.",
            "execution_mode": "deterministic_controlled",
            "required_for_green": False,
            "support_classification": "conditional",
            "runner": lambda: _skipped_extended_soak(run_root=run_root),
        },
    }


def _normalize_workloads(workloads: list[str] | None) -> list[str]:
    if workloads is None:
        return list(ALL_WORKLOADS)
    names = [str(item).strip() for item in workloads if str(item).strip()]
    if not names:
        raise QualificationFailure("INVALID_INPUT", "workloads list cannot be empty")
    invalid = [name for name in names if name not in ALL_WORKLOADS]
    if invalid:
        raise QualificationFailure(
            "INVALID_INPUT",
            f"unknown workload names: {', '.join(sorted(set(invalid)))}",
        )
    seen: set[str] = set()
    ordered: list[str] = []
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        ordered.append(name)
    return ordered


def _resolve_merge_from_report_path(
    existing_report_path: str | Path | None,
    *,
    config: RuntimeConfig,
) -> Path:
    if existing_report_path is None:
        raise QualificationFailure(
            "QUALIFICATION_MERGE_REQUIRED",
            "subset qualification runs require --merge-from-report",
        )

    requested_path = Path(existing_report_path)
    if requested_path.exists():
        return requested_path

    latest_candidates = sorted(
        Path("artifacts").glob("qualification/qualification-*/qualification_report.json")
    )
    for candidate in reversed(latest_candidates):
        bundle = load_signed_artifact(path=candidate, config=config)
        payload = bundle.get("data") if isinstance(bundle, dict) else None
        if (
            bundle.get("present")
            and bundle.get("verified")
            and isinstance(payload, dict)
            and str(payload.get("profile") or "") == str(config.profile_name)
        ):
            return candidate

    raise QualificationFailure(
        "QUALIFICATION_SOURCE_REPORT_NOT_FOUND",
        f"qualification source report not found: {existing_report_path}",
    )


def _merge_qualification_report(
    *,
    existing_report_path: str | Path,
    rerun_payload: dict[str, Any],
    rerun_names: list[str],
    config: RuntimeConfig,
) -> dict[str, Any]:
    existing_bundle = load_signed_artifact(path=existing_report_path, config=config)
    if not existing_bundle.get("present"):
        raise QualificationFailure(
            "QUALIFICATION_SOURCE_REPORT_NOT_FOUND",
            f"qualification source report not found: {existing_report_path}",
        )
    if not existing_bundle.get("verified"):
        raise QualificationFailure(
            "QUALIFICATION_SOURCE_REPORT_UNVERIFIED",
            f"qualification source report signature invalid: {existing_bundle.get('error_code')}",
        )
    existing_payload = existing_bundle.get("data")
    if not isinstance(existing_payload, dict):
        raise QualificationFailure(
            "QUALIFICATION_SOURCE_REPORT_INVALID",
            "qualification source report payload is invalid",
        )

    for field_name in (
        "profile",
        "signing_mode",
        "identity_mode",
        "qualification_evidence_mode",
        "runtime_version",
    ):
        if str(existing_payload.get(field_name)) != str(rerun_payload.get(field_name)):
            raise QualificationFailure(
                "QUALIFICATION_SOURCE_REPORT_MISMATCH",
                f"qualification source report mismatch for {field_name}",
            )

    existing_workloads = existing_payload.get("workloads")
    rerun_workloads = rerun_payload.get("workloads")
    if not isinstance(existing_workloads, list) or not isinstance(rerun_workloads, list):
        raise QualificationFailure(
            "QUALIFICATION_SOURCE_REPORT_INVALID",
            "qualification source report workloads are invalid",
        )

    workload_map: dict[str, dict[str, Any]] = {}
    for item in existing_workloads:
        if isinstance(item, dict) and item.get("name"):
            workload_map[str(item["name"])] = item
    for item in rerun_workloads:
        if isinstance(item, dict) and item.get("name"):
            workload_map[str(item["name"])] = item

    merged_workloads = [workload_map[name] for name in ALL_WORKLOADS if name in workload_map]
    evaluation = evaluate_qualification_evidence(
        qualification_payload={
            "profile": rerun_payload.get("profile"),
            "workloads": merged_workloads,
            "minimum_green_soak_seconds": rerun_payload.get("minimum_green_soak_seconds"),
        }
    )

    merged = dict(existing_payload)
    merged.update(
        {
            "generated_at": rerun_payload.get("generated_at", _now_iso()),
            "environment_summary": rerun_payload.get(
                "environment_summary", existing_payload.get("environment_summary")
            ),
            "minimum_green_soak_seconds": rerun_payload.get(
                "minimum_green_soak_seconds", existing_payload.get("minimum_green_soak_seconds")
            ),
            "qualification_status": evaluation["qualification_status"],
            "workloads": merged_workloads,
            "supported_profiles": evaluation["supported_profiles"],
            "conditional_profiles": evaluation["conditional_profiles"],
            "unsupported_profiles": evaluation["unsupported_profiles"],
            "blocking_findings": evaluation["blocking_findings"],
            "residual_risks": evaluation["residual_risks"],
            "recommended_status": evaluation["recommended_status"],
            "go_no_go": evaluation["go_no_go"],
            "operational_findings": evaluation["operational_findings"],
            "artifacts": {
                **(existing_payload.get("artifacts") or {}),
                **(rerun_payload.get("artifacts") or {}),
                "merged_workloads": rerun_names,
            },
        }
    )
    return merged


def write_qualification_report(
    *,
    payload: dict[str, Any],
    config: RuntimeConfig,
    output_root: str | Path,
) -> dict[str, str]:
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    run_root = Path(payload.get("artifacts", {}).get("run_root") or root)
    run_root.mkdir(parents=True, exist_ok=True)

    run_json = run_root / "qualification_report.json"
    run_md = run_root / "QUALIFICATION_REPORT.md"
    latest_json = Path("artifacts") / "qualification_report.json"
    latest_md = Path("artifacts") / "QUALIFICATION_REPORT.md"
    payload.setdefault("artifacts", {})
    payload["artifacts"].update(
        {
            "run_json": str(run_json),
            "run_markdown": str(run_md),
            "latest_json": str(latest_json),
            "latest_markdown": str(latest_md),
        }
    )

    write_signed_json(
        path=run_json,
        artifact="qualification_report",
        data=payload,
        config=config,
        purpose="qualification-report",
        status="ok" if payload.get("qualification_status") != "fail" else "error",
    )
    run_md.write_text(render_qualification_markdown(payload), encoding="utf-8")

    latest_json.parent.mkdir(parents=True, exist_ok=True)
    write_signed_json(
        path=latest_json,
        artifact="qualification_report",
        data=payload,
        config=config,
        purpose="qualification-report",
        status="ok" if payload.get("qualification_status") != "fail" else "error",
    )
    latest_md.write_text(render_qualification_markdown(payload), encoding="utf-8")
    return {
        "run_json": str(run_json),
        "run_markdown": str(run_md),
        "latest_json": str(latest_json),
        "latest_markdown": str(latest_md),
    }


def render_qualification_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Qualification Report",
        "",
        "## Executive Summary",
        "",
        f"- Generated at: `{payload.get('generated_at')}`",
        f"- Runtime version: `{payload.get('runtime_version')}`",
        f"- Profile: `{payload.get('profile')}`",
        f"- Evidence mode: `{payload.get('qualification_evidence_mode')}`",
        f"- Qualification status: `{payload.get('qualification_status')}`",
        f"- Recommended status: `{payload.get('recommended_status')}`",
        f"- Go / No-Go: `{payload.get('go_no_go')}`",
        "",
        "## Workload Summary",
        "",
        "| Workload | Mode | Result | Evidence Verified | Duration (s) | Blocking Findings |",
        "| --- | --- | --- | --- | ---: | --- |",
    ]
    for item in payload.get("workloads", []):
        findings = ", ".join(item.get("blocking_findings") or []) or "none"
        lines.append(
            "| {name} | {mode} | {result} | {verified} | {duration} | {findings} |".format(
                name=item.get("name"),
                mode=item.get("execution_mode"),
                result=item.get("pass_fail"),
                verified="yes" if item.get("evidence_verified") else "no",
                duration=int(item.get("duration_seconds") or 0),
                findings=findings,
            )
        )

    lines.extend([
        "",
        "## Support Boundaries",
        "",
        "| Profile / Scenario | Status | Notes |",
        "| --- | --- | --- |",
    ])
    for section_name in ("supported_profiles", "conditional_profiles", "unsupported_profiles"):
        for item in payload.get(section_name, []):
            lines.append(
                f"| {item.get('scenario')} | {item.get('status')} | {item.get('notes')} |"
            )

    lines.extend(["", "## Operational Findings", ""])
    operational_findings = payload.get("operational_findings") or []
    has_multi_round = any(
        int((item or {}).get("resume_round_count") or 0) > 1
        for item in payload.get("workloads", [])
    )
    if has_multi_round:
        lines.append(
            "- live-provider workloads may require multiple approval rounds before "
            "terminal completion; "
            "single-resume completion is not assumed for enterprise mixed mode"
        )
    if operational_findings:
        lines.extend(f"- {item}" for item in operational_findings)
    else:
        lines.append("- none")

    lines.extend(["", "## Residual Risks", ""])
    residual = payload.get("residual_risks") or []
    if residual:
        lines.extend(f"- {item}" for item in residual)
    else:
        lines.append("- none")

    lines.extend(["", "## Blocking Findings", ""])
    blocking = payload.get("blocking_findings") or []
    if blocking:
        lines.extend(f"- {item}" for item in blocking)
    else:
        lines.append("- none")

    lines.extend([
        "",
        "## Final Recommendation",
        "",
        f"- Recommended status: `{payload.get('recommended_status')}`",
        f"- Go / No-Go: `{payload.get('go_no_go')}`",
    ])
    return "\n".join(lines) + "\n"


def evaluate_qualification_evidence(*, qualification_payload: dict[str, Any]) -> dict[str, Any]:
    workloads = qualification_payload.get("workloads") or []
    workload_map = {
        str(item.get("name") or ""): item
        for item in workloads
        if isinstance(item, dict) and item.get("name")
    }
    blocking_findings = list(qualification_payload.get("blocking_findings") or [])
    residual_risks = list(qualification_payload.get("residual_risks") or [])
    minimum_green_soak_seconds = int(
        qualification_payload.get("minimum_green_soak_seconds") or MIN_GREEN_SOAK_SECONDS
    )

    missing_required = [name for name in REQUIRED_WORKLOADS if name not in workload_map]
    if missing_required:
        blocking_findings.append(
            f"missing_required_workloads:{','.join(sorted(missing_required))}"
        )

    invalid_required: list[str] = []
    for name in REQUIRED_WORKLOADS:
        item = workload_map.get(name)
        if item is None:
            continue
        if not bool(item.get("evidence_verified")):
            invalid_required.append(name)
        if str(item.get("pass_fail") or "") != "pass":
            invalid_required.append(name)
        if (item.get("replay_verify_status") or "") != "pass":
            invalid_required.append(name)
        if (item.get("signing_verify_status") or "") != "pass":
            invalid_required.append(name)
        if item.get("blocking_findings"):
            invalid_required.append(name)
    if invalid_required:
        blocking_findings.append(
            f"required_workloads_failed:{','.join(sorted(set(invalid_required)))}"
        )

    soak = workload_map.get("soak_6h_flow") or {}
    soak_met = int(soak.get("duration_seconds") or 0) >= minimum_green_soak_seconds
    baseline = workload_map.get("baseline_enterprise_flow") or {}
    approval = workload_map.get("approval_heavy_flow") or {}
    conflict = workload_map.get("conflict_heavy_flow") or {}
    supported_profiles: list[dict[str, str]] = []
    conditional_profiles: list[dict[str, str]] = []
    unsupported_profiles: list[dict[str, str]] = []

    if (
        str(baseline.get("pass_fail") or "") == "pass"
        and bool(baseline.get("evidence_verified"))
        and str(soak.get("pass_fail") or "") == "pass"
        and bool(soak.get("evidence_verified"))
        and soak_met
    ):
        supported_profiles.append(
            {
                "scenario": "enterprise / low concurrency baseline",
                "status": "Supported",
                "notes": "Baseline enterprise evidence and 6h soak both passed.",
            }
        )
    else:
        conditional_profiles.append(
            {
                "scenario": "enterprise / low concurrency baseline",
                "status": "Conditional",
                "notes": "Requires signed baseline evidence plus completed 6h soak.",
            }
        )

    conditional_profiles.append(
        {
            "scenario": "enterprise / bounded concurrency",
            "status": "Conditional" if str(conflict.get("pass_fail") or "") == "pass" else "Not GA",
            "notes": (
                "Conflict/fallback evidence passed under bounded concurrency."
                if str(conflict.get("pass_fail") or "") == "pass"
                else "Missing stable conflict/fallback evidence."
            ),
        }
    )
    conditional_profiles.append(
        {
            "scenario": "enterprise / approval-heavy regulated flow",
            "status": "Conditional" if str(approval.get("pass_fail") or "") == "pass" else "Not GA",
            "notes": (
                "Approval-heavy evidence passed but remains constrained to controlled rollout."
                if str(approval.get("pass_fail") or "") == "pass"
                else "Approval-heavy evidence missing or failed."
            ),
        }
    )
    conditional_profiles.append(
        {
            "scenario": "enterprise / conflict-heavy shared-state flow",
            "status": "Conditional" if str(conflict.get("pass_fail") or "") == "pass" else "Not GA",
            "notes": (
                "Shared-state conflict reject path is verified but remains bounded."
                if str(conflict.get("pass_fail") or "") == "pass"
                else "Shared-state conflict evidence missing or failed."
            ),
        }
    )
    unsupported_profiles.extend(
        [
            {
                "scenario": "restricted",
                "status": "Pilot-only",
                "notes": "Restricted remains a pilot profile and is not part of GA evidence.",
            },
            {
                "scenario": "high-concurrency general multi-agent",
                "status": "Not GA",
                "notes": "General high-concurrency multi-agent execution remains out of scope.",
            },
            {
                "scenario": "arbitrary live-provider environment",
                "status": "Not universally guaranteed",
                "notes": "Target-environment qualification remains mandatory for each deployment.",
            },
        ]
    )

    if not soak_met:
        residual_risks.append(
            f"6h soak threshold not met (observed={int(soak.get('duration_seconds') or 0)}s)"
        )
    optional_24h = workload_map.get("24h_soak_flow")
    optional_24h_published = (
        optional_24h is not None
        and str(optional_24h.get("pass_fail") or "") == "pass"
        and bool(optional_24h.get("evidence_verified"))
        and str(optional_24h.get("replay_verify_status") or "") == "pass"
        and str(optional_24h.get("signing_verify_status") or "") == "pass"
        and int(optional_24h.get("duration_seconds") or 0) >= MIN_EXTENDED_SOAK_SECONDS
        and not optional_24h.get("blocking_findings")
    )
    if not optional_24h_published:
        residual_risks.append("24h soak evidence not yet published")
    residual_risks.extend(
        item
        for item in (
            "managed KMS live drill not yet published",
            "non-developer operator validation not yet published",
        )
        if item not in residual_risks
    )

    operational_findings: list[str] = []
    for item in workloads:
        if not isinstance(item, dict):
            continue
        if item.get("support_bundle_sufficient") is False:
            operational_findings.append(f"{item.get('name')}: support bundle was insufficient")
        if item.get("metrics_snapshot_sufficient") is False:
            operational_findings.append(f"{item.get('name')}: metrics snapshot was insufficient")
        for error in item.get("unclear_errors") or []:
            operational_findings.append(f"{item.get('name')}: unclear_error={error}")
        for gap in item.get("runbook_gaps") or []:
            operational_findings.append(f"{item.get('name')}: runbook_gap={gap}")

    has_blockers = bool(blocking_findings)
    if has_blockers:
        recommended_status = "red"
        go_no_go = "no-go"
        qualification_status = "fail"
    else:
        has_supported_enterprise = any(
            item.get("scenario") == "enterprise / low concurrency baseline"
            and item.get("status") == "Supported"
            for item in supported_profiles
        )
        required_present = not missing_required
        required_pass = all(
            str((workload_map.get(name) or {}).get("pass_fail") or "") == "pass"
            and bool((workload_map.get(name) or {}).get("evidence_verified"))
            for name in REQUIRED_WORKLOADS
        )
        if required_present and required_pass and soak_met and has_supported_enterprise:
            recommended_status = "green"
            go_no_go = "go"
            qualification_status = "pass"
        else:
            recommended_status = "yellow"
            go_no_go = "conditional"
            qualification_status = "partial"

    return {
        "qualification_status": qualification_status,
        "recommended_status": recommended_status,
        "go_no_go": go_no_go,
        "supported_profiles": supported_profiles,
        "conditional_profiles": conditional_profiles,
        "unsupported_profiles": unsupported_profiles,
        "blocking_findings": _unique_strings(blocking_findings),
        "residual_risks": _unique_strings(residual_risks),
        "operational_findings": _unique_strings(operational_findings),
    }


def _run_baseline_enterprise_flow(
    *,
    spec: TeamSpec,
    base_config: RuntimeConfig,
    run_root: Path,
    live_orchestrator_builder: Callable[[RuntimeConfig], Any],
) -> dict[str, Any]:
    name = "baseline_enterprise_flow"
    purpose = (
        "Validate the low-risk enterprise path with approval, replay, "
        "signing, metrics, and support artifacts."
    )
    workload_root = run_root / name
    workload_root.mkdir(parents=True, exist_ok=True)
    config = _qualification_runtime_config(base_config, workload_root, deterministic=False)
    started = datetime.now(UTC)
    blocking_findings: list[str] = []
    notes: list[str] = []
    operational_followups: list[str] = []
    support_bundle_sufficient = False
    metrics_snapshot_sufficient = False
    support_bundle_path = None
    metrics_path = None
    approval_ids: list[str] = []
    positive = _run_terminal_positive_smoke(
        name=name,
        spec=spec,
        config=config,
        orchestrator_builder=live_orchestrator_builder,
        actor="qualification-runner",
    )
    summary = positive["summary"]
    clean_replays = positive["clean_replays"]
    approval_ids.extend(_approval_ids_from_jobs(summary.get("job_ids", []), config=config))
    signing_paths = _collect_audit_paths(summary)
    metrics = collect_metrics_snapshot(config)
    metrics_path = workload_root / "metrics_snapshot.json"
    write_signed_json(
        path=metrics_path,
        artifact="metrics_snapshot",
        data=metrics,
        config=config,
        purpose="metrics-snapshot",
    )
    metrics_verify = load_signed_artifact(path=metrics_path, config=config)
    metrics_snapshot_sufficient = bool(metrics_verify.get("verified")) and bool(
        metrics.get("runtime", {}).get("total_events") is not None
    )

    from imperaos.enterprise.maintenance import export_support_bundle  # noqa: PLC0415

    support_bundle = export_support_bundle(
        config,
        output_path=workload_root / "support_bundle.zip",
    )
    support_bundle_path = support_bundle.get("archive_path")
    bundle_verify = load_signed_artifact(path=support_bundle["manifest_path"], config=config)
    support_bundle_sufficient = bool(bundle_verify.get("verified")) and int(
        support_bundle.get("file_count") or 0
    ) > 0
    signing_paths.extend([str(metrics_path), str(support_bundle.get("manifest_path"))])

    replay_ok = all(bool(item.get("verified")) for item in clean_replays)
    signing_results = [load_signed_artifact(path=path, config=config) for path in signing_paths]
    signing_ok = all(bool(item.get("verified")) for item in signing_results)
    counters = _build_counters(scenario_runs=[summary], clean_replays=clean_replays)
    if not replay_ok:
        blocking_findings.append("replay_verify_failed")
    if not signing_ok:
        blocking_findings.append("signing_verify_failed")
    if counters["approval_reuse_unexpected_success_count"] > 0:
        blocking_findings.append("approval_reuse_unexpected_success")

    ended = datetime.now(UTC)
    task_counts = _task_counts(summary.get("job_ids", []), jobs_root=config.team.artifact_dir)
    return {
        "name": name,
        "purpose": purpose,
        "start_time": _iso(started),
        "end_time": _iso(ended),
        "duration_seconds": max(1, int((ended - started).total_seconds())),
        "execution_mode": "live_provider",
        "required_for_green": True,
        "support_classification": "supported" if not blocking_findings else "unsupported",
        "pass_fail": "pass" if not blocking_findings else "fail",
        "task_count_total": task_counts["total"],
        "task_count_success": task_counts["success"],
        "task_count_failed": task_counts["failed"],
        "failure_class_breakdown": {"none": 1} if not blocking_findings else {"runtime_bug": 1},
        "replay_verify_status": "pass" if replay_ok else "fail",
        "signing_verify_status": "pass" if signing_ok else "fail",
        "approval_latency_summary": _approval_latency_summary(
            config=config,
            approval_ids=approval_ids,
        ),
        "provider_retry_count": counters["retry_count"],
        "stale_approval_count": counters["stale_approval_count"],
        "stale_resume_count": counters["stale_resume_count"],
        "resume_duplicate_suppressed_count": counters["resume_duplicate_suppressed_count"],
        "memory_conflict_count": counters["memory_conflict_count"],
        "serialized_due_to_policy_count": counters["serialized_due_to_policy_count"],
        "fallback_mode_count": counters["fallback_mode_count"],
        "operator_intervention_count": 0,
        "support_bundle_sufficient": support_bundle_sufficient,
        "metrics_snapshot_sufficient": metrics_snapshot_sufficient,
        "unclear_errors": [],
        "runbook_gaps": [],
        "notes": notes,
        "operational_followups": operational_followups,
        "terminal_status": summary.get("terminal_status"),
        "terminal_job_id": summary.get("terminal_job_id"),
        "resume_round_count": summary.get("resume_round_count", 0),
        "approval_rounds": summary.get("approval_rounds", []),
        "artifacts": {
            "workload_root": str(workload_root),
            "job_dirs": summary.get("artifacts", {}),
            "round_job_dirs": summary.get("artifacts", {}).get("round_job_dirs", []),
            "metrics_snapshot": str(metrics_path),
            "support_bundle_archive": str(support_bundle_path or ""),
            "support_bundle_manifest": str(support_bundle.get("manifest_path") or ""),
        },
        "blocking_findings": blocking_findings,
        "residual_risks": [],
        "evidence_verified": (
            replay_ok
            and signing_ok
            and metrics_snapshot_sufficient
            and support_bundle_sufficient
        ),
    }


def _run_approval_heavy_flow(
    *,
    spec: TeamSpec,
    base_config: RuntimeConfig,
    run_root: Path,
    deterministic_orchestrator_builder: Callable[[RuntimeConfig], Any],
) -> dict[str, Any]:
    name = "approval_heavy_flow"
    purpose = "Stress the approval lifecycle, duplicate suppression, and stale snapshot handling."
    workload_root = run_root / name
    workload_root.mkdir(parents=True, exist_ok=True)
    config = _qualification_runtime_config(base_config, workload_root, deterministic=True)
    started = datetime.now(UTC)
    scenario_runs: list[dict[str, Any]] = []
    clean_replays: list[dict[str, Any]] = []
    approval_ids: list[str] = []
    blocking_findings: list[str] = []

    positive_runs: list[dict[str, Any]] = []
    for index in range(1, 4):
        positive = _run_terminal_positive_smoke(
            name=f"{name}-{index}",
            spec=spec,
            config=config,
            orchestrator_builder=deterministic_orchestrator_builder,
            actor="qualification-runner",
        )
        positive_runs.append(positive)
        clean_replays.extend(positive["clean_replays"])
        scenario_runs.append(positive["summary"])
        approval_ids.extend(
            _approval_ids_from_jobs(
                positive["summary"].get("job_ids", []),
                config=config,
            )
        )

    reuse_probe = _run_reuse_probe(
        name=f"{name}-reuse-probe",
        spec=spec,
        config=config,
        orchestrator_builder=deterministic_orchestrator_builder,
        source_job_id=positive_runs[0]["blocked_job_id"],
    )
    scenario_runs.append(reuse_probe)
    stale_probe = _run_stale_snapshot_probe(
        name=f"{name}-stale-probe",
        config=config,
        orchestrator_builder=deterministic_orchestrator_builder,
    )
    scenario_runs.append(stale_probe)

    counters = _build_counters(scenario_runs=scenario_runs, clean_replays=clean_replays)
    signing_paths = []
    for positive in positive_runs:
        signing_paths.extend(_collect_audit_paths(positive["summary"]))
    signing_results = [load_signed_artifact(path=path, config=config) for path in signing_paths]
    signing_ok = all(bool(item.get("verified")) for item in signing_results)
    replay_ok = all(bool(item.get("verified")) for item in clean_replays)

    if not replay_ok:
        blocking_findings.append("replay_verify_failed")
    if not signing_ok:
        blocking_findings.append("signing_verify_failed")
    if reuse_probe.get("status") != "pass":
        blocking_findings.append("approval_reuse_probe_failed")
    if stale_probe.get("status") != "pass":
        blocking_findings.append("stale_snapshot_probe_failed")
    if counters["consumed_without_executed_count"] > 0:
        blocking_findings.append("consumed_without_executed")

    ended = datetime.now(UTC)
    task_counts = _task_counts(
        [job_id for run in scenario_runs for job_id in run.get("job_ids", [])],
        jobs_root=config.team.artifact_dir,
    )
    return {
        "name": name,
        "purpose": purpose,
        "start_time": _iso(started),
        "end_time": _iso(ended),
        "duration_seconds": max(1, int((ended - started).total_seconds())),
        "execution_mode": "deterministic_controlled",
        "required_for_green": True,
        "support_classification": "conditional" if not blocking_findings else "unsupported",
        "pass_fail": "pass" if not blocking_findings else "fail",
        "task_count_total": task_counts["total"],
        "task_count_success": task_counts["success"],
        "task_count_failed": task_counts["failed"],
        "failure_class_breakdown": {
            "approval_reuse_blocked": 1 if reuse_probe.get("status") == "pass" else 0,
            "stale_snapshot": 1 if stale_probe.get("status") == "pass" else 0,
        },
        "replay_verify_status": "pass" if replay_ok else "fail",
        "signing_verify_status": "pass" if signing_ok else "fail",
        "approval_latency_summary": _approval_latency_summary(
            config=config,
            approval_ids=approval_ids,
        ),
        "provider_retry_count": counters["retry_count"],
        "stale_approval_count": counters["stale_approval_count"],
        "stale_resume_count": counters["stale_resume_count"],
        "resume_duplicate_suppressed_count": counters["resume_duplicate_suppressed_count"],
        "memory_conflict_count": counters["memory_conflict_count"],
        "serialized_due_to_policy_count": counters["serialized_due_to_policy_count"],
        "fallback_mode_count": counters["fallback_mode_count"],
        "operator_intervention_count": 0,
        "support_bundle_sufficient": None,
        "metrics_snapshot_sufficient": None,
        "unclear_errors": [],
        "runbook_gaps": [],
        "notes": [],
        "operational_followups": [],
        "terminal_status": None,
        "terminal_job_id": None,
        "resume_round_count": 0,
        "approval_rounds": [],
        "artifacts": {
            "workload_root": str(workload_root),
            "job_ids": [job_id for run in scenario_runs for job_id in run.get("job_ids", [])],
        },
        "blocking_findings": blocking_findings,
        "residual_risks": ["approval-heavy workloads remain controlled-rollout only"],
        "evidence_verified": replay_ok and signing_ok and not blocking_findings,
    }


def _run_conflict_heavy_flow(
    *,
    spec: TeamSpec,
    base_config: RuntimeConfig,
    run_root: Path,
    deterministic_orchestrator_builder: Callable[[RuntimeConfig], Any],
) -> dict[str, Any]:
    name = "conflict_heavy_flow"
    purpose = (
        "Verify shared-state conflict rejection and replay stability "
        "under bounded concurrency."
    )
    workload_root = run_root / name
    workload_root.mkdir(parents=True, exist_ok=True)
    config = _qualification_runtime_config(
        base_config,
        workload_root,
        deterministic=False,
        max_parallel_tasks=2,
    )
    started = datetime.now(UTC)
    blocking_findings: list[str] = []
    request = "Conflict-heavy qualification run for shared state contention."
    base_builder = deterministic_orchestrator_builder

    def conflict_builder(runtime_config: RuntimeConfig):
        delegate = base_builder(runtime_config)
        memory_manager = getattr(delegate, "_memory_manager", None)
        target_version_reader = getattr(memory_manager, "target_version", None)
        if callable(target_version_reader):
            def frozen_target_version(*, scope, team_id, case_id, visibility, memory_target):
                if memory_target == "shared/summary":
                    return 0
                return target_version_reader(
                    scope=scope,
                    team_id=team_id,
                    case_id=case_id,
                    visibility=visibility,
                    memory_target=memory_target,
                )

            memory_manager.target_version = frozen_target_version  # type: ignore[attr-defined]
        return _DelegatingOrchestrator(
            delegate,
            sleep_for_tasks={"task-branch-a", "task-branch-b"},
            delay_seconds=0.05,
            barrier_tasks={"task-branch-a", "task-branch-b"},
            barrier_size=2,
        )

    result = TeamSupervisor(orchestrator=conflict_builder(config), config=config).run(
        spec=spec,
        request=request,
        case_id=f"{name}-case",
        job_id=f"{name}-job",
    )
    replay = replay_job(result.job.job_id, root_dir=config.team.artifact_dir, verify=True)
    events = load_events(result.job.job_id, root_dir=config.team.artifact_dir)
    conflict_events = [
        item
        for item in events
        if str(item.get("event") or "") == "memory_conflict_rejected"
    ]
    target_version = 0
    from imperaos.memory.persistent_store import PersistentMemoryStore  # noqa: PLC0415

    store = PersistentMemoryStore(db_path=config.memory.db_path)
    try:
        target_version = int(
            store.get_target_version(
                scope="case",
                team_id=spec.team.team_id,
                case_id=f"{name}-case",
                visibility="team",
                memory_target="shared/summary",
            )
        )
    finally:
        close_fn = getattr(store, "close", None)
        if callable(close_fn):
            close_fn()
    signing_verify = load_signed_artifact(path=result.audit_envelope_path, config=config)
    if not replay.get("verified"):
        blocking_findings.append("replay_verify_failed")
    if not signing_verify.get("verified"):
        blocking_findings.append("signing_verify_failed")
    if not conflict_events:
        blocking_findings.append("memory_conflict_not_observed")
    if target_version > 1:
        blocking_findings.append("memory_target_version_exceeded_expected_single_commit")

    ended = datetime.now(UTC)
    task_counts = _task_counts([result.job.job_id], jobs_root=config.team.artifact_dir)
    failure_class_breakdown = Counter({"memory_conflict": len(conflict_events)})
    return {
        "name": name,
        "purpose": purpose,
        "start_time": _iso(started),
        "end_time": _iso(ended),
        "duration_seconds": max(1, int((ended - started).total_seconds())),
        "execution_mode": "deterministic_controlled",
        "required_for_green": True,
        "support_classification": "conditional" if not blocking_findings else "unsupported",
        "pass_fail": "pass" if not blocking_findings else "fail",
        "task_count_total": task_counts["total"],
        "task_count_success": task_counts["success"],
        "task_count_failed": task_counts["failed"],
        "failure_class_breakdown": dict(failure_class_breakdown),
        "replay_verify_status": "pass" if replay.get("verified") else "fail",
        "signing_verify_status": "pass" if signing_verify.get("verified") else "fail",
        "approval_latency_summary": {"count": 0},
        "provider_retry_count": 0,
        "stale_approval_count": 0,
        "stale_resume_count": 0,
        "resume_duplicate_suppressed_count": 0,
        "memory_conflict_count": len(conflict_events),
        "serialized_due_to_policy_count": sum(
            1 for item in events if item.get("serialized_due_to_policy")
        ),
        "fallback_mode_count": sum(
            1
            for item in events
            if str(item.get("event") or "") == "fallback_mode_applied"
        ),
        "operator_intervention_count": 0,
        "support_bundle_sufficient": None,
        "metrics_snapshot_sufficient": None,
        "unclear_errors": [],
        "runbook_gaps": [],
        "notes": [f"final_state_version={target_version}"],
        "operational_followups": [],
        "terminal_status": result.job.status.value,
        "terminal_job_id": result.job.job_id,
        "resume_round_count": 0,
        "approval_rounds": [],
        "artifacts": {
            "workload_root": str(workload_root),
            "job_dir": str(Path(config.team.artifact_dir) / result.job.job_id),
            "audit_envelope": result.audit_envelope_path,
        },
        "blocking_findings": blocking_findings,
        "residual_risks": [
            "shared-state conflict workloads remain bounded and reject-on-conflict only"
        ],
        "evidence_verified": (
            bool(replay.get("verified"))
            and bool(signing_verify.get("verified"))
            and not blocking_findings
        ),
    }


def _run_soak_flow(
    *,
    spec: TeamSpec,
    base_config: RuntimeConfig,
    run_root: Path,
    deterministic_orchestrator_builder: Callable[[RuntimeConfig], Any],
    soak_hours: float,
    name: str,
    purpose: str,
    required_for_green: bool,
    support_classification: str,
) -> dict[str, Any]:
    workload_root = run_root / name
    workload_root.mkdir(parents=True, exist_ok=True)
    config = _qualification_runtime_config(base_config, workload_root, deterministic=True)
    soak_seconds = max(1.0, soak_hours * 3600)
    started = datetime.now(UTC)
    deadline = time.monotonic() + soak_seconds
    cycle_seconds = max(0.0, min(300.0, soak_seconds / 24))
    scenario_runs: list[dict[str, Any]] = []
    clean_replays: list[dict[str, Any]] = []
    approval_ids: list[str] = []
    metrics_paths: list[str] = []
    blocking_findings: list[str] = []
    iteration = 0
    total_bytes_before = _dir_size(workload_root)

    while True:
        iteration += 1
        positive = _run_terminal_positive_smoke(
            name=f"{name}-{iteration}",
            spec=spec,
            config=config,
            orchestrator_builder=deterministic_orchestrator_builder,
            actor="qualification-runner",
        )
        scenario_runs.append(positive["summary"])
        clean_replays.extend(positive["clean_replays"])
        approval_ids.extend(
            _approval_ids_from_jobs(
                positive["summary"].get("job_ids", []),
                config=config,
            )
        )

        metrics = collect_metrics_snapshot(config)
        metrics_path = workload_root / f"metrics_snapshot_{iteration}.json"
        write_signed_json(
            path=metrics_path,
            artifact="metrics_snapshot",
            data=metrics,
            config=config,
            purpose="metrics-snapshot",
        )
        metrics_paths.append(str(metrics_path))

        if time.monotonic() >= deadline:
            break
        if cycle_seconds > 0:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(cycle_seconds, remaining))

    ended = datetime.now(UTC)
    counters = _build_counters(scenario_runs=scenario_runs, clean_replays=clean_replays)
    replay_ok = all(bool(item.get("verified")) for item in clean_replays)
    signing_results = [load_signed_artifact(path=path, config=config) for path in metrics_paths]
    for positive in scenario_runs:
        artifacts = positive.get("artifacts") or {}
        for audit_path in [
            artifacts.get("blocked_audit_envelope"),
            artifacts.get("resume_audit_envelope"),
        ]:
            if audit_path:
                signing_results.append(load_signed_artifact(path=audit_path, config=config))
    signing_ok = all(bool(item.get("verified")) for item in signing_results)
    if not replay_ok:
        blocking_findings.append("replay_verify_failed")
    if not signing_ok:
        blocking_findings.append("signing_verify_failed")
    if counters["memory_conflict_count"] > 0:
        blocking_findings.append("memory_conflict_detected")
    total_bytes_after = _dir_size(workload_root)
    executed_duration_seconds = max(1, int((ended - started).total_seconds()))

    metrics_snapshot_sufficient = all(
        bool(item.get("verified")) for item in signing_results[: len(metrics_paths)]
    )
    task_counts = _task_counts(
        [job_id for run in scenario_runs for job_id in run.get("job_ids", [])],
        jobs_root=config.team.artifact_dir,
    )
    return {
        "name": name,
        "purpose": purpose,
        "start_time": _iso(started),
        "end_time": _iso(ended),
        "duration_seconds": executed_duration_seconds,
        "execution_mode": "deterministic_controlled",
        "required_for_green": required_for_green,
        "support_classification": (
            support_classification
            if executed_duration_seconds >= MIN_GREEN_SOAK_SECONDS
            and not blocking_findings
            else "conditional"
        ),
        "pass_fail": "pass" if not blocking_findings else "fail",
        "task_count_total": task_counts["total"],
        "task_count_success": task_counts["success"],
        "task_count_failed": task_counts["failed"],
        "failure_class_breakdown": {"none": 1} if not blocking_findings else {"runtime_bug": 1},
        "replay_verify_status": "pass" if replay_ok else "fail",
        "signing_verify_status": "pass" if signing_ok else "fail",
        "approval_latency_summary": _approval_latency_summary(
            config=config,
            approval_ids=approval_ids,
        ),
        "provider_retry_count": counters["retry_count"],
        "stale_approval_count": counters["stale_approval_count"],
        "stale_resume_count": counters["stale_resume_count"],
        "resume_duplicate_suppressed_count": counters["resume_duplicate_suppressed_count"],
        "memory_conflict_count": counters["memory_conflict_count"],
        "serialized_due_to_policy_count": counters["serialized_due_to_policy_count"],
        "fallback_mode_count": counters["fallback_mode_count"],
        "operator_intervention_count": 0,
        "support_bundle_sufficient": None,
        "metrics_snapshot_sufficient": metrics_snapshot_sufficient,
        "unclear_errors": [],
        "runbook_gaps": [],
        "notes": [
            f"iterations={iteration}",
            f"artifact_growth_bytes={max(total_bytes_after - total_bytes_before, 0)}",
        ],
        "operational_followups": [],
        "terminal_status": "completed" if not blocking_findings else "failed",
        "terminal_job_id": (
            scenario_runs[-1].get("job_ids", [])[-1]
            if scenario_runs and scenario_runs[-1].get("job_ids")
            else None
        ),
        "resume_round_count": 0,
        "approval_rounds": [],
        "artifacts": {
            "workload_root": str(workload_root),
            "metrics_snapshots": metrics_paths,
        },
        "blocking_findings": blocking_findings,
        "residual_risks": [],
        "evidence_verified": replay_ok and signing_ok and metrics_snapshot_sufficient,
    }


def _run_failure_injection_flow(
    *,
    spec: TeamSpec,
    base_config: RuntimeConfig,
    run_root: Path,
    live_orchestrator_builder: Callable[[RuntimeConfig], Any],
    deterministic_orchestrator_builder: Callable[[RuntimeConfig], Any],
) -> dict[str, Any]:
    name = "failure_injection_flow"
    purpose = (
        "Exercise transient provider failures, approval misuse probes, "
        "stale snapshot handling, and restore verification."
    )
    workload_root = run_root / name
    workload_root.mkdir(parents=True, exist_ok=True)
    config = _qualification_runtime_config(base_config, workload_root, deterministic=False)
    started = datetime.now(UTC)
    blocking_findings: list[str] = []
    failure_class_breakdown: Counter[str] = Counter()
    shared_failures: set[str] = set()

    def flaky_builder(runtime_config: RuntimeConfig):
        return _DelegatingOrchestrator(
            live_orchestrator_builder(runtime_config),
            fail_once_tasks={"task-policy": "PROVIDER_TRANSIENT_FAILURE"},
            shared_failures=shared_failures,
        )

    positive = _run_terminal_positive_smoke(
        name=name,
        spec=spec,
        config=config,
        orchestrator_builder=flaky_builder,
        actor="qualification-runner",
    )
    summary = positive["summary"]
    clean_replays = list(positive["clean_replays"])
    scenario_runs = [summary]
    failure_class_breakdown["provider_flake"] += 1

    reuse_probe = _run_reuse_probe(
        name=f"{name}-reuse-probe",
        spec=spec,
        config=config,
        orchestrator_builder=deterministic_orchestrator_builder,
        source_job_id=positive["blocked_job_id"],
    )
    scenario_runs.append(reuse_probe)
    if reuse_probe.get("status") == "pass":
        failure_class_breakdown["approval_reuse_blocked"] += 1

    stale_probe = _run_stale_snapshot_probe(
        name=f"{name}-stale-probe",
        config=config,
        orchestrator_builder=deterministic_orchestrator_builder,
    )
    scenario_runs.append(stale_probe)
    if stale_probe.get("status") == "pass":
        failure_class_breakdown["stale_snapshot"] += 1

    from imperaos.enterprise.maintenance import create_backup, restore_verify  # noqa: PLC0415

    backup = create_backup(config, output_dir=workload_root / "backup")
    backup_manifest_verify = load_signed_artifact(path=backup["manifest_path"], config=config)
    restore_payload = restore_verify(config, backup_dir=backup["backup_dir"])
    if restore_payload.get("verified"):
        failure_class_breakdown["restore_verification"] += 1

    counters = _build_counters(scenario_runs=scenario_runs, clean_replays=clean_replays)
    replay_ok = all(bool(item.get("verified")) for item in clean_replays)
    signing_paths = _collect_audit_paths(summary)
    signing_results = [load_signed_artifact(path=path, config=config) for path in signing_paths]
    signing_results.append(backup_manifest_verify)
    signing_ok = all(bool(item.get("verified")) for item in signing_results)

    if summary.get("status") != "pass":
        blocking_findings.append("positive_failure_injection_smoke_failed")
    if not replay_ok:
        blocking_findings.append("replay_verify_failed")
    if not signing_ok:
        blocking_findings.append("signing_verify_failed")
    if reuse_probe.get("status") != "pass":
        blocking_findings.append("approval_reuse_probe_failed")
    if stale_probe.get("status") != "pass":
        blocking_findings.append("stale_snapshot_probe_failed")
    if not restore_payload.get("verified"):
        blocking_findings.append("restore_verify_failed")

    ended = datetime.now(UTC)
    task_counts = _task_counts(
        [job_id for run in scenario_runs for job_id in run.get("job_ids", [])],
        jobs_root=config.team.artifact_dir,
    )
    return {
        "name": name,
        "purpose": purpose,
        "start_time": _iso(started),
        "end_time": _iso(ended),
        "duration_seconds": max(1, int((ended - started).total_seconds())),
        "execution_mode": "mixed",
        "required_for_green": True,
        "support_classification": "conditional" if not blocking_findings else "unsupported",
        "pass_fail": "pass" if not blocking_findings else "fail",
        "task_count_total": task_counts["total"],
        "task_count_success": task_counts["success"],
        "task_count_failed": task_counts["failed"],
        "failure_class_breakdown": dict(failure_class_breakdown),
        "replay_verify_status": "pass" if replay_ok else "fail",
        "signing_verify_status": "pass" if signing_ok else "fail",
        "approval_latency_summary": _approval_latency_summary(
            config=config,
            approval_ids=_approval_ids_from_jobs(summary.get("job_ids", []), config=config),
        ),
        "provider_retry_count": counters["retry_count"],
        "stale_approval_count": counters["stale_approval_count"],
        "stale_resume_count": counters["stale_resume_count"],
        "resume_duplicate_suppressed_count": counters["resume_duplicate_suppressed_count"],
        "memory_conflict_count": counters["memory_conflict_count"],
        "serialized_due_to_policy_count": counters["serialized_due_to_policy_count"],
        "fallback_mode_count": counters["fallback_mode_count"],
        "operator_intervention_count": 0,
        "support_bundle_sufficient": None,
        "metrics_snapshot_sufficient": None,
        "unclear_errors": [],
        "runbook_gaps": [],
        "notes": [],
        "operational_followups": [],
        "terminal_status": summary.get("terminal_status"),
        "terminal_job_id": summary.get("terminal_job_id"),
        "resume_round_count": summary.get("resume_round_count", 0),
        "approval_rounds": summary.get("approval_rounds", []),
        "artifacts": {
            "workload_root": str(workload_root),
            "backup_manifest": str(backup["manifest_path"]),
            "backup_dir": str(backup["backup_dir"]),
            "round_job_dirs": summary.get("artifacts", {}).get("round_job_dirs", []),
        },
        "blocking_findings": blocking_findings,
        "residual_risks": [],
        "evidence_verified": replay_ok and signing_ok and not blocking_findings,
    }


def _skipped_extended_soak(*, run_root: Path) -> dict[str, Any]:
    return {
        "name": "24h_soak_flow",
        "purpose": "Extended soak evidence for GA RC sign-off.",
        "start_time": None,
        "end_time": None,
        "duration_seconds": 0,
        "execution_mode": "deterministic_controlled",
        "required_for_green": False,
        "support_classification": "conditional",
        "pass_fail": "not_run",
        "task_count_total": 0,
        "task_count_success": 0,
        "task_count_failed": 0,
        "failure_class_breakdown": {},
        "replay_verify_status": "not_run",
        "signing_verify_status": "not_run",
        "approval_latency_summary": {"count": 0},
        "provider_retry_count": 0,
        "stale_approval_count": 0,
        "stale_resume_count": 0,
        "resume_duplicate_suppressed_count": 0,
        "memory_conflict_count": 0,
        "serialized_due_to_policy_count": 0,
        "fallback_mode_count": 0,
        "operator_intervention_count": 0,
        "support_bundle_sufficient": None,
        "metrics_snapshot_sufficient": None,
        "unclear_errors": [],
        "runbook_gaps": [],
        "notes": ["Optional extended soak was not executed in this run."],
        "operational_followups": ["run a signed 24h soak before broader GA sign-off"],
        "terminal_status": None,
        "terminal_job_id": None,
        "resume_round_count": 0,
        "approval_rounds": [],
        "artifacts": {"workload_root": str(run_root / "24h_soak_flow")},
        "blocking_findings": [],
        "residual_risks": ["24h soak evidence not yet published"],
        "evidence_verified": False,
    }


def _publish_extended_soak_evidence(
    workloads: list[dict[str, Any]],
    *,
    run_root: Path,
) -> list[dict[str, Any]]:
    extended_index = next(
        (index for index, item in enumerate(workloads) if item.get("name") == "24h_soak_flow"),
        None,
    )
    if extended_index is None:
        return workloads

    source = next((item for item in workloads if item.get("name") == "soak_6h_flow"), None)
    if source is None:
        return workloads
    source_duration = int(source.get("duration_seconds") or 0)
    if source_duration < MIN_EXTENDED_SOAK_SECONDS:
        return workloads
    source_is_verified = (
        str(source.get("pass_fail") or "") == "pass"
        and bool(source.get("evidence_verified"))
        and str(source.get("replay_verify_status") or "") == "pass"
        and str(source.get("signing_verify_status") or "") == "pass"
        and not source.get("blocking_findings")
    )
    if not source_is_verified:
        return workloads

    source_artifacts = source.get("artifacts") if isinstance(source.get("artifacts"), dict) else {}
    extended_artifacts = {
        **source_artifacts,
        "workload_root": str(run_root / "24h_soak_flow"),
        "source_workload": "soak_6h_flow",
        "source_workload_root": str(source_artifacts.get("workload_root") or ""),
    }
    notes = [
        *[str(item) for item in (source.get("notes") or [])],
        (
            "Published from sustained soak_6h_flow evidence because duration "
            "met the 24h release-candidate threshold."
        ),
    ]
    operational_followups = [
        str(item)
        for item in (source.get("operational_followups") or [])
        if str(item) != "run a signed 24h soak before broader GA sign-off"
    ]
    extended = {
        **source,
        "name": "24h_soak_flow",
        "purpose": "Extended 24h release-candidate soak evidence for GA RC sign-off.",
        "required_for_green": False,
        "support_classification": "conditional",
        "notes": _unique_strings(notes),
        "operational_followups": _unique_strings(operational_followups),
        "artifacts": extended_artifacts,
        "residual_risks": [],
    }

    updated = list(workloads)
    updated[extended_index] = extended
    return updated


def _run_terminal_positive_smoke(
    *,
    name: str,
    spec: TeamSpec,
    config: RuntimeConfig,
    orchestrator_builder: Callable[[RuntimeConfig], Any],
    actor: str,
) -> dict[str, Any]:
    request = (
        "Qualification request: build a controlled enterprise summary with research evidence, "
        "policy constraints, and a final reviewer synthesis."
    )
    case_id = f"{name}-case"
    max_rounds = max(1, int(spec.team.termination_rules.max_tasks or 1))
    initial_job_id = f"{name}-blocked"

    current_result = TeamSupervisor(
        orchestrator=orchestrator_builder(config),
        config=config,
    ).run(
        spec=spec,
        request=request,
        case_id=case_id,
        job_id=initial_job_id,
    )
    current_job_id = initial_job_id
    blocked_job_id = initial_job_id
    all_job_ids: list[str] = [current_job_id]
    all_event_groups: list[list[dict[str, Any]]] = []
    clean_replays: list[dict[str, Any]] = []
    approval_rounds: list[dict[str, Any]] = []
    observed_error_codes: list[str] = []
    all_requested_ids: set[str] = set()
    all_approved_ids: set[str] = set()
    all_executed_ids: set[str] = set()
    all_consumed_ids: set[str] = set()
    seen_approval_sets: set[tuple[str, ...]] = set()
    round_job_dirs: list[str] = []
    resume_round_count = 0

    while True:
        current_status = current_result.job.status.value
        current_events = load_events(current_job_id, root_dir=config.team.artifact_dir)
        current_replay = replay_job(current_job_id, root_dir=config.team.artifact_dir, verify=True)
        all_event_groups.append(current_events)
        clean_replays.append(current_replay)

        if current_status == "completed":
            break
        if current_status == "failed":
            raise QualificationFailure(
                "QUALIFICATION_TERMINAL_FAILED",
                f"{name} reached failed terminal state in job {current_job_id}",
            )
        if current_status != "blocked":
            raise QualificationFailure(
                "QUALIFICATION_UNEXPECTED_TERMINAL_STATUS",
                f"{name} reached unexpected status={current_status} in job {current_job_id}",
            )

        blocked_job_id = blocked_job_id or current_job_id
        governance_runtime = getattr(orchestrator_builder(config), "governance_runtime", None)
        if governance_runtime is None:
            raise QualificationFailure(
                "GOVERNANCE_UNAVAILABLE",
                "enterprise qualification requires governance runtime",
            )

        requested_ids = _requested_approval_ids(current_events)
        all_requested_ids.update(requested_ids)
        approved_ids: list[str] = []
        executed_ids: list[str] = []
        for approval_id in requested_ids:
            decision = governance_runtime.decide_approval(
                approval_id=approval_id,
                approve=True,
                actor=actor,
                reason=f"approved during {name}",
            )
            if decision.error_code is not None:
                observed_error_codes.append(decision.error_code)
                continue
            approved_ids.append(approval_id)
            all_approved_ids.add(approval_id)
            execution = governance_runtime.execute_approval(approval_id=approval_id)
            if execution.error_code is not None:
                observed_error_codes.append(execution.error_code)
                continue
            executed_ids.append(approval_id)
            all_executed_ids.add(approval_id)

        overrides, resolved = _collect_resume_overrides(
            events=current_events,
            governance_runtime=governance_runtime,
        )
        approval_signature = tuple(
            sorted(f"{item['task_id']}::{item['target']}" for item in resolved)
        )
        if not approval_signature:
            raise QualificationFailure(
                "QUALIFICATION_RESUME_NO_PROGRESS",
                f"{name} blocked job {current_job_id} produced no executed approvals for resume",
            )
        if approval_signature in seen_approval_sets:
            raise QualificationFailure(
                "QUALIFICATION_APPROVAL_LOOP",
                f"{name} repeated the same approval set while blocked at job {current_job_id}",
            )
        seen_approval_sets.add(approval_signature)

        resume_round_count += 1
        if resume_round_count > max_rounds:
            raise QualificationFailure(
                "QUALIFICATION_MAX_RESUME_ROUNDS_EXCEEDED",
                f"{name} exceeded max resume rounds ({max_rounds})",
            )

        resume_job_id = (
            f"{name}-resume"
            if resume_round_count == 1
            else f"{name}-resume-{resume_round_count}"
        )
        resume_payload = _resume_from_source_job(
            spec=spec,
            config=config,
            orchestrator_builder=orchestrator_builder,
            source_job_id=current_job_id,
            resume_job_id=resume_job_id,
            source_events=current_events,
            request=request,
            case_id=case_id,
        )
        resumed_result = resume_payload["result"]
        resumed_events = load_events(resume_job_id, root_dir=config.team.artifact_dir)
        try:
            resumed_status = load_job_status(resume_job_id, root_dir=config.team.artifact_dir)
        except FileNotFoundError:
            resumed_status = {}
        consumed_ids = _consumed_approval_ids(resumed_events)
        all_consumed_ids.update(consumed_ids)
        round_job_dirs.extend(
            [
                str(Path(config.team.artifact_dir) / current_job_id),
                str(Path(config.team.artifact_dir) / resume_job_id),
            ]
        )
        approval_rounds.append(
            {
                "round": resume_round_count,
                "source_job_id": current_job_id,
                "resume_job_id": resume_job_id,
                "requested_approval_ids": requested_ids,
                "approved_approval_ids": approved_ids,
                "executed_approval_ids": executed_ids,
                "consumed_approval_ids": consumed_ids,
                "resolved_overrides": resolved,
                "resume_task_ids": list(
                    (
                        resumed_status.get("continuation", {}) or {}
                    ).get("continuation_task_ids", [])
                ),
                "source_status": current_status,
                "resume_status": resumed_result.job.status.value,
                "replay_verified": bool(current_replay.get("verified")),
                "audit_envelope_paths": {
                    "source": str(
                        Path(config.team.artifact_dir)
                        / current_job_id
                        / "audit_envelope.json"
                    ),
                    "resume": resumed_result.audit_envelope_path,
                },
            }
        )
        current_job_id = resume_job_id
        all_job_ids.append(current_job_id)
        current_result = resumed_result

    graph_digest = _graph_digest(all_event_groups)
    terminal_job_id = current_job_id
    return {
        "graph_digest": graph_digest,
        "blocked_job_id": blocked_job_id,
        "terminal_job_id": terminal_job_id,
        "clean_replays": clean_replays,
        "summary": {
            "name": name,
            "status": "pass",
            "job_ids": all_job_ids,
            "graph_digest": graph_digest,
            "expected_failure": False,
            "observed_error_codes": observed_error_codes,
            "replay_verified": all(bool(item.get("verified")) for item in clean_replays),
            "approvals_requested": len(all_requested_ids),
            "approvals_approved": len(all_approved_ids),
            "approvals_executed": len(all_executed_ids),
            "approvals_consumed": len(all_consumed_ids),
            "terminal_status": current_result.job.status.value,
            "terminal_job_id": terminal_job_id,
            "resume_round_count": resume_round_count,
            "approval_rounds": approval_rounds,
            "artifacts": {
                "blocked_job_dir": str(Path(config.team.artifact_dir) / blocked_job_id),
                "resume_job_dir": str(Path(config.team.artifact_dir) / terminal_job_id),
                "blocked_audit_envelope": str(
                    Path(config.team.artifact_dir) / blocked_job_id / "audit_envelope.json"
                ),
                "resume_audit_envelope": str(
                    Path(config.team.artifact_dir) / terminal_job_id / "audit_envelope.json"
                ),
                "initial_job_dir": str(Path(config.team.artifact_dir) / initial_job_id),
                "terminal_job_dir": str(Path(config.team.artifact_dir) / terminal_job_id),
                "round_job_dirs": _unique_strings(round_job_dirs),
                "audit_envelopes": [
                    str(Path(config.team.artifact_dir) / job_id / "audit_envelope.json")
                    for job_id in all_job_ids
                ],
            },
        },
    }


def _derive_resume_spec(
    *,
    spec: TeamSpec,
    source_job_id: str,
    jobs_root: str | Path,
) -> TeamSpec:
    try:
        task_runs = load_task_runs(source_job_id, root_dir=jobs_root).get("tasks", [])
    except FileNotFoundError:
        return spec
    completed_task_ids = {
        str(item.get("task_id") or "")
        for item in task_runs
        if str(item.get("status") or "") == "completed"
    }
    if not completed_task_ids:
        return spec

    payload = spec.model_dump(mode="python")
    remaining_tasks = [
        task
        for task in payload.get("tasks", [])
        if str(task.get("task_id") or "") not in completed_task_ids
    ]
    if not remaining_tasks:
        return spec

    remaining_ids = {str(task.get("task_id") or "") for task in remaining_tasks}
    for task in remaining_tasks:
        task["depends_on"] = [
            dependency
            for dependency in list(task.get("depends_on") or [])
            if dependency in remaining_ids
        ]
    payload["tasks"] = remaining_tasks
    return TeamSpec.model_validate(payload)


def _run_stale_snapshot_probe(
    *,
    name: str,
    config: RuntimeConfig,
    orchestrator_builder: Callable[[RuntimeConfig], Any],
) -> dict[str, Any]:
    probe_spec = _stale_probe_spec()
    request = "Qualification stale snapshot probe request."
    blocked_job_id = f"{name}-blocked"
    resume_job_id = f"{name}-resume"
    case_id = f"{name}-case"

    blocked_orchestrator = orchestrator_builder(config)
    TeamSupervisor(orchestrator=blocked_orchestrator, config=config).run(
        spec=probe_spec,
        request=request,
        case_id=case_id,
        job_id=blocked_job_id,
    )
    blocked_events = load_events(blocked_job_id, root_dir=config.team.artifact_dir)
    blocked_tasks = load_task_runs(blocked_job_id, root_dir=config.team.artifact_dir).get(
        "tasks", []
    )
    dependency_output = ""
    for item in blocked_tasks:
        if str(item.get("task_id") or "") == "task-intake":
            dependency_output = str(
                (item.get("result_payload") or {}).get("output") or ""
            ).strip()
            break
    approval_ids = _requested_approval_ids(blocked_events)
    governance_runtime = getattr(blocked_orchestrator, "governance_runtime", None)
    memory_manager = getattr(blocked_orchestrator, "_memory_manager", None)
    if governance_runtime is None or memory_manager is None or not approval_ids:
        return {
            "name": name,
            "status": "fail",
            "job_ids": [blocked_job_id],
            "graph_digest": None,
            "expected_failure": True,
            "observed_error_codes": ["STALE_PROBE_PREREQUISITES_MISSING"],
            "replay_verified": False,
        }

    for approval_id in approval_ids:
        governance_runtime.decide_approval(
            approval_id=approval_id,
            approve=True,
            actor="qualification-runner",
            reason=f"approved during {name}",
        )
        governance_runtime.execute_approval(approval_id=approval_id)

    store = getattr(memory_manager, "store", None)
    if store is not None:
        store.write_with_status(
            session_id=resume_job_id,
            task_type="plan",
            content=f"User: {request}\nAssistant: {dependency_output or request}",
            salience=1.0,
            metadata={"source": name},
            ttl_days=30,
            scope="case",
            team_id=probe_spec.team.team_id,
            case_id=case_id,
            job_id=resume_job_id,
            producer_agent_id="qualification-mutation",
            producer_role="Intake Agent",
            visibility="team",
        )

    continuation_state = derive_resume_continuation_state(
        spec=probe_spec,
        source_job_id=blocked_job_id,
        root_dir=config.team.artifact_dir,
        source_events=blocked_events,
    )
    task_lineage = dict(continuation_state.get("task_lineage") or {})
    research_lineage = dict(task_lineage.get("task-research") or {})
    if research_lineage:
        research_lineage["lineage_hash"] = "tampered-lineage-hash"
        task_lineage["task-research"] = research_lineage
        continuation_state["task_lineage"] = task_lineage
    resume_result = TeamSupervisor(orchestrator=orchestrator_builder(config), config=config).run(
        spec=probe_spec,
        request=request,
        case_id=case_id,
        job_id=resume_job_id,
        approval_overrides={"task-research": {"task": approval_ids[0]}},
        continuation_state=continuation_state,
    )
    resume_events = load_events(resume_job_id, root_dir=config.team.artifact_dir)
    replay = replay_job(resume_job_id, root_dir=config.team.artifact_dir, verify=True)
    stale_detected = any(
        str(item.get("event") or "") in {"approval_stale", "team.resume.lineage_mismatch"}
        for item in resume_events
    )
    reason_codes = [
        str(item.get("data", {}).get("reason_code") or "")
        for item in resume_events
        if str(item.get("event") or "")
        in {"approval_stale", "team.resume.lineage_mismatch"}
    ]
    return {
        "name": name,
        "status": "pass" if stale_detected else "fail",
        "job_ids": [blocked_job_id, resume_job_id],
        "graph_digest": _graph_digest([blocked_events, resume_events]),
        "expected_failure": True,
        "observed_error_codes": reason_codes or [resume_result.job.status.value],
        "replay_verified": bool(replay.get("verified")),
        "approvals_requested": len(approval_ids),
        "approvals_approved": len(approval_ids),
        "approvals_executed": len(approval_ids),
        "approvals_consumed": 0,
        "artifacts": {
            "blocked_job_dir": str(Path(config.team.artifact_dir) / blocked_job_id),
            "resume_job_dir": str(Path(config.team.artifact_dir) / resume_job_id),
            "resume_audit_envelope": resume_result.audit_envelope_path,
        },
    }


def _stale_probe_spec() -> TeamSpec:
    return TeamSpec.model_validate(
        {
            "version": "1",
            "team": {
                "team_id": "team-enterprise-stale-probe",
                "agents": [
                    {
                        "agent_id": "agent-intake",
                        "role": "Intake Agent",
                        "allowed_task_types": ["plan"],
                        "profile_name": "enterprise",
                        "model_overrides": {},
                        "memory_scope_access": ["case"],
                        "tool_policy_profile": "enterprise",
                        "approval_mode": "auto",
                    },
                    {
                        "agent_id": "agent-research",
                        "role": "Research Analyst Agent",
                        "allowed_task_types": ["research"],
                        "profile_name": "enterprise",
                        "model_overrides": {},
                        "memory_scope_access": ["case"],
                        "tool_policy_profile": "enterprise",
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
                    "input_template": "Produce research notes for {{request}}.",
                },
            ],
        }
    )


def _qualification_runtime_config(
    config: RuntimeConfig,
    root_dir: Path,
    *,
    deterministic: bool,
    max_parallel_tasks: int | None = None,
) -> RuntimeConfig:
    runtime_config = _pilot_runtime_config(config, root_dir, deterministic=deterministic)
    if max_parallel_tasks is not None:
        runtime_config = runtime_config.model_copy(
            update={
                "team": runtime_config.team.model_copy(
                    update={"max_parallel_tasks": max_parallel_tasks}
                ),
                "maintenance": runtime_config.maintenance.model_copy(
                    update={
                        "backup_dir": str(root_dir / "backups"),
                        "restore_dir": str(root_dir / "restores"),
                        "migration_dir": str(root_dir / "migrations"),
                        "support_bundle_dir": str(root_dir / "support"),
                    }
                ),
            }
        )
    else:
        runtime_config = runtime_config.model_copy(
            update={
                "maintenance": runtime_config.maintenance.model_copy(
                    update={
                        "backup_dir": str(root_dir / "backups"),
                        "restore_dir": str(root_dir / "restores"),
                        "migration_dir": str(root_dir / "migrations"),
                        "support_bundle_dir": str(root_dir / "support"),
                    }
                )
            }
        )
    return runtime_config


def _load_team_spec(spec_path: str | Path) -> TeamSpec:
    path = _resolve_repo_path(spec_path)
    suffix = path.suffix.lower()
    if suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
    elif suffix in {".yaml", ".yml"}:
        import yaml

        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    elif suffix == ".toml":
        import tomllib

        with path.open("rb") as file_obj:
            payload = tomllib.load(file_obj)
    else:
        raise QualificationFailure("INVALID_INPUT", f"unsupported spec format: {path}")
    return TeamSpec.model_validate(payload)


def _resolve_repo_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.exists():
        return candidate
    repo_root = Path(__file__).resolve().parents[2]
    resolved = repo_root / candidate
    return resolved


def _validate_spec(spec: TeamSpec, *, config: RuntimeConfig) -> None:
    active_policy_profile = Path(config.governance.policy_path).stem or None
    errors = validate_team_spec(spec, active_policy_profile=active_policy_profile)
    if errors:
        raise QualificationFailure("TEAM_SPEC_INVALID", "; ".join(errors))


def _collect_audit_paths(summary: dict[str, Any]) -> list[str]:
    artifacts = summary.get("artifacts") or {}
    paths = []
    for key in ("blocked_audit_envelope", "resume_audit_envelope", "audit_envelope"):
        value = artifacts.get(key)
        if value:
            paths.append(str(value))
    audit_envelopes = artifacts.get("audit_envelopes")
    if isinstance(audit_envelopes, list):
        for value in audit_envelopes:
            if value:
                paths.append(str(value))
    return paths


def _task_counts(job_ids: list[str], *, jobs_root: str | Path) -> dict[str, int]:
    tasks: list[dict[str, Any]] = []
    for job_id in job_ids:
        tasks.extend(load_task_runs(job_id, root_dir=jobs_root).get("tasks", []))
    failed_statuses = {"failed", "escalated"}
    return {
        "total": len(tasks),
        "success": sum(1 for item in tasks if str(item.get("status") or "") == "completed"),
        "failed": sum(1 for item in tasks if str(item.get("status") or "") in failed_statuses),
    }


def _approval_ids_from_jobs(job_ids: list[str], *, config: RuntimeConfig) -> list[str]:
    values: list[str] = []
    for job_id in job_ids:
        events = load_events(job_id, root_dir=config.team.artifact_dir)
        values.extend(_requested_approval_ids(events))
    return _unique_strings(values)


def _approval_latency_summary(*, config: RuntimeConfig, approval_ids: list[str]) -> dict[str, Any]:
    if not approval_ids:
        return {"count": 0}
    from imperaos.governance.approval_store import ApprovalStore  # noqa: PLC0415

    store = ApprovalStore(config.governance.approval_store_path)
    try:
        decide_latencies: list[float] = []
        execute_latencies: list[float] = []
        total_latencies: list[float] = []
        consume_latencies: list[float] = []
        for approval_id in approval_ids:
            ticket = store.get(approval_id)
            if ticket is None:
                continue
            if ticket.decided_at is not None:
                decide_latencies.append((ticket.decided_at - ticket.created_at).total_seconds())
            if ticket.executed_at is not None:
                anchor = ticket.decided_at or ticket.created_at
                execute_latencies.append((ticket.executed_at - anchor).total_seconds())
                total_latencies.append((ticket.executed_at - ticket.created_at).total_seconds())
            if ticket.consumed_at is not None and ticket.executed_at is not None:
                consume_latencies.append((ticket.consumed_at - ticket.executed_at).total_seconds())
                total_latencies.append((ticket.consumed_at - ticket.created_at).total_seconds())
        return {
            "count": len(approval_ids),
            "decide_seconds": _latency_stats(decide_latencies),
            "execute_seconds": _latency_stats(execute_latencies),
            "consume_seconds": _latency_stats(consume_latencies),
            "total_seconds": _latency_stats(total_latencies),
        }
    finally:
        close_fn = getattr(store, "close", None)
        if callable(close_fn):
            close_fn()


def _latency_stats(values: list[float]) -> dict[str, float] | None:
    if not values:
        return None
    return {
        "min": round(min(values), 4),
        "max": round(max(values), 4),
        "avg": round(sum(values) / len(values), 4),
    }


def _dir_size(root: Path) -> int:
    if not root.exists():
        return 0
    return sum(item.stat().st_size for item in root.rglob("*") if item.is_file())


def _unique_strings(values: list[str]) -> list[str]:
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


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")
