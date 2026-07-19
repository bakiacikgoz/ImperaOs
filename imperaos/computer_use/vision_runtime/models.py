from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from imperaos.computer_use.models import ComputerUseMode, RiskClass


class VisionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)


class SurfaceKind(StrEnum):
    DESKTOP = "desktop"
    BROWSER = "browser"
    FILE_MANAGER = "file_manager"
    EDITOR = "editor"
    TERMINAL = "terminal"
    DIALOG = "dialog"
    UNKNOWN = "unknown"


class InputActionType(StrEnum):
    MOVE_MOUSE = "move_mouse"
    CLICK = "click"
    DOUBLE_CLICK = "double_click"
    RIGHT_CLICK = "right_click"
    DRAG = "drag"
    TYPE_TEXT = "type_text"
    PRESS_KEY = "press_key"
    HOTKEY = "hotkey"
    SCROLL = "scroll"
    WAIT = "wait"
    SWITCH_WINDOW = "switch_window"
    FOCUS_WINDOW_OR_APP = "focus_window_or_app"
    SELECT_FILE = "select_file"


class NormalizedBBox(VisionModel):
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    w: float = Field(gt=0.0, le=1.0)
    h: float = Field(gt=0.0, le=1.0)


class UiElement(VisionModel):
    element_id: str
    label: str | None = None
    role: str | None = None
    bbox: NormalizedBBox
    confidence: float = Field(ge=0.0, le=1.0)


class VisionObservation(VisionModel):
    screenshot_hash: str = Field(min_length=64, max_length=64)
    raw_screenshot_path: str | None = None
    captured_at: str
    platform: str
    image_width: int | None = Field(default=None, ge=1)
    image_height: int | None = Field(default=None, ge=1)
    active_app: str | None = None
    active_window_title: str | None = None
    surface_kind: SurfaceKind = SurfaceKind.UNKNOWN
    visible_text_redacted: list[str] = Field(default_factory=list)
    ui_elements: list[UiElement] = Field(default_factory=list)
    sensitive_indicators: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class VisionInterpretation(VisionModel):
    observation_hash: str = Field(min_length=64, max_length=64)
    summary: str
    candidate_actions: list[VisionAction] = Field(default_factory=list)
    surface_kind: SurfaceKind = SurfaceKind.UNKNOWN
    active_app_guess: str | None = None
    active_window_title_guess: str | None = None
    visible_text_redacted: list[str] = Field(default_factory=list)
    ui_elements: list[UiElement] = Field(default_factory=list)
    sensitive_indicators: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class VisionAction(VisionModel):
    action_id: str
    action_type: InputActionType
    target_element_id: str | None = None
    target_bbox: NormalizedBBox | None = None
    text: str | None = None
    hotkey: list[str] = Field(default_factory=list)
    scroll_delta: int | None = None
    wait_ms: int | None = None
    rationale: str
    expected_effect: str
    risk_class: RiskClass
    requires_approval: bool
    confidence: float = Field(ge=0.0, le=1.0)


class StopDecision(VisionModel):
    reason: str
    summary: str | None = None


class VisionPolicyDecision(VisionModel):
    allowed: bool
    requires_approval: bool
    denied: bool
    reason_code: str
    risk_reasons: list[str] = Field(default_factory=list)
    policy_hash: str


class ExecutionResult(VisionModel):
    status: Literal["executed", "skipped", "blocked", "failed"]
    message: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class VisionVerificationStatus(StrEnum):
    SATISFIED = "satisfied"
    INCONCLUSIVE = "inconclusive"
    FAILED = "failed"
    SKIPPED = "skipped"


class VerificationResult(VisionModel):
    verified: bool
    confidence: float = Field(ge=0.0, le=1.0)
    message: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    status: VisionVerificationStatus | None = None
    reason_code: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    before_observation_hash: str | None = Field(default=None, min_length=64, max_length=64)
    after_observation_hash: str | None = Field(default=None, min_length=64, max_length=64)
    action_digest: str | None = None


class VisionRunRequest(VisionModel):
    job_id: str
    objective: str
    mode: ComputerUseMode = ComputerUseMode.STEP_APPROVAL
    raw_screenshot_opt_in: bool = False


class VisionStepResult(VisionModel):
    step_index: int
    before_hash: str = Field(min_length=64, max_length=64)
    action: VisionAction
    policy_decision: VisionPolicyDecision
    execution_status: Literal["skipped", "executed", "blocked", "approval_required", "failed"]
    after_hash: str | None = Field(default=None, min_length=64, max_length=64)
    verification: VerificationResult | None = None
    checkpoint_id: str | None = None
    approval_snapshot: dict[str, Any] | None = None


class VisionRunArtifact(VisionModel):
    artifact_version: Literal["computer_use_vision/v1"] = "computer_use_vision/v1"
    job_id: str
    status: Literal["running", "awaiting_approval", "completed", "failed", "stopped", "blocked"]
    objective: str
    steps: list[VisionStepResult]
    redaction_report: dict[str, Any]
    integrity: dict[str, Any]
    stop_reason: str | None = None
    runtime_preflight: dict[str, Any] | None = Field(default=None, alias="runtimePreflight")
