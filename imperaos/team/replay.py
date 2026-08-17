from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from imperaos.runtime.paths import TEAM_ARTIFACT_ROOT


def _job_dir(job_id: str, root_dir: str | Path = TEAM_ARTIFACT_ROOT) -> Path:
    return Path(root_dir) / job_id


def load_job_status(job_id: str, root_dir: str | Path = TEAM_ARTIFACT_ROOT) -> dict[str, Any]:
    path = _job_dir(job_id, root_dir) / "status.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_events(job_id: str, root_dir: str | Path = TEAM_ARTIFACT_ROOT) -> list[dict[str, Any]]:
    path = _job_dir(job_id, root_dir) / "events.jsonl"
    if not path.exists():
        return []
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [json.loads(line) for line in lines]


def load_audit_envelope(
    job_id: str,
    root_dir: str | Path = TEAM_ARTIFACT_ROOT,
) -> dict[str, Any]:
    path = _job_dir(job_id, root_dir) / "audit_envelope.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_task_runs(job_id: str, root_dir: str | Path = TEAM_ARTIFACT_ROOT) -> dict[str, Any]:
    path = _job_dir(job_id, root_dir) / "tasks.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_handoffs(job_id: str, root_dir: str | Path = TEAM_ARTIFACT_ROOT) -> dict[str, Any]:
    path = _job_dir(job_id, root_dir) / "handoffs.json"
    return json.loads(path.read_text(encoding="utf-8"))


def replay_job(
    job_id: str,
    root_dir: str | Path = TEAM_ARTIFACT_ROOT,
    *,
    verify: bool = True,
) -> dict[str, Any]:
    status = load_job_status(job_id, root_dir)
    events = load_events(job_id, root_dir)
    envelope = load_audit_envelope(job_id, root_dir)
    tasks = load_task_runs(job_id, root_dir).get("tasks", [])
    handoffs = load_handoffs(job_id, root_dir).get("handoffs", [])

    task_events = [
        item
        for item in events
        if item.get("event")
        in {
            "task_created",
            "task_assigned",
            "task_started",
            "task_completed",
            "task_blocked",
            "task_failed",
            "task_escalated",
            "team.resume.frontier_loaded",
            "team.resume.continuation_selected",
            "team.resume.completed",
        }
    ]
    handoff_events = [item for item in events if item.get("event") == "handoff"]
    approval_events = [
        item
        for item in events
        if item.get("event")
        in {
            "approval_requested",
            "approval_resolved",
            "approval_consumed",
            "approval_stale",
            "resume_duplicate_suppressed",
            "team.resume.lineage_mismatch",
            "team.resume.snapshot_drift",
            "team.resume.approval_carry_forwarded",
        }
    ]
    verification = _verify_replay(events=events, envelope=envelope, tasks=tasks, handoffs=handoffs)

    payload = {
        "job_id": job_id,
        "status": status.get("job", {}).get("status"),
        "team_id": status.get("job", {}).get("team_id"),
        "case_id": status.get("job", {}).get("case_id"),
        "final_output": status.get("job", {}).get("final_output"),
        "event_count": len(events),
        "task_event_count": len(task_events),
        "handoff_event_count": len(handoff_events),
        "approval_event_count": len(approval_events),
        "decision_count": len(envelope.get("decision_chain", [])),
        "integrity": envelope.get("integrity", {}),
        "trace_refs": envelope.get("trace_refs", []),
        "approvals": approval_events,
        "tasks": tasks,
        "handoffs": handoffs,
    }
    if verify:
        payload["verified"] = verification["verified"]
        payload["errors"] = verification["errors"]
        payload["checks"] = verification["checks"]
        payload["consistency"] = verification["consistency"]
    return payload


def _verify_replay(
    *,
    events: list[dict[str, Any]],
    envelope: dict[str, Any],
    tasks: list[dict[str, Any]],
    handoffs: list[dict[str, Any]],
) -> dict[str, Any]:
    errors: list[str] = []
    seqs = [int(item.get("event_seq") or 0) for item in events]
    duplicate_event_seq_count = len(seqs) - len(set(seqs))
    non_contiguous_event_seq_count = 0
    if seqs != list(range(1, len(events) + 1)):
        errors.append("event_seq mismatch")
        non_contiguous_event_seq_count = 1

    envelope_consistency = envelope.get("consistency", {})
    if envelope.get("event_count") != len(events):
        errors.append("envelope event_count mismatch")
    if not envelope_consistency.get("verified", False):
        errors.extend(str(item) for item in envelope_consistency.get("errors", []))

    missing_causal_ref_count = 0
    seen_event_ids: set[str] = set()
    allowed_external_causal_refs = _external_causal_refs(events)
    handoff_hash_by_id: dict[str, str] = {
        str(item.get("handoff_id")): str(item.get("payload_hash") or "")
        for item in handoffs
        if item.get("handoff_id")
    }
    handoff_hash_by_approval_id: dict[str, str] = {
        str(item.get("approval_id")): str(item.get("payload_hash") or "")
        for item in handoffs
        if item.get("approval_id")
    }
    payload_hash_mismatch_count = 0
    resume_token_use_count: dict[str, int] = {}
    memory_versions_by_target: dict[str, int] = {}
    memory_version_conflict_count = 0
    for item in events:
        event_name = str(item.get("event") or "")
        event_id = str(item.get("event_id") or "")
        causal_ref = str(item.get("causal_ref") or "").strip()
        if _event_requires_causal_ref(event_name) and (
            not causal_ref
            or (
                causal_ref not in seen_event_ids
                and causal_ref not in allowed_external_causal_refs
            )
        ):
            errors.append(f"missing causal_ref for event_id={event_id}")
            missing_causal_ref_count += 1

        payload_hash = str(item.get("payload_hash") or "")
        data = item.get("data")
        if isinstance(data, dict):
            if event_name == "handoff":
                handoff_id = str(data.get("handoff_id") or "")
                expected_hash = handoff_hash_by_id.get(handoff_id)
                if expected_hash and payload_hash and payload_hash != expected_hash:
                    errors.append(f"handoff payload hash mismatch for {handoff_id}")
                    payload_hash_mismatch_count += 1
            elif event_name in {"approval_requested", "approval_consumed"}:
                if str(data.get("target") or "") == "handoff":
                    approval_id = str(data.get("approval_id") or item.get("approval_id") or "")
                    expected_hash = handoff_hash_by_approval_id.get(approval_id)
                    if expected_hash and payload_hash and payload_hash != expected_hash:
                        errors.append(f"approval payload hash mismatch for {approval_id}")
                        payload_hash_mismatch_count += 1
                else:
                    expected_hash = _payload_hash(data)
                    if payload_hash and payload_hash != expected_hash:
                        errors.append(f"payload hash mismatch for event_id={event_id}")
                        payload_hash_mismatch_count += 1
            elif payload_hash:
                expected_hash = _payload_hash(data)
                if payload_hash != expected_hash:
                    errors.append(f"payload hash mismatch for event_id={event_id}")
                    payload_hash_mismatch_count += 1
        resume_token_ref = str(item.get("resume_token_ref") or "").strip()
        if resume_token_ref and event_name in {"task_started", "approval_consumed"}:
            resume_token_use_count[resume_token_ref] = (
                resume_token_use_count.get(resume_token_ref, 0) + 1
            )
        memory_target = str(item.get("memory_target") or "").strip()
        if memory_target and item.get("committed_state_version") is not None:
            committed_version = int(item.get("committed_state_version") or 0)
            previous_version = memory_versions_by_target.get(memory_target, 0)
            if committed_version < previous_version:
                errors.append(f"memory version regressed for target={memory_target}")
                memory_version_conflict_count += 1
            memory_versions_by_target[memory_target] = committed_version
        seen_event_ids.add(event_id)

    for resume_token_ref, count in resume_token_use_count.items():
        if count > 2:
            errors.append(f"resume token reused excessively: {resume_token_ref}")

    terminal_event_ids = {
        item.get("task_run_id")
        for item in events
        if item.get("event") in {"task_completed", "task_blocked", "task_failed", "task_escalated"}
    }
    missing_terminal_task_count = 0
    for task in tasks:
        if task.get("task_run_id") not in terminal_event_ids:
            errors.append(f"missing terminal event for task_run_id={task.get('task_run_id')}")
            missing_terminal_task_count += 1

    event_handoff_ids = {
        str(item.get("data", {}).get("handoff_id"))
        for item in events
        if item.get("event") == "handoff"
    }
    for handoff in handoffs:
        if str(handoff.get("handoff_id")) not in event_handoff_ids:
            errors.append(f"missing replay handoff event for {handoff.get('handoff_id')}")

    return {
        "verified": not errors,
        "errors": errors,
        "checks": {
            "event_count": len(events),
            "task_count": len(tasks),
            "handoff_count": len(handoffs),
        },
        "consistency": {
            "duplicate_event_seq_count": duplicate_event_seq_count,
            "non_contiguous_event_seq_count": non_contiguous_event_seq_count,
            "missing_causal_ref_count": missing_causal_ref_count,
            "missing_terminal_task_count": missing_terminal_task_count,
            "payload_hash_mismatch_count": payload_hash_mismatch_count,
            "memory_version_conflict_count": memory_version_conflict_count,
            "resume_token_count": len(resume_token_use_count),
            "resume_frontier_count": sum(
                1
                for item in events
                if str(item.get("event") or "") == "team.resume.frontier_loaded"
            ),
            "resume_root_restart_count": sum(
                int((item.get("data") or {}).get("resume_root_restart_count") or 0)
                for item in events
                if str(item.get("event") or "") == "team.resume.continuation_selected"
            ),
            "approval_carry_forward_count": sum(
                1
                for item in events
                if str(item.get("event") or "") == "team.resume.approval_carry_forwarded"
            ),
            "resume_lineage_mismatch_count": sum(
                1
                for item in events
                if str(item.get("event") or "") == "team.resume.lineage_mismatch"
            ),
            "invalid_frontier_count": sum(
                1
                for item in events
                if str(item.get("event") or "") == "team.resume.invalid_frontier"
            ),
        },
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
        "approval_stale",
        "resume_duplicate_suppressed",
        "approval_consumed",
        "memory_read_attempt",
        "memory_read_succeeded",
        "memory_read_blocked",
        "memory_write_attempt",
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
        "fallback_mode_applied",
        "fallback_mode_released",
        "safe_abort",
    }


def _payload_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _external_causal_refs(events: list[dict[str, Any]]) -> set[str]:
    refs: set[str] = set()
    for item in events:
        if str(item.get("event") or "") != "team.resume.continuation_selected":
            continue
        data = item.get("data")
        if not isinstance(data, dict):
            continue
        upstream_nodes = data.get("upstream_completed_nodes") or []
        if not isinstance(upstream_nodes, list):
            continue
        for upstream in upstream_nodes:
            if not isinstance(upstream, dict):
                continue
            terminal_event_id = str(upstream.get("terminal_event_id") or "").strip()
            if terminal_event_id:
                refs.add(terminal_event_id)
    return refs
