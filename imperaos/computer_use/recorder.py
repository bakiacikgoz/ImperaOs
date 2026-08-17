from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from imperaos.computer_use.models import ComputerUseMode, PerceptionSnapshot, ProposedAction


class ActionTrace(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    action_id: str
    target_ref: str
    approval_id: str | None = None
    status: str
    evidence: dict[str, Any] = Field(default_factory=dict)


class RecorderArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    mode: ComputerUseMode
    traces: list[ActionTrace] = Field(default_factory=list)


def build_recorder_artifact(
    *,
    mode: ComputerUseMode,
    perception: PerceptionSnapshot,
    actions: list[ProposedAction],
    approval_ids: list[str],
    raw_evidence_allowed: bool,
) -> dict[str, Any]:
    traces: list[ActionTrace] = []
    for index, action in enumerate(actions):
        evidence = {
            "screenshot_hash": perception.evidence.screenshot_hash,
            "redacted_fingerprint": perception.evidence.redacted_fingerprint,
            "selector_trace": perception.selector_context.selector_trace,
            "accessibility_subset": perception.evidence.accessibility_subset,
        }
        if raw_evidence_allowed:
            evidence["raw_screenshot_path"] = perception.evidence.raw_screenshot_path
        traces.append(
            ActionTrace(
                action_id=action.action_id,
                target_ref=action.target_descriptor.target_ref,
                approval_id=approval_ids[index] if index < len(approval_ids) else None,
                status=action.execution_result.get("status", "planned"),
                evidence=evidence,
            )
        )
    return RecorderArtifact(mode=mode, traces=traces).model_dump(mode="json")
