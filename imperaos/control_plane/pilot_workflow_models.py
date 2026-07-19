from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from imperaos.memory.models import StrictModel

PilotWorkflowStatus = Literal["pass", "conditional", "blocked", "fail"]
PilotWorkflowMode = Literal["deterministic", "dry_run", "target_rehearsal"]


class PilotWorkflowMemoryExpectation(StrictModel):
    workspace_id: str = Field(default="workspace-main", alias="workspaceId")
    principal_id: str = Field(default="operator-main", alias="principalId")
    actor_id: str = Field(default="operator-main", alias="actorId")
    requester_role: str = Field(default="operator", alias="requesterRole")
    agent_id: str = Field(default="agent-alpha", alias="agentId")
    team_id: str = Field(default="team-alpha", alias="teamId")
    query: str = "hash only policy evidence"
    semantic_runtime_mode: Literal["disabled", "observe", "enforced"] = Field(
        default="enforced",
        alias="semanticRuntimeMode",
    )
    required_statuses: list[str] = Field(default_factory=lambda: ["pass"], alias="requiredStatuses")
    write_expectation: Literal["proposal_only", "written", "blocked"] = Field(
        default="proposal_only",
        alias="writeExpectation",
    )


class PilotWorkflowProviderExpectation(StrictModel):
    provider_kind: Literal["openai_responses", "anthropic_messages"] = Field(
        default="openai_responses",
        alias="providerKind",
    )
    model: str = "gpt-placeholder"
    runtime_mode: Literal["dry_run", "offline_conformance", "disabled"] = Field(
        default="dry_run",
        alias="runtimeMode",
    )
    expected_status: Literal["pass", "blocked", "conditional", "error"] = Field(
        default="pass",
        alias="expectedStatus",
    )
    evidence_mode: Literal["hash_only"] = Field(default="hash_only", alias="evidenceMode")
    raw_persistence: Literal[False] = Field(default=False, alias="rawPersistence")


class PilotWorkflowApprovalExpectation(StrictModel):
    expected_status: Literal["proposal_only", "approval_required", "blocked"] = Field(
        default="proposal_only",
        alias="expectedStatus",
    )
    executed_mutations: Literal[0] = Field(default=0, alias="executedMutations")


class PilotWorkflowEvidenceExpectation(StrictModel):
    evidence_mode: Literal["hash_only"] = Field(default="hash_only", alias="evidenceMode")
    raw_persistence: Literal[False] = Field(default=False, alias="rawPersistence")
    require_verifier_pass: bool = Field(default=True, alias="requireVerifierPass")


class GovernedPilotScenario(StrictModel):
    scenario_id: str = Field(alias="scenarioId")
    title: str
    user_intent: str = Field(alias="userIntent")
    memory: PilotWorkflowMemoryExpectation = Field(
        default_factory=PilotWorkflowMemoryExpectation
    )
    provider: PilotWorkflowProviderExpectation = Field(
        default_factory=PilotWorkflowProviderExpectation
    )
    approval: PilotWorkflowApprovalExpectation = Field(
        default_factory=PilotWorkflowApprovalExpectation
    )
    evidence: PilotWorkflowEvidenceExpectation = Field(
        default_factory=PilotWorkflowEvidenceExpectation
    )

    @field_validator("scenario_id")
    @classmethod
    def _scenario_id_valid(cls, value: str) -> str:
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{2,127}", value):
            raise ValueError("scenarioId must be stable lowercase snake/kebab text")
        return value


class GovernedPilotWorkflowSpec(StrictModel):
    schema_version: Literal["control-plane.governed-pilot-workflow-spec/v1"] = Field(
        default="control-plane.governed-pilot-workflow-spec/v1",
        alias="schemaVersion",
    )
    workflow_id: str = Field(alias="workflowId")
    title: str
    profile: str = "enterprise"
    mode: PilotWorkflowMode = "deterministic"
    environment_label: str = Field(default="local-deterministic", alias="environmentLabel")
    claims_under_test: list[str] = Field(default_factory=list, alias="claimsUnderTest")
    blocked_claims: list[str] = Field(default_factory=list, alias="blockedClaims")
    scenarios: list[GovernedPilotScenario] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @field_validator("workflow_id")
    @classmethod
    def _workflow_id_valid(cls, value: str) -> str:
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{2,127}", value):
            raise ValueError("workflowId must be stable lowercase snake/kebab text")
        return value

    @field_validator("environment_label")
    @classmethod
    def _environment_label_safe(cls, value: str) -> str:
        forbidden = ("secret", "token", "apikey", "api_key", "credential", "password")
        if any(item in value.lower() for item in forbidden):
            raise ValueError("environmentLabel must not contain credential-like terms")
        return value

    @model_validator(mode="after")
    def _has_scenarios(self) -> GovernedPilotWorkflowSpec:
        if not self.scenarios:
            raise ValueError("at least one scenario is required")
        return self


class PilotWorkflowValidationResult(StrictModel):
    schema_version: Literal["control-plane.governed-pilot-workflow-validation/v1"] = Field(
        default="control-plane.governed-pilot-workflow-validation/v1",
        alias="schemaVersion",
    )
    status: Literal["pass", "blocked"]
    workflow_id: str | None = Field(default=None, alias="workflowId")
    spec_hash: str | None = Field(default=None, alias="specHash")
    scenario_count: int = Field(default=0, alias="scenarioCount")
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")
    warnings: list[str] = Field(default_factory=list)


class PilotWorkflowComponentResult(StrictModel):
    component_id: str = Field(alias="componentId")
    status: Literal["pass", "conditional", "blocked", "fail"]
    reason_codes: list[str] = Field(default_factory=list, alias="reasonCodes")
    evidence_refs: list[str] = Field(default_factory=list, alias="evidenceRefs")
    metrics: dict[str, Any] = Field(default_factory=dict)


class PilotWorkflowStepResult(StrictModel):
    scenario_id: str = Field(alias="scenarioId")
    status: Literal["pass", "conditional", "blocked", "fail"]
    user_intent_hash: str = Field(alias="userIntentHash")
    memory: PilotWorkflowComponentResult
    provider: PilotWorkflowComponentResult
    approval: PilotWorkflowComponentResult
    evidence: PilotWorkflowComponentResult
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")
    warnings: list[str] = Field(default_factory=list)


class GovernedPilotWorkflowReport(StrictModel):
    schema_version: Literal["control-plane.governed-pilot-workflow-report/v1"] = Field(
        default="control-plane.governed-pilot-workflow-report/v1",
        alias="schemaVersion",
    )
    generated_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        alias="generatedAtUtc",
    )
    workflow_id: str = Field(alias="workflowId")
    run_id: str = Field(alias="runId")
    profile: str
    mode: PilotWorkflowMode
    status: Literal["pass", "conditional", "blocked", "fail"]
    spec_hash: str = Field(alias="specHash")
    report_hash: str | None = Field(default=None, alias="reportHash")
    evidence_mode: Literal["hash_only"] = Field(default="hash_only", alias="evidenceMode")
    raw_persistence: Literal[False] = Field(default=False, alias="rawPersistence")
    raw_leak_detected: bool = Field(default=False, alias="rawLeakDetected")
    claim_guard_status: Literal["pass", "conditional", "blocked", "fail"] = Field(
        alias="claimGuardStatus"
    )
    claim_guard_evidence_ref: str | None = Field(default=None, alias="claimGuardEvidenceRef")
    blocked_claims: list[str] = Field(default_factory=list, alias="blockedClaims")
    unsupported_claim_allowed: bool = Field(default=False, alias="unsupportedClaimAllowed")
    steps: list[PilotWorkflowStepResult] = Field(default_factory=list)
    evidence_manifest_path: str | None = Field(default=None, alias="evidenceManifestPath")
    report_path: str | None = Field(default=None, alias="reportPath")
    summary_path: str | None = Field(default=None, alias="summaryPath")
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")
    warnings: list[str] = Field(default_factory=list)


class GovernedPilotWorkflowVerification(StrictModel):
    schema_version: Literal["control-plane.governed-pilot-workflow-verification/v1"] = Field(
        default="control-plane.governed-pilot-workflow-verification/v1",
        alias="schemaVersion",
    )
    verified_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        alias="verifiedAtUtc",
    )
    status: Literal["pass", "fail"]
    workflow_id: str | None = Field(default=None, alias="workflowId")
    run_id: str | None = Field(default=None, alias="runId")
    report_hash: str | None = Field(default=None, alias="reportHash")
    evidence_refs_checked: int = Field(default=0, alias="evidenceRefsChecked")
    raw_leak_detected: bool = Field(default=False, alias="rawLeakDetected")
    unsupported_claim_allowed: bool = Field(default=False, alias="unsupportedClaimAllowed")
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")
    warnings: list[str] = Field(default_factory=list)


class GovernedPilotWorkflowSnapshot(StrictModel):
    schema_version: Literal["control-plane.governed-pilot-workflow/v1"] = Field(
        default="control-plane.governed-pilot-workflow/v1",
        alias="schemaVersion",
    )
    generated_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        alias="generatedAtUtc",
    )
    enabled: bool = False
    status: Literal["pass", "conditional", "blocked", "missing"] = "missing"
    workflow_id: str | None = Field(default=None, alias="workflowId")
    run_id: str | None = Field(default=None, alias="runId")
    mode: str | None = None
    evidence_mode: Literal["hash_only"] = Field(default="hash_only", alias="evidenceMode")
    raw_persistence: bool = Field(default=False, alias="rawPersistence")
    claim_guard_status: str = Field(default="missing", alias="claimGuardStatus")
    blocked_claims: list[str] = Field(default_factory=list, alias="blockedClaims")
    latest_report_path: str | None = Field(default=None, alias="latestReportPath")
    latest_summary_path: str | None = Field(default=None, alias="latestSummaryPath")
    verifier_status: Literal["pass", "fail", "missing"] = Field(
        default="missing",
        alias="verifierStatus",
    )
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")
    warnings: list[str] = Field(default_factory=list)
