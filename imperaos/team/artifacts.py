from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from imperaos.contracts.version import OPERATOR_PANEL_CONTRACT_VERSION
from imperaos.enterprise.signing import build_integrity, canonical_payload_hash
from imperaos.runtime.config import RuntimeConfig
from imperaos.runtime.paths import TEAM_ARTIFACT_ROOT
from imperaos.team.models import (
    AuditEnvelope,
    AuditIntegrity,
    HandoffRecord,
    JobRun,
    TaskRun,
    TeamEvent,
)

AUDIT_ENVELOPE_CONTRACT_VERSION = "2.0"


@dataclass(slots=True)
class TeamArtifactPaths:
    root_dir: Path
    job_dir: Path
    status_path: Path
    events_path: Path
    tasks_path: Path
    handoffs_path: Path
    envelope_path: Path


def ensure_team_artifact_paths(
    *,
    job_id: str,
    root_dir: str | Path = TEAM_ARTIFACT_ROOT,
) -> TeamArtifactPaths:
    base = Path(root_dir)
    job_dir = base / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    return TeamArtifactPaths(
        root_dir=base,
        job_dir=job_dir,
        status_path=job_dir / "status.json",
        events_path=job_dir / "events.jsonl",
        tasks_path=job_dir / "tasks.json",
        handoffs_path=job_dir / "handoffs.json",
        envelope_path=job_dir / "audit_envelope.json",
    )


def write_event(paths: TeamArtifactPaths, event: TeamEvent) -> None:
    with paths.events_path.open("a", encoding="utf-8") as file_obj:
        file_obj.write(json.dumps(event.model_dump(mode="json"), ensure_ascii=False) + "\n")


def write_status(paths: TeamArtifactPaths, payload: dict[str, Any]) -> None:
    _atomic_write_text(
        paths.status_path,
        json.dumps(
            {"contract_version": OPERATOR_PANEL_CONTRACT_VERSION, **payload},
            indent=2,
            ensure_ascii=False,
        ),
    )


def write_task_runs(paths: TeamArtifactPaths, tasks: list[TaskRun]) -> None:
    payload = {
        "contract_version": OPERATOR_PANEL_CONTRACT_VERSION,
        "generated_at": _now_iso(),
        "tasks": [item.model_dump(mode="json") for item in tasks],
    }
    paths.tasks_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def write_handoffs(paths: TeamArtifactPaths, handoffs: list[HandoffRecord]) -> None:
    payload = {
        "contract_version": OPERATOR_PANEL_CONTRACT_VERSION,
        "generated_at": _now_iso(),
        "handoffs": [item.model_dump(mode="json") for item in handoffs],
    }
    paths.handoffs_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def write_audit_envelope(
    *,
    paths: TeamArtifactPaths,
    job: JobRun,
    tasks: list[TaskRun],
    events: list[TeamEvent],
    handoffs: list[HandoffRecord],
    policy_bundle_id: str,
    policy_bundle_hash: str,
    runtime_config_hash: str,
    config: RuntimeConfig | None = None,
) -> str:
    started_at = min((item.timestamp for item in events), default=job.created_at)
    finished_at = max(
        (item.timestamp for item in events),
        default=job.finished_at or datetime.now(UTC),
    )
    consistency = _consistency_report(tasks=tasks, events=events, handoffs=handoffs)
    trace_refs = sorted(
        {
            str(item.result_payload.get("trace_id"))
            for item in tasks
            if item.result_payload.get("trace_id")
        }
    )

    decision_chain = []
    approvals = []
    tool_calls = []
    for event in events:
        if event.event in {
            "task_created",
            "task_assigned",
            "handoff",
            "approval_requested",
            "approval_resolved",
            "approval_stale",
            "memory_write_attempt",
            "memory_read_attempt",
            "memory_read_succeeded",
            "memory_read_blocked",
            "memory_write_succeeded",
            "memory_write_blocked",
            "memory_conflict_detected",
            "memory_conflict_rejected",
            "task_retry",
            "task_started",
            "task_completed",
            "task_blocked",
            "task_failed",
            "task_escalated",
            "approval_consumed",
            "resume_duplicate_suppressed",
            "team.resume.frontier_loaded",
            "team.resume.continuation_selected",
            "team.resume.lineage_mismatch",
            "team.resume.snapshot_drift",
            "team.resume.approval_carry_forwarded",
            "team.resume.invalid_frontier",
            "team.resume.completed",
            "fallback_mode_applied",
            "fallback_mode_released",
            "safe_abort",
            "team_final",
        }:
            decision_chain.append(
                {
                    "event_id": event.event_id,
                    "event_seq": event.event_seq,
                    "timestamp": event.timestamp.isoformat(),
                    "event": event.event,
                    "task_id": event.task_id,
                    "task_run_id": event.task_run_id,
                    "reason_code": event.data.get("reason_code"),
                    "approval_id": event.approval_id,
                    "trace_id": event.trace_id,
                    "causal_ref": event.causal_ref,
                    "payload_hash": event.payload_hash,
                    "branch_id": event.branch_id,
                    "branch_parent": event.branch_parent,
                    "snapshot_hash": event.snapshot_hash,
                    "resolved_memory_fingerprint": event.resolved_memory_fingerprint,
                    "memory_target": event.memory_target,
                    "expected_state_version": event.expected_state_version,
                    "committed_state_version": event.committed_state_version,
                    "resume_token_ref": event.resume_token_ref,
                    "conflict_detected": event.conflict_detected,
                    "conflict_resolution": event.conflict_resolution,
                    "fallback_mode_applied": event.fallback_mode_applied,
                    "serialized_due_to_policy": event.serialized_due_to_policy,
                    "data": event.data,
                }
            )
        if event.event in {"approval_requested", "approval_resolved", "approval_consumed"}:
            approvals.append(
                {
                    "event_id": event.event_id,
                    "event_seq": event.event_seq,
                    "timestamp": event.timestamp.isoformat(),
                    "task_id": event.task_id,
                    "task_run_id": event.task_run_id,
                    "approval_id": event.data.get("approval_id"),
                    "status": event.data.get("status") or event.status_after,
                    "target": event.data.get("target"),
                }
            )
        if event.event == "tool_call":
            tool_calls.append(event.data)

    handoff_payload = [item.model_dump(mode="json") for item in handoffs]
    redaction_report = {
        "handoff_redacted_count": sum(1 for item in handoffs if item.redaction_applied),
        "task_count": len(tasks),
    }

    prev_hash = _read_prev_chain_hash(paths.root_dir)
    envelope_wo_integrity = {
        "contract_version": AUDIT_ENVELOPE_CONTRACT_VERSION,
        "envelope_version": "3",
        "event_schema_version": "3",
        "handoff_schema_version": "3",
        "job_id": job.job_id,
        "case_id": job.case_id,
        "team_id": job.team_id,
        "policy_bundle_id": policy_bundle_id,
        "policy_bundle_hash": policy_bundle_hash,
        "runtime_config_hash": runtime_config_hash,
        "started_at": started_at,
        "finished_at": finished_at,
        "event_count": len(events),
        "trace_refs": trace_refs,
        "consistency": consistency,
        "decision_chain": decision_chain,
        "approvals": approvals,
        "tool_calls": tool_calls,
        "handoffs": handoff_payload,
        "redaction_report": redaction_report,
    }
    integrity_payload = build_integrity(
        payload=envelope_wo_integrity,
        config=config,
        purpose="audit-envelope",
        prev_hash=prev_hash,
    )
    envelope = AuditEnvelope(
        contract_version=AUDIT_ENVELOPE_CONTRACT_VERSION,
        envelope_version="3",
        event_schema_version="3",
        handoff_schema_version="3",
        job_id=job.job_id,
        case_id=job.case_id,
        team_id=job.team_id,
        policy_bundle_id=policy_bundle_id,
        policy_bundle_hash=policy_bundle_hash,
        runtime_config_hash=runtime_config_hash,
        started_at=started_at,
        finished_at=finished_at,
        event_count=len(events),
        trace_refs=trace_refs,
        consistency=consistency,
        decision_chain=decision_chain,
        approvals=approvals,
        tool_calls=tool_calls,
        handoffs=handoff_payload,
        redaction_report=redaction_report,
        integrity=AuditIntegrity.model_validate(integrity_payload),
    )
    paths.envelope_path.write_text(
        json.dumps(envelope.model_dump(mode="json"), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    _write_chain_hash(paths.root_dir, envelope.integrity.hash)
    return str(paths.envelope_path)


def _sha256_payload(payload: dict[str, Any], prev_hash: str | None) -> str:
    return canonical_payload_hash(payload, prev_hash=prev_hash)


def _chain_head_path(root_dir: Path) -> Path:
    chain_dir = root_dir.parent
    chain_dir.mkdir(parents=True, exist_ok=True)
    return chain_dir / "chain_head.txt"


def _read_prev_chain_hash(root_dir: Path) -> str | None:
    path = _chain_head_path(root_dir)
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8").strip()
    return text or None


def _write_chain_hash(root_dir: Path, value: str) -> None:
    _chain_head_path(root_dir).write_text(value, encoding="utf-8")


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    tmp_path.write_text(text, encoding="utf-8")
    try:
        for attempt in range(20):
            try:
                tmp_path.replace(path)
                return
            except PermissionError:
                if attempt == 19:
                    raise
                time.sleep(0.05)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _consistency_report(
    *,
    tasks: list[TaskRun],
    events: list[TeamEvent],
    handoffs: list[HandoffRecord],
) -> dict[str, Any]:
    errors: list[str] = []
    seqs = [item.event_seq for item in events]
    duplicate_event_seq_count = len(seqs) - len(set(seqs))
    expected = list(range(1, len(events) + 1))
    non_contiguous_event_seq_count = 0
    if seqs != expected:
        errors.append("event sequence is not contiguous from 1..N")
        non_contiguous_event_seq_count = 1

    missing_causal_ref_count = 0
    seen_event_ids: set[str] = set()
    allowed_external_causal_refs = _external_causal_refs(events)
    for event in events:
        if _event_requires_causal_ref(event.event):
            causal_ref = str(event.causal_ref or "").strip()
            if not causal_ref or (
                causal_ref not in seen_event_ids
                and causal_ref not in allowed_external_causal_refs
            ):
                errors.append(
                    f"event '{event.event_id}' missing valid causal_ref for '{event.event}'"
                )
                missing_causal_ref_count += 1
        seen_event_ids.add(event.event_id)

    event_handoff_ids = {
        str(item.data.get("handoff_id"))
        for item in events
        if item.event == "handoff" and item.data.get("handoff_id")
    }
    for handoff in handoffs:
        if handoff.handoff_id not in event_handoff_ids:
            errors.append(f"handoff '{handoff.handoff_id}' missing matching handoff event")

    started = {
        item.task_run_id
        for item in events
        if item.event == "task_started" and item.task_run_id is not None
    }
    terminal = {
        item.task_run_id
        for item in events
        if item.event in {"task_completed", "task_blocked", "task_failed", "task_escalated"}
        and item.task_run_id is not None
    }
    missing_terminal_task_count = 0
    for task in tasks:
        if task.started_at is not None and task.task_run_id not in started:
            errors.append(f"task_run '{task.task_run_id}' missing task_started event")
        if task.task_run_id not in terminal:
            errors.append(f"task_run '{task.task_run_id}' missing terminal event")
            missing_terminal_task_count += 1

    return {
        "verified": not errors,
        "errors": errors,
        "task_run_count": len(tasks),
        "handoff_count": len(handoffs),
        "event_count": len(events),
        "duplicate_event_seq_count": duplicate_event_seq_count,
        "non_contiguous_event_seq_count": non_contiguous_event_seq_count,
        "missing_causal_ref_count": missing_causal_ref_count,
        "missing_terminal_task_count": missing_terminal_task_count,
        "stale_approval_count": sum(1 for item in events if item.event == "approval_stale"),
        "stale_resume_count": sum(
            1
            for item in events
            if item.event in {"approval_stale", "resume_duplicate_suppressed"}
        ),
        "resume_duplicate_suppressed_count": sum(
            1 for item in events if item.event == "resume_duplicate_suppressed"
        ),
        "resume_frontier_count": sum(
            1 for item in events if item.event == "team.resume.frontier_loaded"
        ),
        "resume_root_restart_count": sum(
            int(item.data.get("resume_root_restart_count") or 0)
            for item in events
            if item.event == "team.resume.continuation_selected"
        ),
        "approval_carry_forward_count": sum(
            1 for item in events if item.event == "team.resume.approval_carry_forwarded"
        ),
        "resume_lineage_mismatch_count": sum(
            1 for item in events if item.event == "team.resume.lineage_mismatch"
        ),
        "invalid_frontier_count": sum(
            1 for item in events if item.event == "team.resume.invalid_frontier"
        ),
        "memory_conflict_count": sum(
            1 for item in events if item.event == "memory_conflict_rejected"
        ),
        "serialized_due_to_policy_count": sum(
            1 for item in events if item.serialized_due_to_policy
        ),
        "fallback_mode_count": sum(
            1 for item in events if item.event == "fallback_mode_applied"
        ),
    }


def _event_requires_causal_ref(event_name: str) -> bool:
    return event_name in {
        "task_assigned",
        "handoff",
        "team.resume.continuation_selected",
        "team.resume.lineage_mismatch",
        "team.resume.snapshot_drift",
        "team.resume.approval_carry_forwarded",
        "approval_requested",
        "approval_consumed",
        "memory_read_attempt",
        "memory_read_succeeded",
        "memory_read_blocked",
        "memory_write_attempt",
        "memory_write_succeeded",
        "memory_write_blocked",
        "task_retry",
        "task_started",
        "task_completed",
        "task_blocked",
        "task_failed",
        "task_escalated",
        "safe_abort",
    }


def _external_causal_refs(events: list[TeamEvent]) -> set[str]:
    refs: set[str] = set()
    for event in events:
        if event.event != "team.resume.continuation_selected":
            continue
        upstream_nodes = (event.data or {}).get("upstream_completed_nodes") or []
        if not isinstance(upstream_nodes, list):
            continue
        for item in upstream_nodes:
            if not isinstance(item, dict):
                continue
            terminal_event_id = str(item.get("terminal_event_id") or "").strip()
            if terminal_event_id:
                refs.add(terminal_event_id)
    return refs
