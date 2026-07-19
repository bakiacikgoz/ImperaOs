from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from imperaos.computer_use.vision_runtime.models import VisionStepResult


class RedactedVisionAuditRecorder:
    def __init__(
        self,
        *,
        job_id: str,
        job_dir: Path,
        runtime_config_hash: str,
        policy_hash: str,
    ) -> None:
        self.job_id = job_id
        self.job_dir = job_dir
        self.runtime_config_hash = runtime_config_hash
        self.policy_hash = policy_hash
        self.job_dir.mkdir(parents=True, exist_ok=True)
        self.events_path = self.job_dir / "events.jsonl"
        self.steps_path = self.job_dir / "steps.json"
        self.envelope_path = self.job_dir / "audit_envelope.json"
        self._events: list[dict[str, Any]] = []
        self._steps: list[dict[str, Any]] = []
        self._prev_hash = ""

    def record_step(self, step: VisionStepResult) -> None:
        payload = step.model_dump(mode="json", exclude_none=True)
        payload.pop("raw_screenshot_path", None)
        self._append_event("checkpoint", payload, step_index=step.step_index)
        self._steps.append(payload)
        self.steps_path.write_text(
            json.dumps(self._steps, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def record_runtime_start(self) -> None:
        self._append_event("runtime_start", {"status": "running"})

    def record_preflight_blocked(self, runtime_preflight: dict[str, Any]) -> None:
        self._append_event(
            "preflight_blocked",
            {
                "reasonCode": runtime_preflight.get("reasonCode"),
                "runtimePreflight": runtime_preflight,
            },
        )

    def record_runtime_stop(self, *, status: str, reason_code: str | None = None) -> None:
        payload: dict[str, Any] = {"status": status}
        if reason_code:
            payload["reasonCode"] = reason_code
        self._append_event("runtime_stop", payload)

    def finalize(self, status: str) -> dict[str, Any]:
        envelope = {
            "artifact_version": "computer_use_vision_audit/v1",
            "job_id": self.job_id,
            "status": status,
            "runtime_config_hash": self.runtime_config_hash,
            "policy_hash": self.policy_hash,
            "redaction_report": {
                "redacted": True,
                "raw_screenshot_persisted_count": 0,
            },
            "integrity": {
                "event_count": len(self._events),
                "last_hash": self._prev_hash,
                "hash_chain_verified": self.verify_hash_chain(),
            },
        }
        self.envelope_path.write_text(
            json.dumps(envelope, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return envelope

    def verify_hash_chain(self) -> bool:
        previous = ""
        for event in self._events:
            if event.get("prev_hash") != previous:
                return False
            if event.get("hash") != _event_hash({k: v for k, v in event.items() if k != "hash"}):
                return False
            previous = str(event["hash"])
        return True

    def _write_events(self) -> None:
        lines = [json.dumps(event, ensure_ascii=False, sort_keys=True) for event in self._events]
        self.events_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    def _append_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        step_index: int | None = None,
    ) -> None:
        event: dict[str, Any] = {
            "event_version": "computer_use_vision_event/v1",
            "job_id": self.job_id,
            "event_type": event_type,
            "created_at": datetime.now(UTC).isoformat(),
            "payload": payload,
            "prev_hash": self._prev_hash,
        }
        if step_index is not None:
            event["step_index"] = step_index
        event["hash"] = _event_hash(event)
        self._prev_hash = str(event["hash"])
        self._events.append(event)
        self._write_events()


def _event_hash(event: dict[str, Any]) -> str:
    payload = json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
