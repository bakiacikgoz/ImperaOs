from __future__ import annotations

from dataclasses import dataclass

from imperaos.router.sltc_router import SLTCRouter
from imperaos.schemas.models import (
    ExpertName,
    PlannerOutput,
    ResponseMode,
    RouterDecision,
    TaskType,
)


class SLTCRouterInterface:
    """Research-path contract for sLTC-compatible router integrations."""

    def decide(self, features: dict[str, float | int | str]) -> RouterDecision:  # pragma: no cover
        raise NotImplementedError


@dataclass(slots=True)
class FeatureMappedSLTCRouter(SLTCRouterInterface):
    """Maps flat feature dictionaries into planner output for SLTCRouter decisions."""

    confidence_threshold: float = 0.6
    decay: float = 0.82
    spike_threshold: float = 0.55

    def __post_init__(self) -> None:
        self._router = SLTCRouter(
            confidence_threshold=self.confidence_threshold,
            decay=self.decay,
            spike_threshold=self.spike_threshold,
        )

    def decide(self, features: dict[str, float | int | str]) -> RouterDecision:
        task_raw = str(features.get("task_type", "chat"))
        task_type = TaskType(task_raw) if task_raw in TaskType._value2member_map_ else TaskType.CHAT

        confidence = _as_float(features.get("confidence"), 0.5)
        needs_expert = _as_bool(features.get("needs_expert"), task_type != TaskType.CHAT)
        latency_budget_ms = max(1, int(_as_float(features.get("latency_budget_ms"), 3000.0)))

        candidates_raw = features.get("expert_candidates")
        candidates: list[ExpertName] = []
        if isinstance(candidates_raw, str):
            for token in [item.strip() for item in candidates_raw.split(",") if item.strip()]:
                if token in ExpertName._value2member_map_:
                    candidates.append(ExpertName(token))

        if not candidates and needs_expert:
            default_by_task = {
                TaskType.CODE: [ExpertName.CODE, ExpertName.PLAN],
                TaskType.RESEARCH: [ExpertName.RESEARCH, ExpertName.PLAN],
                TaskType.PLAN: [ExpertName.PLAN, ExpertName.RESEARCH],
                TaskType.MIXED: [ExpertName.RESEARCH, ExpertName.PLAN, ExpertName.CODE],
                TaskType.CHAT: [],
            }
            candidates = default_by_task.get(task_type, [])

        planner_output = PlannerOutput(
            task_type=task_type,
            intent=str(features.get("intent", "feature_mapped")),
            needs_expert=needs_expert,
            expert_candidates=candidates,
            confidence=max(0.0, min(1.0, confidence)),
            latency_budget_ms=latency_budget_ms,
            can_fallback=True,
            response_mode=ResponseMode.TOOL_FIRST if needs_expert else ResponseMode.DIRECT,
        )
        return self._router.decide(planner_output)


# Backward-compatible exported name: previously no-op placeholder.
PlaceholderSLTCRouter = FeatureMappedSLTCRouter


def _as_float(value: float | int | str | None, default: float) -> float:
    if value is None:
        return default
    if isinstance(value, (float, int)):
        return float(value)
    try:
        return float(str(value))
    except ValueError:
        return default


def _as_bool(value: float | int | str | bool | None, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    lowered = str(value).strip().lower()
    if lowered in {"1", "true", "yes", "y", "on"}:
        return True
    if lowered in {"0", "false", "no", "n", "off"}:
        return False
    return default
