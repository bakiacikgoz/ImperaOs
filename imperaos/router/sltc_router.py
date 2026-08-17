from __future__ import annotations

from dataclasses import dataclass, field

from imperaos.schemas.models import (
    ExpertName,
    ExpertStatus,
    PlannerOutput,
    RouterDecision,
    TaskType,
)
from imperaos.schemas.reason_codes import ReasonCode


@dataclass(slots=True)
class ExpertTemporalState:
    membrane: float = 0.0
    successes: int = 0
    failures: int = 0
    last_latency_ms: int = 0


@dataclass(slots=True)
class SLTCRouter:
    """Binary spiking-inspired temporal router prototype (Phase 3)."""

    confidence_threshold: float = 0.6
    decay: float = 0.82
    spike_threshold: float = 0.55
    failure_penalty_weight: float = 0.35
    latency_penalty_weight: float = 0.12
    need_bonus: float = 0.12
    conf_bonus: float = 0.2
    task_bias_overrides: dict[str, float] = field(default_factory=dict)
    states: dict[ExpertName, ExpertTemporalState] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for expert_name in (
            ExpertName.LLM_ONLY,
            ExpertName.CODE,
            ExpertName.RESEARCH,
            ExpertName.PLAN,
        ):
            self.states.setdefault(expert_name, ExpertTemporalState())

    def decide(self, planner_output: PlannerOutput) -> RouterDecision:
        if planner_output.confidence < self.confidence_threshold:
            return RouterDecision(
                selected_expert=ExpertName.LLM_ONLY,
                selection_confidence=planner_output.confidence,
                estimated_cost=0.08,
                estimated_latency_ms=planner_output.latency_budget_ms,
                fallback_expert=None,
                reason_code=ReasonCode.LOW_CONFIDENCE,
            )

        candidates = planner_output.expert_candidates or [ExpertName.LLM_ONLY]
        candidates = [
            candidate for candidate in candidates if candidate in self.states
        ] or [ExpertName.LLM_ONLY]

        scores: dict[ExpertName, float] = {}
        for candidate in candidates:
            state = self.states[candidate]
            spike_input = self._spike_input(
                candidate=candidate,
                planner_output=planner_output,
                state=state,
            )
            membrane = (self.decay * state.membrane) + spike_input
            state.membrane = membrane
            scores[candidate] = membrane

        selected = max(scores, key=scores.get)
        selected_score = scores[selected]
        reason_code = (
            ReasonCode.SLTC_SPIKE
            if selected_score >= self.spike_threshold
            else ReasonCode.SLTC_SUBTHRESHOLD
        )

        fallback = self._second_best(scores, selected)
        if selected_score < self.spike_threshold and ExpertName.LLM_ONLY in self.states:
            selected = ExpertName.LLM_ONLY
            fallback = fallback if fallback != ExpertName.LLM_ONLY else None
            reason_code = ReasonCode.SLTC_FALLBACK_LLM

        return RouterDecision(
            selected_expert=selected,
            selection_confidence=max(
                0.0,
                min(1.0, planner_output.confidence * 0.95 + selected_score * 0.05),
            ),
            estimated_cost=self._estimate_cost(selected),
            estimated_latency_ms=self._estimate_latency_ms(
                selected,
                planner_output.latency_budget_ms,
            ),
            fallback_expert=fallback,
            reason_code=reason_code,
        )

    def update_feedback(
        self,
        expert_name: ExpertName,
        status: ExpertStatus,
        elapsed_ms: int,
    ) -> None:
        if expert_name not in self.states:
            return
        state = self.states[expert_name]
        state.last_latency_ms = elapsed_ms
        if status == ExpertStatus.OK:
            state.successes += 1
            state.membrane = max(0.0, state.membrane * 0.9)
        else:
            state.failures += 1
            state.membrane = max(0.0, state.membrane * 0.5)

    @staticmethod
    def _base_task_bias(task_type: TaskType, candidate: ExpertName) -> float:
        table = {
            TaskType.CHAT: {ExpertName.LLM_ONLY: 0.25},
            TaskType.CODE: {ExpertName.CODE: 0.45, ExpertName.PLAN: 0.1},
            TaskType.RESEARCH: {ExpertName.RESEARCH: 0.45, ExpertName.PLAN: 0.1},
            TaskType.PLAN: {ExpertName.PLAN: 0.45, ExpertName.RESEARCH: 0.1},
            TaskType.MIXED: {
                ExpertName.RESEARCH: 0.3,
                ExpertName.PLAN: 0.25,
                ExpertName.CODE: 0.2,
            },
        }
        return table.get(task_type, {}).get(candidate, 0.0)

    def _task_bias(self, task_type: TaskType, candidate: ExpertName) -> float:
        key = f"{task_type.value}:{candidate.value}"
        if key in self.task_bias_overrides:
            return float(self.task_bias_overrides[key])
        return self._base_task_bias(task_type=task_type, candidate=candidate)

    def _spike_input(
        self,
        *,
        candidate: ExpertName,
        planner_output: PlannerOutput,
        state: ExpertTemporalState,
    ) -> float:
        failure_penalty = (
            state.failures / max(state.successes + state.failures, 1)
        ) * self.failure_penalty_weight
        latency_penalty = (
            self.latency_penalty_weight
            if (state.last_latency_ms and state.last_latency_ms > planner_output.latency_budget_ms)
            else 0
        )
        task_bias = self._task_bias(task_type=planner_output.task_type, candidate=candidate)
        need_bonus = (
            self.need_bonus
            if planner_output.needs_expert and candidate != ExpertName.LLM_ONLY
            else 0.0
        )
        conf_bonus = planner_output.confidence * self.conf_bonus

        return max(0.0, task_bias + need_bonus + conf_bonus - failure_penalty - latency_penalty)

    @staticmethod
    def _second_best(scores: dict[ExpertName, float], selected: ExpertName) -> ExpertName | None:
        ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        for name, _score in ordered:
            if name != selected:
                return name
        return None

    @staticmethod
    def _estimate_cost(selected_expert: ExpertName) -> float:
        cost_table = {
            ExpertName.LLM_ONLY: 0.08,
            ExpertName.CODE: 0.38,
            ExpertName.RESEARCH: 0.3,
            ExpertName.PLAN: 0.24,
        }
        return cost_table.get(selected_expert, 0.3)

    @staticmethod
    def _estimate_latency_ms(selected_expert: ExpertName, budget_ms: int) -> int:
        latency_table = {
            ExpertName.LLM_ONLY: int(budget_ms * 0.7),
            ExpertName.CODE: int(budget_ms * 0.95),
            ExpertName.RESEARCH: int(budget_ms * 0.9),
            ExpertName.PLAN: int(budget_ms * 0.8),
        }
        return max(100, latency_table.get(selected_expert, budget_ms))
