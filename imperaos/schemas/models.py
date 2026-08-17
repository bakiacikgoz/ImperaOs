from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from imperaos.schemas.reason_codes import ReasonCode


class TaskType(StrEnum):
    CHAT = "chat"
    CODE = "code"
    RESEARCH = "research"
    PLAN = "plan"
    MIXED = "mixed"


class ResponseMode(StrEnum):
    DIRECT = "direct"
    TOOL_FIRST = "tool-first"
    ASK_CLARIFY = "ask-clarify"


class ExpertStatus(StrEnum):
    OK = "ok"
    PARTIAL = "partial"
    TIMEOUT = "timeout"
    ERROR = "error"
    SKIPPED = "skipped"


class ExpertName(StrEnum):
    LLM_ONLY = "llm_only"
    CODE = "code_expert"
    RESEARCH = "research_expert"
    PLAN = "plan_expert"


class PlannerOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    task_type: TaskType
    intent: str = Field(min_length=1)
    needs_expert: bool
    expert_candidates: list[ExpertName] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    latency_budget_ms: int = Field(ge=1)
    can_fallback: bool = True
    response_mode: ResponseMode = ResponseMode.DIRECT


class RouterDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    selected_expert: ExpertName
    selection_confidence: float = Field(ge=0.0, le=1.0)
    estimated_cost: float = Field(ge=0.0)
    estimated_latency_ms: int = Field(ge=0)
    fallback_expert: ExpertName | None = None
    reason_code: ReasonCode


class ExpertRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    request_id: str
    task_type: TaskType
    intent: str
    user_input: str
    context: dict[str, Any] = Field(default_factory=dict)
    latency_budget_ms: int = Field(ge=1)


class ExpertResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    expert_name: ExpertName
    status: ExpertStatus
    confidence: float = Field(ge=0.0, le=1.0)
    payload: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None
    elapsed_ms: int = Field(ge=0)


class OrchestratorResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    final_text: str
    used_path: str
    fallback_events: list[str] = Field(default_factory=list)
    trace_id: str
    metrics: dict[str, Any] = Field(default_factory=dict)


class TraceEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    request_id: str
    stage: str
    schema_version: str = "2.0"
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    data: dict[str, Any] = Field(default_factory=dict)
