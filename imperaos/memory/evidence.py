from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from imperaos.memory.models import MemoryEvidenceEvent, MemoryPolicyDecision, stable_id, utc_now


class MemoryEvidenceWriter:
    def __init__(self, output_root: str | Path = "artifacts/memory-governance"):
        self.output_root = Path(output_root)
        self.events_root = self.output_root / "events"
        self.events_root.mkdir(parents=True, exist_ok=True)

    def write_event(
        self,
        *,
        event_type: str,
        policy_decision: MemoryPolicyDecision,
        memory_id: str | None = None,
        proposal_id: str | None = None,
        actor_hash: str | None = None,
        content_hash: str | None = None,
        scope: str | None = None,
        visibility: str | None = None,
    ) -> tuple[MemoryEvidenceEvent, str]:
        event_id = stable_id("mem_evt", event_type, memory_id, proposal_id, utc_now().isoformat())
        event_hash = stable_id(
            "mem_hash",
            event_type,
            memory_id or "",
            proposal_id or "",
            content_hash or "",
            policy_decision.reason_code,
        ).replace("mem_hash_", "")
        event = MemoryEvidenceEvent(
            eventId=event_id,
            eventType=event_type,
            memoryId=memory_id,
            proposalId=proposal_id,
            actorHash=actor_hash,
            contentHash=content_hash,
            policyDecision=policy_decision,
            rawContentIncluded=False,
            rawPromptIncluded=False,
            rawResponseIncluded=False,
            scope=scope,
            visibility=visibility,
            eventHash=event_hash,
        )
        path = self.events_root / f"{event_id}.json"
        payload = event.model_dump(mode="json", by_alias=True)
        _assert_no_raw_leak(payload)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        latest = self.output_root / "latest.json"
        latest.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return event, str(path)


def _assert_no_raw_leak(payload: dict[str, Any]) -> None:
    raw = json.dumps(payload, sort_keys=True)
    forbidden = [
        '"candidateText"',
        '"candidate_text"',
        '"rawPrompt": true',
        '"rawResponse": true',
        "sk-",
    ]
    for marker in forbidden:
        if marker in raw:
            raise ValueError(f"memory evidence contains forbidden marker: {marker}")
