from __future__ import annotations

from dataclasses import dataclass

from imperaos.schemas.models import ExpertName, PlannerOutput, RouterDecision, TaskType
from imperaos.schemas.reason_codes import ReasonCode


@dataclass(slots=True)
class RuleRouter:
    confidence_threshold: float = 0.6

    def decide(self, planner_output: PlannerOutput) -> RouterDecision:
        if planner_output.confidence < self.confidence_threshold:
            return RouterDecision(
                selected_expert=ExpertName.LLM_ONLY,
                selection_confidence=planner_output.confidence,
                estimated_cost=0.1,
                estimated_latency_ms=planner_output.latency_budget_ms,
                fallback_expert=None,
                reason_code=ReasonCode.LOW_CONFIDENCE,
            )

        if not planner_output.needs_expert or not planner_output.expert_candidates:
            return RouterDecision(
                selected_expert=ExpertName.LLM_ONLY,
                selection_confidence=planner_output.confidence,
                estimated_cost=0.1,
                estimated_latency_ms=max(100, planner_output.latency_budget_ms // 2),
                fallback_expert=None,
                reason_code=ReasonCode.NO_EXPERT_NEEDED,
            )

        preferred = self._preferred_expert(planner_output.task_type)
        candidate_set = set(planner_output.expert_candidates)
        selected = preferred if preferred in candidate_set else planner_output.expert_candidates[0]
        fallback = self._fallback_expert(selected, planner_output.expert_candidates)

        return RouterDecision(
            selected_expert=selected,
            selection_confidence=planner_output.confidence,
            estimated_cost=0.5,
            estimated_latency_ms=min(planner_output.latency_budget_ms, 2000),
            fallback_expert=fallback,
            reason_code=ReasonCode.RULE_ROUTE,
        )

    @staticmethod
    def _preferred_expert(task_type: TaskType) -> ExpertName:
        mapping = {
            TaskType.CODE: ExpertName.CODE,
            TaskType.RESEARCH: ExpertName.RESEARCH,
            TaskType.PLAN: ExpertName.PLAN,
            TaskType.MIXED: ExpertName.RESEARCH,
            TaskType.CHAT: ExpertName.LLM_ONLY,
        }
        return mapping.get(task_type, ExpertName.LLM_ONLY)

    @staticmethod
    def _fallback_expert(selected: ExpertName, candidates: list[ExpertName]) -> ExpertName | None:
        for candidate in candidates:
            if candidate != selected:
                return candidate
        return None
