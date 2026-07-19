from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ComputerUseMode(StrEnum):
    DRY_RUN = "dry_run"
    STEP_APPROVAL = "step_approval"
    EXECUTE = "execute"


class BrowserTaskFamily(StrEnum):
    PAGE_INSPECTION = "page_inspection"
    FORM_FILL_DRAFT = "form_fill_draft"
    QUEUE_STATUS_UPDATE = "queue_status_update"
    AUTOMATION_SEQUENCE = "automation_sequence"


class PerceptionSource(StrEnum):
    DOM = "dom"
    DETERMINISTIC_SELECTOR = "deterministic_selector"
    SCREENSHOT = "screenshot_grounding"
    OCR = "ocr"


class ActionCategory(StrEnum):
    READ_ONLY = "read_only"
    NAVIGATION = "navigation"
    INPUT = "input"
    FILE_OPS = "file_ops"
    MUTATION = "mutation"
    HIGH_RISK = "high_risk"


class RiskClass(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ExecutionStage(StrEnum):
    PLAN = "plan"
    OBSERVE = "observe"
    INTERPRET_STATE = "interpret_state"
    COMPARE_STATE = "compare_state"
    DECIDE_ACTION = "decide_action"
    CLASSIFY_RISK = "classify_risk"
    REQUIRE_APPROVAL = "require_approval"
    EXECUTE = "execute"
    VERIFY = "verify"
    CHECKPOINT = "checkpoint"
    RECOVER = "recover"
    STOPPED = "stopped"
    COMPLETED = "completed"


class SessionExecutionState(StrEnum):
    QUEUED = "queued"
    STARTING = "starting"
    RUNNING = "running"
    PAUSING = "pausing"
    PAUSED = "paused"
    RESUMING = "resuming"
    STOPPING = "stopping"
    STOPPED = "stopped"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"


class SessionStatus(StrEnum):
    RUNNING = "running"
    PREVIEW_READY = "preview_ready"
    AWAITING_APPROVAL = "awaiting_approval"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


class ComputerUseStopReason(StrEnum):
    UNSUPPORTED_PLATFORM = "unsupported_platform"
    MISSING_ADAPTER = "missing_adapter"
    AUTONOMY_NOT_ENABLED = "autonomy_not_enabled"
    UNKNOWN_VISUAL = "unknown_visual"
    SELECTOR_AMBIGUOUS = "selector_ambiguous"
    UNEXPECTED_MODAL = "unexpected_modal"
    FOCUS_DRIFT = "focus_drift"
    SENSITIVE_SURFACE_DETECTED = "sensitive_surface_detected"
    CONFIDENCE_BELOW_THRESHOLD = "confidence_below_threshold"
    POLICY_DENIED = "policy_denied"
    GOVERNANCE_UNAVAILABLE = "governance_unavailable"


class SelectorContext(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    selector: str
    selector_source: str
    selector_trace: list[str] = Field(default_factory=list)


class EvidenceEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    screenshot_hash: str | None = None
    redacted_fingerprint: str
    accessibility_subset: dict[str, Any] = Field(default_factory=dict)
    raw_screenshot_path: str | None = None


class PerceptionSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    source: PerceptionSource
    confidence: float = Field(ge=0.0, le=1.0)
    perception_fingerprint: str
    sensitive_surface: bool = False
    focused: bool = True
    unexpected_modal: bool = False
    selector_ambiguous: bool = False
    window_or_tab_identity: str
    app_identity: str
    current_url: str
    selector_context: SelectorContext
    evidence: EvidenceEnvelope


class TargetDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    target_ref: str
    window_identity: str
    app_identity: str
    selector_source: str
    selector: str
    expected_effect: str
    current_url: str


class ProposedAction(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    action_id: str
    category: ActionCategory
    risk_class: RiskClass
    target_descriptor: TargetDescriptor
    window_identity: str
    app_identity: str
    selector_source: str
    expected_effect: str
    approval_required: bool = True
    dry_run_preview: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    verification_kind: str | None = None
    verification_value: str | None = None
    execution_result: dict[str, Any] = Field(default_factory=dict)


class ExpectedSurface(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    app_name: str | None = None
    bundle_id: str | None = None
    window_title_contains: str | None = None
    tab_url_host: str | None = None
    tab_url_prefix: str | None = None
    selector_present: str | None = None
    allow_modal: bool = False


class SurfaceObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    foreground_app: str | None = None
    bundle_id: str | None = None
    focused_window_title: str | None = None
    active_tab_url: str | None = None
    active_tab_title: str | None = None
    selected_paths: list[str] | None = None
    active_document_path: str | None = None
    clipboard_text: str | None = None
    modal_detected: bool = False
    visible_selectors: list[str] | None = None
    captured_at: str


class SurfaceMismatch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    code: Literal[
        "wrong_app",
        "wrong_window",
        "wrong_tab",
        "unexpected_modal",
        "missing_expected_selector",
    ]
    message: str
    expected: dict[str, Any] = Field(default_factory=dict)
    observed: dict[str, Any] = Field(default_factory=dict)


class ExpectedFileOperation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    operation: Literal["open_dialog", "save_dialog", "upload", "download"]
    expected_path_prefix: str | None = None
    expected_filename: str | None = None
    allowed_roots: list[str] = Field(default_factory=list)
    must_exist: bool = False
    must_be_writable: bool = False
    allow_create: bool = False
    expected_mime_hint: str | None = None


class FileOperationObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    dialog_open: bool
    selected_path: str | None = None
    resolved_path: str | None = None
    file_exists: bool | None = None
    file_size_bytes: int | None = None
    within_allowed_roots: bool | None = None
    writable: bool | None = None
    download_completed: bool | None = None
    captured_at: str


class FileOperationMismatch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    code: Literal[
        "dialog_not_open",
        "selection_missing",
        "path_outside_allowed_roots",
        "file_missing",
        "file_not_created",
        "download_incomplete",
        "wrong_filename",
        "not_writable",
    ]
    message: str
    expected: dict[str, Any] = Field(default_factory=dict)
    observed: dict[str, Any] = Field(default_factory=dict)


class ControlCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    command_id: str
    command_type: Literal["pause", "resume", "stop"]
    issued_at: str
    issued_by: str | None = None
    expected_state: str | None = None
    reason: str | None = None


class ControlCommandResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    command_id: str
    command_type: Literal["pause", "resume", "stop"]
    outcome: Literal[
        "accepted",
        "applied",
        "rejected",
        "already_applied",
        "deferred",
    ]
    processed_at: str
    previous_state: str | None = None
    resulting_state: str | None = None
    reason: str | None = None
    deferred_until_safe_checkpoint: bool = False


class ReadinessCheckStatus(StrEnum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


class ComputerUseReadinessStatus(StrEnum):
    READY = "ready"
    DEGRADED = "degraded"
    BLOCKED = "blocked"


class ReadinessCheck(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    key: str
    status: ReadinessCheckStatus
    summary: str
    remediation: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class ReadinessReport(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    status: ComputerUseReadinessStatus
    checks: list[ReadinessCheck] = Field(default_factory=list)
    summary: str
    checked_at: str
    platform: str = "unknown"
    supported_surfaces: list[str] = Field(default_factory=list)
    computer_use: dict[str, Any] = Field(default_factory=dict)


class ComputerUseDoctorReport(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    status: Literal["ok", "warning", "blocked"]
    summary: str
    remediation: str | None = None
    checked_at: str
    artifact_root: str
    readiness: ReadinessReport
    job_id: str | None = None
    job_dir: str | None = None
    session_state: str | None = None
    job_status: str | None = None
    stopped_by_user: bool = False
    last_control_result: dict[str, Any] = Field(default_factory=dict)
    last_verification_result: dict[str, Any] = Field(default_factory=dict)
    surface_mismatch_code: str | None = None
    file_operation_mismatch_code: str | None = None
    suggested_actions: list[str] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)


class VerificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    verified: bool
    kind: str
    summary: str
    expected: dict[str, Any] = Field(default_factory=dict)
    observed: dict[str, Any] = Field(default_factory=dict)
    mismatch_code: str | None = None
    retryable: bool = False
    expected_surface: ExpectedSurface | None = None
    observed_surface: SurfaceObservation | None = None
    surface_mismatch: SurfaceMismatch | None = None
    expected_file_operation: ExpectedFileOperation | None = None
    observed_file_operation: FileOperationObservation | None = None
    file_operation_mismatch: FileOperationMismatch | None = None


class WindowState(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    window_identity: str
    app_identity: str
    surface_kind: str = "browser"
    focused: bool = True


class ChangedResource(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    target_ref: str
    action_id: str
    expected_effect: str
    status: str


class WorldModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    active_run_id: str
    objective: str
    stage: ExecutionStage
    last_known_status: str
    active_window: WindowState | None = None
    open_windows: list[WindowState] = Field(default_factory=list)
    execution_state: SessionExecutionState | None = None
    active_application_identity: str | None = None
    active_surface: str | None = None
    focused_window_title: str | None = None
    current_url: str | None = None
    browser_tab_title: str | None = None
    active_document_path: str | None = None
    selected_paths: list[str] = Field(default_factory=list)
    clipboard_text: str | None = None
    expected_surface: ExpectedSurface | None = None
    observed_surface: SurfaceObservation | None = None
    surface_mismatch: SurfaceMismatch | None = None
    expected_file_operation: ExpectedFileOperation | None = None
    observed_file_operation: FileOperationObservation | None = None
    file_operation_mismatch: FileOperationMismatch | None = None
    observed_targets: list[TargetDescriptor] = Field(default_factory=list)
    visible_target_set: list[str] = Field(default_factory=list)
    changed_resources: list[ChangedResource] = Field(default_factory=list)
    pending_approval_ids: list[str] = Field(default_factory=list)
    pending_dialog_state: dict[str, Any] = Field(default_factory=dict)
    selected_file_state: dict[str, Any] = Field(default_factory=dict)
    filesystem_result_set: list[str] = Field(default_factory=list)
    last_completed_action: str | None = None
    last_verified_effect: str | None = None
    last_verification_result: dict[str, Any] = Field(default_factory=dict)
    last_safe_checkpoint: str | None = None
    pending_control: ControlCommand | None = None
    resume_allowed: bool = False
    last_control_result: ControlCommandResult | None = None
    drift_detected: bool = False
    user_intervention_required: bool = False
    interruption_state: str | None = None
    notes: list[str] = Field(default_factory=list)


class ExecutionTurn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    stage: ExecutionStage
    perception: PerceptionSnapshot | None = None
    action: ProposedAction | None = None
    summary: str


class SessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    run_id: str
    prompt: str
    mode: ComputerUseMode = ComputerUseMode.DRY_RUN
    task_family: BrowserTaskFamily
    allowlisted_domains: list[str] = Field(default_factory=list)
    raw_evidence_opt_in: bool = False
    approval_actor: str | None = None


class SessionOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    status: SessionStatus
    mode: ComputerUseMode
    actions: list[ProposedAction] = Field(default_factory=list)
    approval_ids: list[str] = Field(default_factory=list)
    stop_reason: ComputerUseStopReason | None = None
    recorder_artifact: dict[str, Any] = Field(default_factory=dict)
    world_model: WorldModel | None = None
    execution_trace: list[ExecutionTurn] = Field(default_factory=list)
