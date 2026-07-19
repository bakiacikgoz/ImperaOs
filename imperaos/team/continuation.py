from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from imperaos.team.models import TaskDefinition, TeamSpec
from imperaos.team.replay import load_events, load_job_status


class ResumeContinuationError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def derive_resume_continuation_state(
    *,
    spec: TeamSpec,
    source_job_id: str,
    root_dir: str | Path,
    source_status: dict[str, Any] | None = None,
    source_events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    status_payload = source_status or load_job_status(source_job_id, root_dir=root_dir)
    events = source_events or load_events(source_job_id, root_dir=root_dir)
    source_job = status_payload.get("job") or {}
    source_status_value = str(source_job.get("status") or "").strip().lower()
    if source_status_value != "blocked":
        raise ResumeContinuationError(
            "INVALID_CONTINUATION_FRONTIER",
            f"job {source_job_id} is not blocked; got status={source_status_value or 'unknown'}",
        )

    tasks_payload = list(status_payload.get("tasks") or [])
    if not tasks_payload:
        raise ResumeContinuationError(
            "INVALID_CONTINUATION_FRONTIER",
            f"job {source_job_id} has no task payload for continuation",
        )

    full_tasks = list(spec.tasks)
    tasks_by_id = {item.task_id: item for item in full_tasks}
    inherited = status_payload.get("continuation")
    inherited = inherited if isinstance(inherited, dict) else {}
    root_run_id = str(inherited.get("root_run_id") or source_job_id)
    parent_generation = int(inherited.get("checkpoint_generation") or 0)
    parent_index = int(inherited.get("continuation_index") or 0)
    checkpoint_generation = parent_generation + 1
    continuation_index = parent_index + 1

    task_lineage: dict[str, dict[str, Any]] = {}
    completed_task_ids: set[str] = set()
    blocked_task_ids: list[str] = []
    completed_outputs: dict[str, dict[str, Any]] = {}
    upstream_completed_nodes: list[dict[str, Any]] = []

    for item in tasks_payload:
        task_id = str(item.get("task_id") or "").strip()
        if not task_id:
            continue
        task_run_id = str(item.get("task_run_id") or "").strip()
        result_payload = item.get("result_payload") or {}
        branch_id = str(
            result_payload.get("branch_id")
            or _fallback_branch_id(task_id=task_id, tasks_by_id=tasks_by_id)
        )
        branch_parent = result_payload.get("branch_parent")
        terminal_event_id = str(result_payload.get("terminal_event_id") or "").strip() or None
        lineage_hash = _lineage_hash(
            root_run_id=root_run_id,
            logical_task_id=task_id,
            branch_id=branch_id,
            branch_parent=branch_parent,
        )
        lineage_entry = {
            "root_run_id": root_run_id,
            "logical_task_id": task_id,
            "task_run_id": task_run_id,
            "branch_id": branch_id,
            "branch_parent": branch_parent,
            "lineage_hash": lineage_hash,
            "continuation_index": continuation_index,
            "checkpoint_generation": checkpoint_generation,
            "terminal_event_id": terminal_event_id,
            "task_attempt": int(item.get("task_attempt") or item.get("attempt_count") or 1),
        }
        task_lineage[task_id] = lineage_entry

        task_status = str(item.get("status") or "").strip().lower()
        if task_status == "completed":
            completed_task_ids.add(task_id)
            output = str(result_payload.get("output") or "")
            if output:
                completed_outputs[task_id] = {
                    "output": output,
                    "trace_id": result_payload.get("trace_id"),
                    "agent_id": result_payload.get("agent_id"),
                    "task_run_id": task_run_id,
                }
            upstream_completed_nodes.append(
                {
                    "task_id": task_id,
                    "task_run_id": task_run_id,
                    "lineage_hash": lineage_hash,
                    "terminal_event_id": terminal_event_id,
                }
            )
        elif task_status in {"blocked", "escalated"}:
            blocked_task_ids.append(task_id)

    if not blocked_task_ids:
        raise ResumeContinuationError(
            "INVALID_CONTINUATION_FRONTIER",
            f"job {source_job_id} has no blocked frontier nodes",
        )

    continuation_task_ids = (
        _continuation_task_ids(
            tasks=full_tasks,
            blocked_task_ids=blocked_task_ids,
            completed_task_ids=completed_task_ids,
        )
        if full_tasks
        else sorted(set(blocked_task_ids))
    )
    if not continuation_task_ids:
        raise ResumeContinuationError(
            "INVALID_CONTINUATION_FRONTIER",
            f"job {source_job_id} has no runnable continuation tasks",
        )

    active_approval_refs = _active_approval_refs(events)
    memory_version_refs = _memory_versions(events)
    continuation_token = _payload_hash(
        {
            "source_job_id": source_job_id,
            "root_run_id": root_run_id,
            "blocked_task_ids": sorted(blocked_task_ids),
            "checkpoint_generation": checkpoint_generation,
        }
    )
    blocked_nodes = []
    for task_id in blocked_task_ids:
        lineage_entry = task_lineage.get(task_id) or {
            "root_run_id": root_run_id,
            "logical_task_id": task_id,
            "task_run_id": None,
            "branch_id": _fallback_branch_id(task_id=task_id, tasks_by_id=tasks_by_id),
            "branch_parent": None,
            "lineage_hash": _lineage_hash(
                root_run_id=root_run_id,
                logical_task_id=task_id,
                branch_id=_fallback_branch_id(task_id=task_id, tasks_by_id=tasks_by_id),
                branch_parent=None,
            ),
            "continuation_index": continuation_index,
            "checkpoint_generation": checkpoint_generation,
            "terminal_event_id": None,
            "task_attempt": 1,
        }
        blocked_nodes.append(
            {
                "job_id": source_job_id,
                "root_run_id": root_run_id,
                "task_id": task_id,
                "task_run_id": lineage_entry.get("task_run_id"),
                "blocked_reason": _task_reason(tasks_payload, task_id),
                "lineage_path": {
                    "logical_task_id": task_id,
                    "branch_id": lineage_entry.get("branch_id"),
                    "parent_branch_id": lineage_entry.get("branch_parent"),
                    "lineage_hash": lineage_entry.get("lineage_hash"),
                    "continuation_index": continuation_index,
                    "checkpoint_generation": checkpoint_generation,
                },
                "continuation_token": _payload_hash(
                    {
                        "continuation_token": continuation_token,
                        "task_id": task_id,
                        "task_run_id": lineage_entry.get("task_run_id"),
                    }
                ),
                "upstream_completed_nodes": sorted(completed_task_ids),
                "active_approval_refs": active_approval_refs.get(task_id, []),
                "checkpoint_ref": source_job_id,
                "memory_version_refs": memory_version_refs,
            }
        )

    return {
        "resume_source_job_id": source_job_id,
        "root_run_id": root_run_id,
        "checkpoint_generation": checkpoint_generation,
        "continuation_index": continuation_index,
        "continuation_token": continuation_token,
        "blocked_nodes": blocked_nodes,
        "blocked_task_ids": sorted(blocked_task_ids),
        "blocked_reason": _blocked_reason(tasks_payload, blocked_task_ids),
        "lineage_path": [item["lineage_path"] for item in blocked_nodes],
        "upstream_completed_nodes": upstream_completed_nodes,
        "completed_task_ids": sorted(completed_task_ids),
        "continuation_task_ids": continuation_task_ids,
        "active_approval_refs": active_approval_refs,
        "checkpoint_ref": source_job_id,
        "memory_version_refs": memory_version_refs,
        "completed_outputs": completed_outputs,
        "task_lineage": task_lineage,
    }


def _continuation_task_ids(
    *,
    tasks: list[TaskDefinition],
    blocked_task_ids: list[str],
    completed_task_ids: set[str],
) -> list[str]:
    children: dict[str, list[str]] = {}
    for task in tasks:
        for dependency in task.depends_on:
            children.setdefault(dependency, []).append(task.task_id)
    scheduled: set[str] = set()
    stack = list(blocked_task_ids)
    while stack:
        current = stack.pop()
        if current in scheduled or current in completed_task_ids:
            continue
        scheduled.add(current)
        stack.extend(children.get(current, []))
    ordered = [task.task_id for task in tasks if task.task_id in scheduled]
    return ordered


def _active_approval_refs(events: list[dict[str, Any]]) -> dict[str, list[str]]:
    consumed: set[str] = set()
    requested_by_task: dict[str, list[str]] = {}
    for event in events:
        event_name = str(event.get("event") or "")
        approval_id = str(
            (event.get("data") or {}).get("approval_id") or event.get("approval_id") or ""
        ).strip()
        task_id = str(event.get("task_id") or "").strip()
        if not approval_id:
            continue
        if event_name == "approval_consumed":
            consumed.add(approval_id)
            continue
        if event_name == "approval_requested" and task_id:
            requested_by_task.setdefault(task_id, []).append(approval_id)
    return {
        task_id: [approval_id for approval_id in approval_ids if approval_id not in consumed]
        for task_id, approval_ids in requested_by_task.items()
    }


def _memory_versions(events: list[dict[str, Any]]) -> dict[str, int]:
    versions: dict[str, int] = {}
    for event in events:
        if str(event.get("event") or "") != "memory_write_succeeded":
            continue
        target = str(event.get("memory_target") or "").strip()
        if not target:
            continue
        committed = int(event.get("committed_state_version") or 0)
        versions[target] = max(committed, versions.get(target, 0))
    return versions


def _blocked_reason(tasks_payload: list[dict[str, Any]], blocked_task_ids: list[str]) -> str | None:
    reasons = {
        _task_reason(tasks_payload, task_id)
        for task_id in blocked_task_ids
        if _task_reason(tasks_payload, task_id)
    }
    if not reasons:
        return None
    return ",".join(sorted(reasons))


def _task_reason(tasks_payload: list[dict[str, Any]], task_id: str) -> str | None:
    for item in tasks_payload:
        if str(item.get("task_id") or "") != task_id:
            continue
        reason = str(item.get("reason_code") or "").strip()
        return reason or None
    return None


def _fallback_branch_id(*, task_id: str, tasks_by_id: dict[str, TaskDefinition]) -> str:
    task = tasks_by_id.get(task_id)
    if task is None or not task.depends_on:
        return f"branch:{task_id}"
    parent_ref = ",".join(sorted(task.depends_on))
    return f"branch:{task_id}:{hashlib.sha256(parent_ref.encode('utf-8')).hexdigest()[:10]}"


def _lineage_hash(
    *,
    root_run_id: str,
    logical_task_id: str,
    branch_id: str,
    branch_parent: str | None,
) -> str:
    return _payload_hash(
        {
            "root_run_id": root_run_id,
            "logical_task_id": logical_task_id,
            "branch_id": branch_id,
            "branch_parent": branch_parent,
        }
    )


def _payload_hash(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
