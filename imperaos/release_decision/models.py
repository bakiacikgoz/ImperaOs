from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Literal

from pydantic import Field, field_validator, model_validator

from imperaos.memory.models import StrictModel

ReleaseDecisionStatus = Literal[
    "blocked",
    "conditional",
    "approved_for_design_partner_rc",
    "approved_for_hat_a_rc",
]
HatAStatus = Literal["approved", "conditional", "blocked", "not_evaluated"]
HatBStatus = Literal[
    "blocked_external_credentials",
    "conditional",
    "approved",
    "not_in_scope",
]
DesignPartnerRcStatus = Literal["approved", "conditional", "blocked"]
NoShipSeverity = Literal["blocker", "warning", "external_blocker", "deferred"]
NoShipItemStatus = Literal["open", "resolved", "accepted_boundary", "deferred"]
SignoffRole = Literal["release_owner", "security_operator", "pilot_operator", "product_owner"]
EvidenceKind = Literal[
    "gate_ledger",
    "freeze_manifest",
    "handoff",
    "field_evidence",
    "claim_matrix",
    "signoff",
    "dossier",
    "scan_report",
    "summary",
]


class EvidenceRef(StrictModel):
    artifact_id: str = Field(alias="artifactId")
    path: str
    sha256: str
    kind: EvidenceKind
    schema_version: str | None = Field(default=None, alias="schemaVersion")
    generated_at_utc: datetime | None = Field(default=None, alias="generatedAtUtc")

    @field_validator("artifact_id")
    @classmethod
    def _artifact_id_valid(cls, value: str) -> str:
        if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{1,127}", value):
            raise ValueError("artifactId must be stable lowercase text")
        return value

    @field_validator("path")
    @classmethod
    def _path_is_relative(cls, value: str) -> str:
        normalized = value.replace("\\", "/")
        if re.match(r"^[A-Za-z]:/", normalized) or normalized.startswith("/"):
            raise ValueError("evidence path must be relative")
        if ".." in normalized.split("/"):
            raise ValueError("evidence path must not traverse parents")
        return normalized

    @field_validator("sha256")
    @classmethod
    def _sha256_valid(cls, value: str) -> str:
        if not re.fullmatch(r"[a-fA-F0-9]{64}", value):
            raise ValueError("sha256 must be 64 hex chars")
        return value.lower()


class RcFreezeReconciliationInput(StrictModel):
    gate_ledger_ref: EvidenceRef = Field(alias="gateLedgerRef")
    freeze_manifest_ref: EvidenceRef = Field(alias="freezeManifestRef")
    repo_root: str = Field(default=".", alias="repoRoot")
    expected_head_sha: str | None = Field(default=None, alias="expectedHeadSha")
    profile: str = "enterprise"
    allow_conditional: bool = Field(default=False, alias="allowConditional")


class RcFreezeReconciliationReport(StrictModel):
    schema_version: Literal["rc-freeze-reconciliation/v1"] = Field(
        default="rc-freeze-reconciliation/v1",
        alias="schemaVersion",
    )
    generated_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        alias="generatedAtUtc",
    )
    status: Literal["ready", "conditional", "blocked"]
    original_freeze_status: str = Field(default="missing", alias="originalFreezeStatus")
    reconciled_status: str = Field(default="missing", alias="reconciledStatus")
    closed_conditional_reasons: list[str] = Field(
        default_factory=list,
        alias="closedConditionalReasons",
    )
    remaining_conditional_reasons: list[str] = Field(
        default_factory=list,
        alias="remainingConditionalReasons",
    )
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")
    warnings: list[str] = Field(default_factory=list)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list, alias="evidenceRefs")


class NoShipItem(StrictModel):
    id: str
    severity: NoShipSeverity
    status: NoShipItemStatus
    claim_id: str = Field(alias="claimId")
    reason_code: str = Field(alias="reasonCode")
    evidence_refs: list[EvidenceRef] = Field(default_factory=list, alias="evidenceRefs")
    resolution_path: str | None = Field(default=None, alias="resolutionPath")


class NoShipRegister(StrictModel):
    schema_version: Literal["release.no-ship-register/v1"] = Field(
        default="release.no-ship-register/v1",
        alias="schemaVersion",
    )
    status: Literal["clear", "conditional", "blocked"]
    items: list[NoShipItem] = Field(default_factory=list)
    blocking_count: int = Field(default=0, alias="blockingCount")
    external_blocker_count: int = Field(default=0, alias="externalBlockerCount")
    accepted_boundary_count: int = Field(default=0, alias="acceptedBoundaryCount")

    @model_validator(mode="after")
    def _count_items(self) -> NoShipRegister:
        self.blocking_count = sum(
            1 for item in self.items if item.severity == "blocker" and item.status == "open"
        )
        self.external_blocker_count = sum(
            1 for item in self.items if item.severity == "external_blocker"
        )
        self.accepted_boundary_count = sum(
            1 for item in self.items if item.status == "accepted_boundary"
        )
        if self.blocking_count:
            self.status = "blocked"
        elif any(item.status == "open" for item in self.items):
            self.status = "conditional"
        return self


class HumanSignoffRecord(StrictModel):
    schema_version: Literal["human-signoff/v1"] = Field(
        default="human-signoff/v1",
        alias="schemaVersion",
    )
    signoff_id: str = Field(alias="signoffId")
    role: SignoffRole
    operator_display_name_hash: str = Field(alias="operatorDisplayNameHash")
    dossier_sha256: str = Field(alias="dossierSha256")
    accepted_boundaries: list[str] = Field(default_factory=list, alias="acceptedBoundaries")
    signed_at_utc: datetime = Field(alias="signedAtUtc")
    notes_hash: str | None = Field(default=None, alias="notesHash")

    @field_validator("operator_display_name_hash", "dossier_sha256", "notes_hash")
    @classmethod
    def _hash_valid(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not re.fullmatch(r"[a-fA-F0-9]{64}", value):
            raise ValueError("hash values must be 64 hex chars")
        return value.lower()


class HumanSignoffVerificationReport(StrictModel):
    schema_version: Literal["human-signoff-verification/v1"] = Field(
        default="human-signoff-verification/v1",
        alias="schemaVersion",
    )
    status: Literal["missing", "partial", "verified", "blocked"]
    required_roles: list[str] = Field(default_factory=list, alias="requiredRoles")
    verified_roles: list[str] = Field(default_factory=list, alias="verifiedRoles")
    missing_roles: list[str] = Field(default_factory=list, alias="missingRoles")
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")
    warnings: list[str] = Field(default_factory=list)


class ReleaseDecisionDossier(StrictModel):
    schema_version: Literal["release-decision-dossier/v1"] = Field(
        default="release-decision-dossier/v1",
        alias="schemaVersion",
    )
    generated_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        alias="generatedAtUtc",
    )
    decision_id: str = Field(alias="decisionId")
    profile: str
    head_sha: str | None = Field(default=None, alias="headSha")
    branch: str | None = None
    status: ReleaseDecisionStatus
    hat_a_status: HatAStatus = Field(alias="hatAStatus")
    hat_b_status: HatBStatus = Field(alias="hatBStatus")
    design_partner_rc_status: DesignPartnerRcStatus = Field(alias="designPartnerRcStatus")
    rc_freeze_reconciliation: RcFreezeReconciliationReport = Field(
        default_factory=lambda: RcFreezeReconciliationReport(
            status="conditional",
            originalFreezeStatus="missing",
            reconciledStatus="missing",
            remainingConditionalReasons=["RC_FREEZE_RECONCILIATION_MISSING"],
        ),
        alias="rcFreezeReconciliation",
    )
    no_ship_register: NoShipRegister = Field(
        default_factory=lambda: NoShipRegister(status="conditional"),
        alias="noShipRegister",
    )
    signoff_status: Literal["missing", "partial", "verified", "blocked"] = Field(
        alias="signoffStatus"
    )
    required_signoff_roles: list[str] = Field(alias="requiredSignoffRoles")
    evidence_refs: list[EvidenceRef] = Field(default_factory=list, alias="evidenceRefs")
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")
    warnings: list[str] = Field(default_factory=list)


class ReleaseDecisionVerificationReport(StrictModel):
    schema_version: Literal["release-decision-verification/v1"] = Field(
        default="release-decision-verification/v1",
        alias="schemaVersion",
    )
    status: Literal["ready", "conditional", "blocked"]
    dossier_sha256: str | None = Field(default=None, alias="dossierSha256")
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")
    warnings: list[str] = Field(default_factory=list)
    allow_conditional: bool = Field(default=False, alias="allowConditional")


class RcReleaseDecisionSnapshot(StrictModel):
    schema_version: Literal["control-plane.rc-release-decision-snapshot/v1"] = Field(
        default="control-plane.rc-release-decision-snapshot/v1",
        alias="schemaVersion",
    )
    status: Literal[
        "not_available",
        "blocked",
        "conditional",
        "approved_for_design_partner_rc",
        "approved_for_hat_a_rc",
    ] = "not_available"
    latest_dossier_ref: str | None = Field(default=None, alias="latestDossierRef")
    latest_summary_ref: str | None = Field(default=None, alias="latestSummaryRef")
    signoff_status: str = Field(default="missing", alias="signoffStatus")
    hat_a_status: str = Field(default="not_evaluated", alias="hatAStatus")
    hat_b_status: str = Field(default="not_in_scope", alias="hatBStatus")
    design_partner_rc_status: str = Field(default="conditional", alias="designPartnerRcStatus")
    no_ship_blocking_count: int = Field(default=0, alias="noShipBlockingCount")
    external_blocker_count: int = Field(default=0, alias="externalBlockerCount")
    evidence_ref_count: int = Field(default=0, alias="evidenceRefCount")
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")
    warnings: list[str] = Field(default_factory=list)
