from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import Field

from imperaos.memory.models import StrictModel, utc_now
from imperaos.runtime.config import RuntimeConfig


class MemoryPolicyEnforcementSnapshot(StrictModel):
    contract_version: Literal["memory-policy-enforcement-snapshot/v1"] = Field(
        default="memory-policy-enforcement-snapshot/v1",
        alias="contractVersion",
    )
    generated_at_utc: datetime = Field(default_factory=utc_now, alias="generatedAtUtc")
    status: Literal["disabled", "pass", "degraded", "blocked"] = "disabled"
    enabled: bool = False
    semantic_runtime_mode: Literal["disabled", "shadow", "enforced"] = Field(
        default="disabled",
        alias="semanticRuntimeMode",
    )
    read_event_count: int = Field(default=0, alias="readEventCount", ge=0)
    write_event_count: int = Field(default=0, alias="writeEventCount", ge=0)
    denied_count: int = Field(default=0, alias="deniedCount", ge=0)
    approval_required_count: int = Field(default=0, alias="approvalRequiredCount", ge=0)
    degraded_count: int = Field(default=0, alias="degradedCount", ge=0)
    raw_leak_count: int = Field(default=0, alias="rawLeakCount", ge=0)
    latest_evidence_refs: tuple[str, ...] = Field(default_factory=tuple, alias="latestEvidenceRefs")
    reason_codes: tuple[str, ...] = Field(default_factory=tuple, alias="reasonCodes")
    raw_content_included: Literal[False] = Field(default=False, alias="rawContentIncluded")


def build_memory_policy_enforcement_snapshot(
    *,
    config: RuntimeConfig,
    evidence_root: str | Path = "artifacts",
    generated_at: datetime | None = None,
) -> MemoryPolicyEnforcementSnapshot:
    runtime = config.memory.runtime
    root = Path(evidence_root) / "memory-runtime-policy" / "events"
    if not runtime.policy_enforcement_enabled:
        return MemoryPolicyEnforcementSnapshot(
            generatedAtUtc=generated_at or utc_now(),
            status="disabled",
            enabled=False,
            semanticRuntimeMode=runtime.semantic_runtime_mode,
            reasonCodes=("MEMORY_RUNTIME_POLICY_DISABLED",),
        )
    events = _load_events(root)
    read_count = sum(1 for item, _path in events if item.get("operation") == "read")
    write_count = sum(1 for item, _path in events if item.get("operation") == "write")
    denied_count = sum(
        1
        for item, _path in events
        if item.get("action") == "deny" or item.get("status") == "denied"
    )
    approval_count = sum(1 for item, _path in events if item.get("action") == "requires_approval")
    degraded_count = sum(1 for item, _path in events if item.get("status") == "degraded")
    raw_leak_count = sum(1 for item, _path in events if _raw_leak_detected(item))
    reasons = sorted(
        {
            str(reason)
            for item, _path in events
            for reason in item.get("reasonCodes", [])
            if reason
        }
    )
    status: Literal["disabled", "pass", "degraded", "blocked"] = "pass"
    if raw_leak_count:
        status = "blocked"
        reasons.append("MEMORY_RUNTIME_POLICY_RAW_LEAK_DETECTED")
    elif denied_count or degraded_count:
        status = "degraded"
    return MemoryPolicyEnforcementSnapshot(
        generatedAtUtc=generated_at or utc_now(),
        status=status,
        enabled=True,
        semanticRuntimeMode=runtime.semantic_runtime_mode,
        readEventCount=read_count,
        writeEventCount=write_count,
        deniedCount=denied_count,
        approvalRequiredCount=approval_count,
        degradedCount=degraded_count,
        rawLeakCount=raw_leak_count,
        latestEvidenceRefs=tuple(str(path) for _item, path in events[-5:]),
        reasonCodes=tuple(dict.fromkeys(reasons)),
        rawContentIncluded=False,
    )


def _load_events(root: Path) -> list[tuple[dict[str, object], Path]]:
    events: list[tuple[dict[str, object], Path]] = []
    if not root.exists():
        return events
    for path in sorted(root.glob("*.json")):
        try:
            events.append((json.loads(path.read_text(encoding="utf-8")), path))
        except (OSError, json.JSONDecodeError):
            continue
    return events


def _raw_leak_detected(payload: dict[str, object]) -> bool:
    forbidden_keys = {
        "query",
        "prompt",
        "response",
        "summary",
        "memory",
        "raw",
        "text",
        "token",
        "apiKey",
        "privateKey",
    }
    if payload.get("rawContentIncluded") is not False:
        return True
    return any(key in forbidden_keys for key in payload)
