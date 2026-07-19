from __future__ import annotations

import re
import time

from imperaos.experts.base import ExpertBase
from imperaos.schemas.expert_payloads import PlanExpertPayload
from imperaos.schemas.models import ExpertName, ExpertRequest, ExpertResult, ExpertStatus


class MemoryPlanExpert(ExpertBase):
    name = ExpertName.PLAN
    estimated_tool_calls_per_run = 1

    def run(self, request: ExpertRequest) -> ExpertResult:
        started = time.perf_counter()
        parts = self._split_into_steps(request.user_input)
        if not parts:
            parts = [request.user_input.strip() or "Görev girdisi boş"]

        plan_steps = [f"Adım {idx + 1}: {chunk}" for idx, chunk in enumerate(parts[:6])]
        memory_candidates = [chunk for chunk in parts[:3] if chunk]

        payload = PlanExpertPayload(
            plan_steps=plan_steps,
            state_summary="İstek deterministik olarak adımlara ayrıldı.",
            memory_candidates=memory_candidates,
            confidence=0.78,
        )
        elapsed = int((time.perf_counter() - started) * 1000)
        return ExpertResult(
            expert_name=self.name,
            status=ExpertStatus.OK,
            confidence=payload.confidence,
            payload=payload.model_dump(mode="json"),
            elapsed_ms=elapsed,
        )

    @staticmethod
    def _split_into_steps(text: str) -> list[str]:
        normalized = re.sub(r"[\n\r]+", " ", text).strip()
        if not normalized:
            return []
        pieces = re.split(r"[.!?;]|\s+-\s+", normalized)
        chunks = [piece.strip() for piece in pieces if piece.strip()]
        # Keep deterministic ordering and stable de-dup.
        seen: set[str] = set()
        unique: list[str] = []
        for chunk in chunks:
            lowered = chunk.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            unique.append(chunk)
        return unique
