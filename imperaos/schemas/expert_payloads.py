from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class VerificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    parse_ok: bool
    lint_ok: bool | None = None
    tests_ok: bool | None = None
    stage_reached: int = Field(default=0, ge=0, le=5)
    failure_reason: str | None = None
    retry_count: int = Field(default=0, ge=0, le=10)
    retry_strategy: str | None = None
    details: dict[str, str | int | bool | None] = Field(default_factory=dict)


class CodeExpertPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    issue_type: Literal["syntax", "runtime", "test", "import", "config", "refactor", "generic"]
    strategy: Literal["minimal_patch", "test_first_fix", "safe_refactor", "explain_only"]
    patch_plan: list[str] = Field(min_length=1)
    candidate_snippet: str | None = None
    verification: VerificationResult
    notes: str


class ResearchCitation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    path: str
    line: int = Field(ge=1)
    snippet: str


class ResearchExpertPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    summary: str
    evidence: list[str] = Field(default_factory=list)
    citations: list[ResearchCitation] = Field(default_factory=list)
    uncertainty: float = Field(ge=0.0, le=1.0)


class PlanExpertPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    plan_steps: list[str] = Field(default_factory=list)
    state_summary: str
    memory_candidates: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
