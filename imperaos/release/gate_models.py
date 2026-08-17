from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import Field, field_validator, model_validator

from imperaos.memory.models import StrictModel

GateStatus = Literal["pass", "fail", "blocked", "conditional", "skipped"]
LedgerStatus = Literal["ready", "conditional", "blocked", "fail"]
RuntimePlatform = Literal["auto", "windows", "macos", "linux", "unknown", "github_actions"]
GateMode = Literal["rc-focused", "rc-full"]


class ReleaseGateTarget(StrictModel):
    target_id: Literal["mainline-rc", "design-partner-rc", "pilot-readiness"] = Field(
        alias="targetId"
    )
    profile: str = "enterprise"
    mode: GateMode = "rc-full"
    platform: RuntimePlatform = "auto"
    output_root: str = Field(alias="outputRoot")
    allow_expected_conditionals: bool = Field(default=False, alias="allowExpectedConditionals")


class GateCommandSpec(StrictModel):
    command_id: str = Field(alias="commandId")
    label: str
    argv: list[str]
    cwd: str = "."
    env: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: int = Field(default=900, alias="timeoutSeconds", ge=1, le=14400)
    platforms: list[str] = Field(default_factory=lambda: ["windows", "macos", "linux"])
    writes_artifacts: bool = Field(default=True, alias="writesArtifacts")
    mutates_worktree: bool = Field(default=False, alias="mutatesWorktree")
    destructive: bool = False
    expected_exit_codes: list[int] = Field(default_factory=lambda: [0], alias="expectedExitCodes")

    @field_validator("argv")
    @classmethod
    def _argv_must_be_list(cls, value: list[str]) -> list[str]:
        if (
            not isinstance(value, list)
            or not value
            or not all(isinstance(item, str) for item in value)
        ):
            raise ValueError("argv must be a non-empty list of strings")
        return value

    @model_validator(mode="after")
    def _deny_declared_destructive(self) -> GateCommandSpec:
        if self.destructive:
            raise ValueError("destructive gate commands are not allowed")
        return self


class GateArtifactRequirement(StrictModel):
    requirement_id: str = Field(alias="requirementId")
    gate_id: str = Field(alias="gateId")
    path: str
    kind: Literal["json", "md", "log", "text"] = "json"
    schema_ref: str | None = Field(default=None, alias="schemaRef")
    required_for_ready: bool = Field(default=True, alias="requiredForReady")
    hash_only: bool = Field(default=True, alias="hashOnly")
    allow_missing_when_conditional: bool = Field(
        default=False,
        alias="allowMissingWhenConditional",
    )


class GateArtifactRef(StrictModel):
    path: str
    sha256: str
    size_bytes: int = Field(alias="sizeBytes", ge=0)
    kind: Literal["json", "md", "log", "text", "unknown"] = "unknown"
    schema_ref: str | None = Field(default=None, alias="schemaRef")
    content_persisted: bool = Field(default=False, alias="contentPersisted")
    scan_status: Literal["pass", "fail", "skipped"] = Field(default="pass", alias="scanStatus")
    reason_codes: list[str] = Field(default_factory=list, alias="reasonCodes")


class GateCommandExecution(StrictModel):
    command_id: str = Field(alias="commandId")
    status: Literal["pass", "fail", "blocked", "timeout"]
    exit_code: int | None = Field(default=None, alias="exitCode")
    duration_ms: int = Field(default=0, alias="durationMs")
    redacted_stdout_tail: str = Field(default="", alias="redactedStdoutTail")
    redacted_stderr_tail: str = Field(default="", alias="redactedStderrTail")
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")


class GateRunResult(StrictModel):
    schema_version: Literal["release.gate-run-result/v1"] = Field(
        default="release.gate-run-result/v1",
        alias="schemaVersion",
    )
    gate_id: str = Field(alias="gateId")
    status: GateStatus
    started_at_utc: datetime = Field(alias="startedAtUtc")
    finished_at_utc: datetime = Field(alias="finishedAtUtc")
    duration_ms: int = Field(alias="durationMs", ge=0)
    exit_code: int | None = Field(default=None, alias="exitCode")
    commands: list[GateCommandExecution] = Field(default_factory=list)
    artifact_refs: list[GateArtifactRef] = Field(default_factory=list, alias="artifactRefs")
    missing_artifact_requirements: list[str] = Field(
        default_factory=list,
        alias="missingArtifactRequirements",
    )
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")
    warnings: list[str] = Field(default_factory=list)
    worktree_mutated: bool = Field(default=False, alias="worktreeMutated")
    secret_scan_status: Literal["pass", "fail", "skipped"] = Field(
        default="pass",
        alias="secretScanStatus",
    )
    raw_marker_scan_status: Literal["pass", "fail", "skipped"] = Field(
        default="pass",
        alias="rawMarkerScanStatus",
    )


class ReleaseGateSpec(StrictModel):
    gate_id: str = Field(alias="gateId")
    label: str | None = None
    commands: list[GateCommandSpec] = Field(default_factory=list)
    artifact_requirements: list[GateArtifactRequirement] = Field(
        default_factory=list,
        alias="artifactRequirements",
    )
    required: bool = True


class ReleaseGatePlan(StrictModel):
    schema_version: Literal["release.gate-plan/v1"] = Field(
        default="release.gate-plan/v1",
        alias="schemaVersion",
    )
    generated_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        alias="generatedAtUtc",
    )
    target: ReleaseGateTarget
    gates: list[ReleaseGateSpec]
    required_gate_ids: list[str] = Field(alias="requiredGateIds")
    make_required: bool = Field(default=False, alias="makeRequired")
    warnings: list[str] = Field(default_factory=list)


class GateEvidenceLedger(StrictModel):
    schema_version: Literal["release.gate-evidence-ledger/v1"] = Field(
        default="release.gate-evidence-ledger/v1",
        alias="schemaVersion",
    )
    generated_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        alias="generatedAtUtc",
    )
    repo_head_sha: str = Field(alias="repoHeadSha")
    branch: str
    target: ReleaseGateTarget
    gate_results: list[GateRunResult] = Field(default_factory=list, alias="gateResults")
    required_gate_ids: list[str] = Field(default_factory=list, alias="requiredGateIds")
    status: LedgerStatus
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")
    warnings: list[str] = Field(default_factory=list)
    artifact_root: str = Field(alias="artifactRoot")
    ledger_sha256: str | None = Field(default=None, alias="ledgerSha256")


class GateEvidenceVerificationReport(StrictModel):
    schema_version: Literal["release.gate-evidence-verification/v1"] = Field(
        default="release.gate-evidence-verification/v1",
        alias="schemaVersion",
    )
    generated_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        alias="generatedAtUtc",
    )
    ledger_ref: GateArtifactRef | None = Field(default=None, alias="ledgerRef")
    status: LedgerStatus
    verified_gate_count: int = Field(default=0, alias="verifiedGateCount")
    missing_gate_ids: list[str] = Field(default_factory=list, alias="missingGateIds")
    missing_artifact_ids: list[str] = Field(default_factory=list, alias="missingArtifactIds")
    tampered_artifact_refs: list[str] = Field(default_factory=list, alias="tamperedArtifactRefs")
    secret_or_raw_findings: list[str] = Field(default_factory=list, alias="secretOrRawFindings")
    claim_impact: str = Field(default="no_claim_change", alias="claimImpact")
    ready_for_rc_freeze: bool = Field(default=False, alias="readyForRcFreeze")
    reason_codes: list[str] = Field(default_factory=list, alias="reasonCodes")
    warnings: list[str] = Field(default_factory=list)


class RcEvidenceBackfillReport(StrictModel):
    schema_version: Literal["release.rc-evidence-backfill/v1"] = Field(
        default="release.rc-evidence-backfill/v1",
        alias="schemaVersion",
    )
    status: Literal["ready", "conditional", "blocked"]
    ready_for_rc_freeze: bool = Field(alias="readyForRcFreeze")
    resolved_gate_ids: list[str] = Field(default_factory=list, alias="resolvedGateIds")
    missing_gate_ids: list[str] = Field(default_factory=list, alias="missingGateIds")
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")
    warnings: list[str] = Field(default_factory=list)


class RcEvidenceOrchestrationReport(StrictModel):
    schema_version: Literal["release.rc-evidence-orchestration/v1"] = Field(
        default="release.rc-evidence-orchestration/v1",
        alias="schemaVersion",
    )
    status: LedgerStatus
    ledger_path: str = Field(alias="ledgerPath")
    verification_path: str = Field(alias="verificationPath")
    ready_for_rc_freeze: bool = Field(alias="readyForRcFreeze")
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")
    warnings: list[str] = Field(default_factory=list)


class RcGateEvidenceSnapshot(StrictModel):
    schema_version: Literal["control-plane.rc-gate-evidence-snapshot/v1"] = Field(
        default="control-plane.rc-gate-evidence-snapshot/v1",
        alias="schemaVersion",
    )
    status: Literal["ready", "conditional", "blocked", "missing"] = "missing"
    target: str = "mainline-rc"
    latest_ledger_ref: str | None = Field(default=None, alias="latestLedgerRef")
    latest_verification_ref: str | None = Field(default=None, alias="latestVerificationRef")
    verified_gate_count: int = Field(default=0, alias="verifiedGateCount")
    missing_gate_count: int = Field(default=0, alias="missingGateCount")
    missing_artifact_count: int = Field(default=0, alias="missingArtifactCount")
    secret_scan_status: str = Field(default="missing", alias="secretScanStatus")
    raw_marker_scan_status: str = Field(default="missing", alias="rawMarkerScanStatus")
    platform: str = "unknown"
    make_required: bool = Field(default=False, alias="makeRequired")
    ready_for_rc_freeze: bool = Field(default=False, alias="readyForRcFreeze")
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")
    warnings: list[str] = Field(default_factory=list)
