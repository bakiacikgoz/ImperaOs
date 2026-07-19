from __future__ import annotations

import hashlib
import json
from threading import Lock
from typing import Any

from imperaos.team.artifacts import TeamArtifactPaths, write_event
from imperaos.team.models import TeamEvent


class EventRecorder:
    def __init__(
        self,
        *,
        paths: TeamArtifactPaths,
        team_id: str,
        case_id: str,
        job_id: str,
        sink: list[TeamEvent],
        lock: Lock,
    ) -> None:
        self._paths = paths
        self._team_id = team_id
        self._case_id = case_id
        self._job_id = job_id
        self._sink = sink
        self._lock = _shared_lock(str(paths.events_path))
        self._event_seq = 0

    def emit(
        self,
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
        with self._lock:
            self._sync_event_seq()
            self._event_seq += 1
            payload = data or {}
            entry = TeamEvent(
                event=event,
                event_seq=self._event_seq,
                team_id=self._team_id,
                case_id=self._case_id,
                job_id=self._job_id,
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
                payload_hash=payload_hash or _payload_hash(payload),
                branch_id=branch_id,
                branch_parent=branch_parent,
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
                data=payload,
            )
            self._sink.append(entry)
            write_event(self._paths, entry)
            return entry

    def _sync_event_seq(self) -> None:
        if not self._paths.events_path.exists():
            return
        lines = [
            line
            for line in self._paths.events_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if not lines:
            return
        try:
            payload = json.loads(lines[-1])
        except json.JSONDecodeError:
            return
        self._event_seq = max(self._event_seq, int(payload.get("event_seq") or 0))


def _payload_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


_LOCK_GUARD = Lock()
_PATH_LOCKS: dict[str, Lock] = {}


def _shared_lock(key: str) -> Lock:
    with _LOCK_GUARD:
        lock = _PATH_LOCKS.get(key)
        if lock is None:
            lock = Lock()
            _PATH_LOCKS[key] = lock
        return lock
