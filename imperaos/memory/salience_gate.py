from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SalienceDecision:
    salience_score: float
    spike: bool
    should_write: bool
    reason: str


@dataclass(slots=True)
class SalienceGate:
    """Binary spike-like salience gate for memory writes."""

    threshold: float = 0.62
    decay: float = 0.82
    task_bonus: float = 0.08
    expert_bonus: float = 0.06
    spike_reduction: float = 0.5
    membrane_state: float = 0.0
    last_reason: str = "init"
    keyword_weights: dict[str, float] = field(
        default_factory=lambda: {
            "remember": 0.18,
            "hatırla": 0.18,
            "plan": 0.12,
            "adım": 0.12,
            "deadline": 0.1,
            "todo": 0.1,
            "bug": 0.12,
            "hata": 0.12,
            "important": 0.16,
            "önemli": 0.16,
        }
    )

    def evaluate(
        self,
        *,
        task_type: str,
        user_input: str,
        assistant_output: str,
        expert_payload: dict[str, Any] | None = None,
    ) -> SalienceDecision:
        base = 0.05
        text = f"{user_input} {assistant_output}".lower()

        keyword_score = sum(weight for key, weight in self.keyword_weights.items() if key in text)
        length_score = min(len(user_input) / 350.0, 0.2)
        task_bonus = self.task_bonus if task_type in {"plan", "research", "mixed", "code"} else 0.0
        expert_bonus = self.expert_bonus if expert_payload else 0.0
        total_input = min(1.0, base + keyword_score + length_score + task_bonus + expert_bonus)

        membrane = (self.decay * self.membrane_state) + total_input
        spike = membrane >= self.threshold

        self.membrane_state = membrane * (self.spike_reduction if spike else 1.0)
        reason = "spike_threshold" if spike else "below_threshold"
        self.last_reason = reason

        score = max(0.0, min(1.0, membrane))
        return SalienceDecision(
            salience_score=score,
            spike=spike,
            should_write=spike,
            reason=reason,
        )
