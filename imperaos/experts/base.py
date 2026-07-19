from __future__ import annotations

from abc import ABC, abstractmethod

from imperaos.schemas.models import ExpertRequest, ExpertResult


class ExpertBase(ABC):
    name: str
    estimated_tool_calls_per_run: int = 1

    @abstractmethod
    def run(self, request: ExpertRequest) -> ExpertResult:
        raise NotImplementedError
