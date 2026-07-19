from __future__ import annotations

import json
import re
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from imperaos.control_plane.claim_guard import ClaimGuard
from imperaos.control_plane.pilot_workflow import build_governed_pilot_workflow_snapshot
from imperaos.control_plane.pilot_workflow_evidence import find_raw_leaks
from imperaos.control_plane.storage import canonical_json_hash, file_sha256
from imperaos.memory.models import StrictModel
from imperaos.runtime.config import RuntimeConfig, redact_config_payload

FieldEvidenceMode = Literal["rehearsal", "target_environment"]
FieldEvidenceStatus = Literal[
    "prepared",
    "collecting",
    "collected",
    "verified",
    "attested",
    "promotion_evaluated",
    "expired",
    "blocked",
    "invalid",
    "rc_ready",
]

STRICT_BLOCKED_CLAIMS = (
    "public-desktop-installer",
    "live-macos-computer-use",
    "live-windows-computer-use",
    "live-linux-computer-use",
    "multi-tenant-cloud-control-plane",
)

REQUIRED_ITEM_KINDS = {
    "session_manifest",
    "claim_guard_matrix",
    "governed_pilot_workflow_report",
    "memory_policy_enforcement_summary",
    "security_posture_summary",
    "support_bundle_manifest",
}

PLACEHOLDER_PATTERN = re.compile(
    r"\b(todo|tbd|placeholder|sample|example|codex|automation)\b", re.I
)
SECRET_MARKERS = ("sk-", "api_key", "token=", "password=", "private_key", "BEGIN RAW")


class TargetEnvironmentDescriptor(StrictModel):
    schema_version: Literal["control-plane.target-environment/v1"] = Field(
        default="control-plane.target-environment/v1",
        alias="schemaVersion",
    )
    environment_id: str = Field(alias="environmentId")
    environment_label: str = Field(alias="environmentLabel")
    environment_label_hash: str = Field(alias="environmentLabelHash")
    profile: str
    runtime_mode: Literal["self_hosted"] = Field(default="self_hosted", alias="runtimeMode")
    platform_summary: dict[str, str] = Field(default_factory=dict, alias="platformSummary")
    config_hash: str = Field(alias="configHash")
    created_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        alias="createdAtUtc",
    )


class FieldEvidenceSession(StrictModel):
    schema_version: Literal["control-plane.field-evidence-session/v1"] = Field(
        default="control-plane.field-evidence-session/v1",
        alias="schemaVersion",
    )
    session_id: str = Field(alias="sessionId")
    mode: FieldEvidenceMode
    status: FieldEvidenceStatus = "prepared"
    target_environment: TargetEnvironmentDescriptor = Field(alias="targetEnvironment")
    prepared_at_utc: datetime = Field(alias="preparedAtUtc")
    expires_at_utc: datetime = Field(alias="expiresAtUtc")
    commit_sha: str = Field(alias="commitSha")
    profile: str
    artifact_root: str = Field(alias="artifactRoot")
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")
    warnings: list[str] = Field(default_factory=list)


class FieldEvidenceItem(StrictModel):
    artifact_id: str = Field(alias="artifactId")
    kind: str
    relative_path: str = Field(alias="relativePath")
    sha256: str
    size_bytes: int = Field(alias="sizeBytes", ge=0)
    generated_at_utc: datetime = Field(alias="generatedAtUtc")
    producer: str
    redaction_status: Literal["redacted", "not_applicable"] = Field(
        default="redacted",
        alias="redactionStatus",
    )
    raw_persistence: bool = Field(default=False, alias="rawPersistence")
    signature_status: Literal["valid", "pending", "missing", "invalid"] = Field(
        default="missing",
        alias="signatureStatus",
    )
    required_for_strict_rc: bool = Field(default=False, alias="requiredForStrictRc")

    @field_validator("relative_path")
    @classmethod
    def _relative_path_safe(cls, value: str) -> str:
        path = Path(value)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("relativePath must not be absolute or escape with ..")
        return value


class FieldEvidenceBundle(StrictModel):
    schema_version: Literal["control-plane.field-evidence-bundle/v1"] = Field(
        default="control-plane.field-evidence-bundle/v1",
        alias="schemaVersion",
    )
    session_id: str = Field(alias="sessionId")
    mode: FieldEvidenceMode
    bundle_sha256: str = Field(default="sha256:pending", alias="bundleSha256")
    items: list[FieldEvidenceItem] = Field(default_factory=list)
    claim_boundaries: dict[str, str] = Field(default_factory=dict, alias="claimBoundaries")
    raw_persistence: bool = Field(default=False, alias="rawPersistence")
    secret_persistence: bool = Field(default=False, alias="secretPersistence")
    pii_persistence: bool = Field(default=False, alias="piiPersistence")
    generated_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        alias="generatedAtUtc",
    )
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")
    warnings: list[str] = Field(default_factory=list)


class FieldEvidenceVerificationResult(StrictModel):
    schema_version: Literal["control-plane.field-evidence-verification/v1"] = Field(
        default="control-plane.field-evidence-verification/v1",
        alias="schemaVersion",
    )
    verified_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        alias="verifiedAtUtc",
    )
    session_id: str | None = Field(default=None, alias="sessionId")
    mode: FieldEvidenceMode | None = None
    status: Literal["pass", "conditional", "blocked", "invalid"]
    bundle_sha256: str | None = Field(default=None, alias="bundleSha256")
    item_count: int = Field(default=0, alias="itemCount")
    raw_persistence: bool = Field(default=False, alias="rawPersistence")
    secret_persistence: bool = Field(default=False, alias="secretPersistence")
    pii_persistence: bool = Field(default=False, alias="piiPersistence")
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")
    warnings: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list, alias="evidenceRefs")


class OperatorAttestationBinding(StrictModel):
    schema_version: Literal["imperaos-non-developer-operator-attestation/v2"] = Field(
        default="imperaos-non-developer-operator-attestation/v2",
        alias="schemaVersion",
    )
    session_id: str = Field(alias="sessionId")
    release_pack_id: str = Field(alias="releasePackId")
    target_environment_label_hash: str = Field(alias="targetEnvironmentLabelHash")
    bundle_sha256: str = Field(alias="bundleSha256")
    operator_display_name: str = Field(alias="operatorDisplayName")
    operator_role: str = Field(alias="operatorRole")
    non_developer_operator: bool = Field(alias="nonDeveloperOperator")
    reviewed_runbook: bool = Field(alias="reviewedRunbook")
    completed_validation: bool = Field(alias="completedValidation")
    signed_at_utc: datetime = Field(alias="signedAtUtc")
    notes_redacted: str | None = Field(default=None, alias="notesRedacted")

    @model_validator(mode="after")
    def _reject_placeholders(self) -> OperatorAttestationBinding:
        fields = [self.operator_display_name, self.operator_role, self.notes_redacted or ""]
        if any(PLACEHOLDER_PATTERN.search(value) for value in fields):
            raise ValueError("operator attestation contains placeholder or automation terms")
        return self


class OperatorAttestationValidationResult(StrictModel):
    schema_version: Literal["control-plane.operator-attestation-binding-verification/v1"] = Field(
        default="control-plane.operator-attestation-binding-verification/v1",
        alias="schemaVersion",
    )
    validated_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        alias="validatedAtUtc",
    )
    status: Literal["valid", "missing", "invalid", "blocked"]
    session_id: str | None = Field(default=None, alias="sessionId")
    release_pack_id: str | None = Field(default=None, alias="releasePackId")
    bundle_sha256: str | None = Field(default=None, alias="bundleSha256")
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")
    warnings: list[str] = Field(default_factory=list)


class DesignPartnerFieldEvidenceSnapshot(StrictModel):
    schema_version: Literal["control-plane.design-partner-field-evidence/v1"] = Field(
        default="control-plane.design-partner-field-evidence/v1",
        alias="schemaVersion",
    )
    generated_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        alias="generatedAtUtc",
    )
    status: Literal["ready", "conditional", "blocked", "missing"] = "missing"
    mode: FieldEvidenceMode | None = None
    session_id: str | None = Field(default=None, alias="sessionId")
    evidence_mode: Literal["hash_only"] = Field(default="hash_only", alias="evidenceMode")
    raw_persistence: bool = Field(default=False, alias="rawPersistence")
    attestation_status: Literal["missing", "valid", "invalid", "blocked"] = Field(
        default="missing",
        alias="attestationStatus",
    )
    strict_rc_status: Literal["ready", "conditional", "blocked", "missing"] = Field(
        default="missing",
        alias="strictRcStatus",
    )
    item_count: int = Field(default=0, alias="itemCount")
    blocked_claims: list[str] = Field(default_factory=list, alias="blockedClaims")
    latest_bundle_path: str | None = Field(default=None, alias="latestBundlePath")
    latest_attestation_path: str | None = Field(default=None, alias="latestAttestationPath")
    latest_promotion_path: str | None = Field(default=None, alias="latestPromotionPath")
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")
    warnings: list[str] = Field(default_factory=list)


class DesignPartnerFieldPackManifest(StrictModel):
    schema_version: Literal["control-plane.design-partner-field-pack/v1"] = Field(
        default="control-plane.design-partner-field-pack/v1",
        alias="schemaVersion",
    )
    status: Literal["ready", "conditional", "blocked"]
    session_id: str | None = Field(default=None, alias="sessionId")
    field_root: str = Field(alias="fieldRoot")
    rc_root: str = Field(alias="rcRoot")
    strict_rc_report_path: str | None = Field(default=None, alias="strictRcReportPath")
    bundle_path: str | None = Field(default=None, alias="bundlePath")
    attestation_validation_path: str | None = Field(
        default=None,
        alias="attestationValidationPath",
    )
    generated_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        alias="generatedAtUtc",
    )
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")
    warnings: list[str] = Field(default_factory=list)


def prepare_field_evidence_session(
    *,
    config: RuntimeConfig,
    mode: FieldEvidenceMode,
    environment_label: str,
    output_root: Path,
    force_new_session: bool = False,
    now: datetime | None = None,
) -> FieldEvidenceSession:
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    session_path = output_root / "session.json"
    if session_path.exists() and not force_new_session:
        return FieldEvidenceSession.model_validate_json(session_path.read_text(encoding="utf-8"))
    generated_at = now or datetime.now(UTC)
    label = _safe_environment_label(environment_label)
    descriptor_seed = {
        "label": label,
        "profile": config.profile_name,
        "mode": mode,
        "generatedAtUtc": generated_at.isoformat(),
    }
    label_hash = canonical_json_hash({"label": label})
    descriptor = TargetEnvironmentDescriptor(
        environmentId=f"target-env-{canonical_json_hash(descriptor_seed, prefixed=False)[:16]}",
        environmentLabel=label,
        environmentLabelHash=label_hash,
        profile=config.profile_name,
        platformSummary={"runtime": "self_hosted", "detail": "redacted"},
        configHash=canonical_json_hash(redact_config_payload(config.model_dump(mode="python"))),
        createdAtUtc=generated_at,
    )
    session = FieldEvidenceSession(
        sessionId=f"field-{canonical_json_hash(descriptor_seed, prefixed=False)[:16]}",
        mode=mode,
        status="prepared",
        targetEnvironment=descriptor,
        preparedAtUtc=generated_at,
        expiresAtUtc=generated_at + timedelta(hours=72),
        commitSha=_git_commit(),
        profile=config.profile_name,
        artifactRoot=str(output_root),
        warnings=["TARGET_ENVIRONMENT_REHEARSAL_ONLY"] if mode == "rehearsal" else [],
    )
    _write_json(session_path, session.model_dump(mode="json", by_alias=True))
    return session


def collect_field_evidence_bundle(
    *,
    session: FieldEvidenceSession,
    evidence_root: Path,
    output_root: Path,
    now: datetime | None = None,
) -> FieldEvidenceBundle:
    output_root = Path(output_root)
    evidence_root = Path(evidence_root)
    generated_at = now or datetime.now(UTC)
    output_root.mkdir(parents=True, exist_ok=True)
    warnings = list(session.warnings)
    blocking = list(session.blocking_reasons)
    if generated_at > session.expires_at_utc:
        blocking.append("TARGET_EVIDENCE_SESSION_EXPIRED")

    _write_json(output_root / "session.json", session.model_dump(mode="json", by_alias=True))
    artifacts_root = output_root / "artifacts"
    artifacts_root.mkdir(parents=True, exist_ok=True)
    refs: list[Path] = []
    refs.append(output_root / "session.json")

    claim_matrix = ClaimGuard(config=RuntimeConfig.from_profile(session.profile)).evaluate(
        evidence_root=evidence_root
    )
    claim_path = artifacts_root / "claim_guard_matrix.json"
    _write_json(claim_path, claim_matrix.model_dump(mode="json"))
    refs.append(claim_path)
    claim_boundaries = {
        claim.claim_id: str(claim.status)
        for claim in claim_matrix.claims
        if claim.claim_id in STRICT_BLOCKED_CLAIMS
    }

    governed_snapshot = build_governed_pilot_workflow_snapshot(artifact_root=evidence_root)
    governed_path = artifacts_root / "governed_pilot_workflow_summary.json"
    _write_json(governed_path, governed_snapshot.model_dump(mode="json", by_alias=True))
    refs.append(governed_path)
    if governed_snapshot.status != "pass":
        warnings.append("GOVERNED_PILOT_WORKFLOW_NOT_PASS")

    memory_policy_path = artifacts_root / "memory_policy_enforcement_summary.json"
    try:
        from imperaos.memory.runtime_policy_snapshot import (
            build_memory_policy_enforcement_snapshot,
        )

        memory_policy = build_memory_policy_enforcement_snapshot(
            config=RuntimeConfig.from_profile(session.profile),
            evidence_root=evidence_root,
            generated_at=generated_at,
        )
        _write_json(memory_policy_path, memory_policy.model_dump(mode="json", by_alias=True))
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"MEMORY_POLICY_SUMMARY_UNAVAILABLE:{type(exc).__name__}")
        _write_json(memory_policy_path, {"status": "missing", "rawContentIncluded": False})
    refs.append(memory_policy_path)

    for source, name, kind, required in (
        (
            evidence_root / "security_posture.json",
            "security_posture_summary.json",
            "security_posture_summary",
            True,
        ),
        (
            evidence_root / "support_bundle_manifest.json",
            "support_bundle_manifest.json",
            "support_bundle_manifest",
            True,
        ),
        (
            evidence_root / "provider-runtime",
            "provider_runtime_summary.json",
            "provider_runtime_summary",
            False,
        ),
        (
            evidence_root / "evidence_index.json",
            "evidence_index_manifest.json",
            "evidence_index_manifest",
            False,
        ),
        (
            evidence_root / "design-partner-rc" / "reports-alerts-logs" / "manifest.json",
            "reports_alerts_logs_manifest.json",
            "reports_alerts_logs_manifest",
            False,
        ),
    ):
        if source.exists():
            refs.append(_copy_or_summarize(source, artifacts_root / name, kind=kind))
        elif required:
            warnings.append(f"FIELD_EVIDENCE_ITEM_MISSING:{kind}")

    items = [
        _field_item(
            source=path,
            root=output_root,
            kind=_kind_for_path(path),
            generated_at=generated_at,
            required_for_strict_rc=_kind_for_path(path) in REQUIRED_ITEM_KINDS,
        )
        for path in refs
    ]
    raw_persistence = any(item.raw_persistence for item in items)
    secret_persistence = _contains_secret_marker(items, output_root)
    if raw_persistence:
        blocking.append("RAW_PERSISTENCE_DETECTED")
    if secret_persistence:
        blocking.append("SECRET_PERSISTENCE_DETECTED")
    for claim_id in STRICT_BLOCKED_CLAIMS:
        status = claim_boundaries.get(claim_id)
        if status not in {"blocked", "deferred"}:
            blocking.append(f"UNSUPPORTED_CLAIM_ALLOWED:{claim_id}")
    bundle = FieldEvidenceBundle(
        sessionId=session.session_id,
        mode=session.mode,
        items=items,
        claimBoundaries=claim_boundaries,
        rawPersistence=raw_persistence,
        secretPersistence=secret_persistence,
        piiPersistence=False,
        generatedAtUtc=generated_at,
        blockingReasons=sorted(set(blocking)),
        warnings=sorted(set(warnings)),
    )
    bundle.bundle_sha256 = _bundle_hash(bundle)
    _write_json(
        output_root / "target_evidence_bundle.json", bundle.model_dump(mode="json", by_alias=True)
    )
    return bundle


def verify_field_evidence_bundle(
    *,
    bundle_path: Path,
    artifact_root: Path | None = None,
    now: datetime | None = None,
) -> FieldEvidenceVerificationResult:
    _ = artifact_root
    path = Path(bundle_path)
    if not path.exists():
        return FieldEvidenceVerificationResult(
            status="invalid",
            blockingReasons=["FIELD_EVIDENCE_BUNDLE_MISSING"],
        )
    try:
        bundle = FieldEvidenceBundle.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return FieldEvidenceVerificationResult(
            status="invalid",
            blockingReasons=[f"FIELD_EVIDENCE_BUNDLE_INVALID:{type(exc).__name__}"],
        )
    root = path.parent
    blocking = list(bundle.blocking_reasons)
    warnings = list(bundle.warnings)
    if _bundle_hash(bundle) != bundle.bundle_sha256:
        blocking.append("FIELD_EVIDENCE_BUNDLE_HASH_MISMATCH")
    for item in bundle.items:
        try:
            item_path = (root / item.relative_path).resolve()
            item_path.relative_to(root.resolve())
        except ValueError:
            blocking.append(f"UNSAFE_ARTIFACT_PATH:{item.artifact_id}")
            continue
        if not item_path.exists():
            if item.required_for_strict_rc:
                blocking.append(f"FIELD_EVIDENCE_ITEM_MISSING:{item.kind}")
            continue
        actual = f"sha256:{file_sha256(item_path)}"
        if actual != item.sha256:
            blocking.append(f"FIELD_EVIDENCE_ITEM_HASH_MISMATCH:{item.artifact_id}")
        if item.raw_persistence:
            blocking.append("RAW_PERSISTENCE_DETECTED")
        try:
            payload = json.loads(item_path.read_text(encoding="utf-8"))
        except Exception:
            payload = item_path.read_text(encoding="utf-8", errors="ignore")
        if find_raw_leaks(payload):
            blocking.append(f"RAW_EVIDENCE_LEAK:{item.artifact_id}")
    for claim_id in STRICT_BLOCKED_CLAIMS:
        if bundle.claim_boundaries.get(claim_id) not in {"blocked", "deferred"}:
            blocking.append(f"UNSUPPORTED_CLAIM_ALLOWED:{claim_id}")
    missing_required = REQUIRED_ITEM_KINDS - {item.kind for item in bundle.items}
    for kind in sorted(missing_required):
        warnings.append(f"FIELD_EVIDENCE_ITEM_MISSING:{kind}")
    status: Literal["pass", "conditional", "blocked", "invalid"]
    if blocking:
        status = "blocked"
    elif missing_required or bundle.mode == "rehearsal":
        status = "conditional"
        if bundle.mode == "rehearsal":
            warnings.append("TARGET_ENVIRONMENT_REHEARSAL_ONLY")
    else:
        status = "pass"
    return FieldEvidenceVerificationResult(
        verifiedAtUtc=now or datetime.now(UTC),
        sessionId=bundle.session_id,
        mode=bundle.mode,
        status=status,
        bundleSha256=bundle.bundle_sha256,
        itemCount=len(bundle.items),
        rawPersistence=bundle.raw_persistence,
        secretPersistence=bundle.secret_persistence,
        piiPersistence=bundle.pii_persistence,
        blockingReasons=sorted(set(blocking)),
        warnings=sorted(set(warnings)),
        evidenceRefs=[str(path)],
    )


def validate_independent_operator_attestation(
    *,
    attestation_path: Path,
    session: FieldEvidenceSession,
    bundle: FieldEvidenceBundle,
    implementation_actor_ids: set[str] | None = None,
    now: datetime | None = None,
) -> OperatorAttestationValidationResult:
    if not Path(attestation_path).exists():
        return OperatorAttestationValidationResult(
            status="missing",
            sessionId=session.session_id,
            bundleSha256=bundle.bundle_sha256,
            blockingReasons=["INDEPENDENT_OPERATOR_ATTESTATION_MISSING"],
        )
    blocking: list[str] = []
    try:
        payload = json.loads(Path(attestation_path).read_text(encoding="utf-8"))
        attestation = OperatorAttestationBinding.model_validate(payload)
    except Exception as exc:  # noqa: BLE001
        return OperatorAttestationValidationResult(
            status="invalid",
            sessionId=session.session_id,
            bundleSha256=bundle.bundle_sha256,
            blockingReasons=[f"OPERATOR_ATTESTATION_INVALID:{type(exc).__name__}"],
        )
    actor_terms = {
        item.lower()
        for item in (implementation_actor_ids or {"codex", "automation", "developer", "agent"})
    }
    if attestation.session_id != session.session_id:
        blocking.append("ATTESTATION_SESSION_MISMATCH")
    if (
        attestation.target_environment_label_hash
        != session.target_environment.environment_label_hash
    ):
        blocking.append("ATTESTATION_TARGET_ENVIRONMENT_MISMATCH")
    if attestation.bundle_sha256 != bundle.bundle_sha256:
        blocking.append("ATTESTATION_BUNDLE_HASH_MISMATCH")
    if not attestation.release_pack_id:
        blocking.append("ATTESTATION_RELEASE_PACK_MISSING")
    if not attestation.non_developer_operator:
        blocking.append("ATTESTATION_OPERATOR_NOT_INDEPENDENT")
    if not attestation.reviewed_runbook:
        blocking.append("ATTESTATION_RUNBOOK_NOT_REVIEWED")
    if not attestation.completed_validation:
        blocking.append("ATTESTATION_VALIDATION_NOT_COMPLETED")
    if any(term in attestation.operator_role.lower() for term in actor_terms):
        blocking.append("ATTESTATION_IMPLEMENTATION_ACTOR_NOT_ALLOWED")
    if any(
        marker.lower() in (attestation.notes_redacted or "").lower() for marker in SECRET_MARKERS
    ):
        blocking.append("ATTESTATION_NOTES_SECRET_LIKE")
    if attestation.signed_at_utc > (now or datetime.now(UTC)) + timedelta(minutes=5):
        blocking.append("ATTESTATION_TIMESTAMP_INVALID")
    return OperatorAttestationValidationResult(
        status="invalid" if blocking else "valid",
        sessionId=session.session_id,
        releasePackId=attestation.release_pack_id,
        bundleSha256=bundle.bundle_sha256,
        blockingReasons=sorted(set(blocking)),
    )


def build_design_partner_field_evidence_snapshot(
    *,
    artifact_root: Path,
    generated_at: datetime | None = None,
) -> DesignPartnerFieldEvidenceSnapshot:
    root = Path(artifact_root) / "design-partner-field-evidence"
    bundle_path = root / "target_evidence_bundle.json"
    promotion_path = root / "strict_rc_promotion.json"
    attestation_validation_path = root / "attestation_validation.json"
    if not bundle_path.exists():
        return DesignPartnerFieldEvidenceSnapshot(
            generatedAtUtc=generated_at or datetime.now(UTC),
            status="missing",
            warnings=["FIELD_EVIDENCE_NOT_COLLECTED"],
        )
    try:
        bundle = FieldEvidenceBundle.model_validate_json(bundle_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return DesignPartnerFieldEvidenceSnapshot(
            generatedAtUtc=generated_at or datetime.now(UTC),
            status="blocked",
            latestBundlePath=str(bundle_path),
            blockingReasons=[f"FIELD_EVIDENCE_BUNDLE_INVALID:{type(exc).__name__}"],
        )
    attestation_status: Literal["missing", "valid", "invalid", "blocked"] = "missing"
    if attestation_validation_path.exists():
        try:
            attestation = OperatorAttestationValidationResult.model_validate_json(
                attestation_validation_path.read_text(encoding="utf-8")
            )
            attestation_status = attestation.status
        except Exception:
            attestation_status = "invalid"
    strict_rc_status: Literal["ready", "conditional", "blocked", "missing"] = "missing"
    promotion_blockers: list[str] = []
    promotion_warnings: list[str] = []
    if promotion_path.exists():
        try:
            from imperaos.control_plane.strict_rc_promotion import StrictRCPromotionReport

            promotion = StrictRCPromotionReport.model_validate_json(
                promotion_path.read_text(encoding="utf-8")
            )
            strict_rc_status = promotion.status
            promotion_blockers = promotion.blockers
            promotion_warnings = promotion.warnings
        except Exception:
            strict_rc_status = "blocked"
            promotion_blockers = ["STRICT_RC_PROMOTION_REPORT_INVALID"]
    status = (
        "ready"
        if strict_rc_status == "ready"
        else "blocked"
        if promotion_blockers
        else "conditional"
    )
    return DesignPartnerFieldEvidenceSnapshot(
        generatedAtUtc=generated_at or datetime.now(UTC),
        status=status,
        mode=bundle.mode,
        sessionId=bundle.session_id,
        rawPersistence=bundle.raw_persistence,
        attestationStatus=attestation_status,
        strictRcStatus=strict_rc_status,
        itemCount=len(bundle.items),
        blockedClaims=[
            claim
            for claim, claim_status in bundle.claim_boundaries.items()
            if claim_status in {"blocked", "deferred"}
        ],
        latestBundlePath=str(bundle_path),
        latestAttestationPath=str(attestation_validation_path)
        if attestation_validation_path.exists()
        else None,
        latestPromotionPath=str(promotion_path) if promotion_path.exists() else None,
        blockingReasons=sorted(set(bundle.blocking_reasons + promotion_blockers)),
        warnings=sorted(set(bundle.warnings + promotion_warnings)),
    )


def load_field_session(path: Path) -> FieldEvidenceSession:
    return FieldEvidenceSession.model_validate_json(Path(path).read_text(encoding="utf-8"))


def load_field_bundle(path: Path) -> FieldEvidenceBundle:
    return FieldEvidenceBundle.model_validate_json(Path(path).read_text(encoding="utf-8"))


def write_attestation_template(
    *,
    session: FieldEvidenceSession,
    bundle: FieldEvidenceBundle,
    output_path: Path,
    release_pack_id: str = "design-partner-rc-v1",
) -> Path:
    payload = {
        "schemaVersion": "imperaos-non-developer-operator-attestation/v2",
        "sessionId": session.session_id,
        "releasePackId": release_pack_id,
        "targetEnvironmentLabelHash": session.target_environment.environment_label_hash,
        "bundleSha256": bundle.bundle_sha256,
        "operatorDisplayName": "TODO_NON_DEVELOPER_OPERATOR",
        "operatorRole": "TODO_OPERATOR_ROLE",
        "nonDeveloperOperator": False,
        "reviewedRunbook": False,
        "completedValidation": False,
        "signedAtUtc": datetime.now(UTC).isoformat(),
        "notesRedacted": "TODO_REDACTED_NOTES",
    }
    _write_json(output_path, payload)
    return output_path


def build_design_partner_field_pack(
    *,
    field_root: Path,
    rc_root: Path,
    output_root: Path,
    config: RuntimeConfig,
    now: datetime | None = None,
) -> DesignPartnerFieldPackManifest:
    _ = config
    output_root.mkdir(parents=True, exist_ok=True)
    promotion_path = Path(field_root) / "strict_rc_promotion.json"
    bundle_path = Path(field_root) / "target_evidence_bundle.json"
    attestation_path = Path(field_root) / "attestation_validation.json"
    blockers = []
    warnings = []
    status: Literal["ready", "conditional", "blocked"] = "conditional"
    session_id = None
    if bundle_path.exists():
        bundle = load_field_bundle(bundle_path)
        session_id = bundle.session_id
        warnings.extend(bundle.warnings)
        blockers.extend(bundle.blocking_reasons)
    else:
        blockers.append("FIELD_EVIDENCE_BUNDLE_MISSING")
    if promotion_path.exists():
        from imperaos.control_plane.strict_rc_promotion import StrictRCPromotionReport

        promotion = StrictRCPromotionReport.model_validate_json(
            promotion_path.read_text(encoding="utf-8")
        )
        status = promotion.status
        blockers.extend(promotion.blockers)
        warnings.extend(promotion.warnings)
    else:
        warnings.append("STRICT_RC_PROMOTION_MISSING")
    manifest = DesignPartnerFieldPackManifest(
        status="blocked" if blockers else status,
        sessionId=session_id,
        fieldRoot=str(field_root),
        rcRoot=str(rc_root),
        strictRcReportPath=str(promotion_path) if promotion_path.exists() else None,
        bundlePath=str(bundle_path) if bundle_path.exists() else None,
        attestationValidationPath=str(attestation_path) if attestation_path.exists() else None,
        generatedAtUtc=now or datetime.now(UTC),
        blockingReasons=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
    )
    _write_json(
        output_root / "field_pack_manifest.json", manifest.model_dump(mode="json", by_alias=True)
    )
    (output_root / "FIELD_EVIDENCE_CLOSURE_REPORT.md").write_text(
        _field_pack_markdown(manifest), encoding="utf-8"
    )
    return manifest


def _safe_environment_label(value: str) -> str:
    label = value.strip()
    if not label:
        raise ValueError("TARGET_ENVIRONMENT_LABEL_MISSING")
    if "@" in label or re.search(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", label):
        label = "redacted-target-environment"
    label = re.sub(r"[^a-zA-Z0-9_.:-]+", "-", label)[:80].strip("-")
    return label or "redacted-target-environment"


def _git_commit() -> str:
    import subprocess

    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    tmp.replace(path)


def _copy_or_summarize(source: Path, dest: Path, *, kind: str) -> Path:
    if source.is_file():
        shutil.copy2(source, dest)
        return dest
    paths = sorted(path for path in source.rglob("*.json") if path.is_file())[:20]
    payload = {
        "schemaVersion": "control-plane.field-evidence-directory-summary/v1",
        "kind": kind,
        "fileCount": len(paths),
        "hashes": [
            {"path": str(path.relative_to(source)), "sha256": f"sha256:{file_sha256(path)}"}
            for path in paths
        ],
        "rawPersistence": False,
    }
    _write_json(dest, payload)
    return dest


def _field_item(
    *,
    source: Path,
    root: Path,
    kind: str,
    generated_at: datetime,
    required_for_strict_rc: bool,
) -> FieldEvidenceItem:
    relative = source.relative_to(root)
    artifact_hash = canonical_json_hash({"path": str(relative)}, prefixed=False)[:10]
    return FieldEvidenceItem(
        artifactId=f"field-{kind}-{artifact_hash}",
        kind=kind,
        relativePath=str(relative),
        sha256=f"sha256:{file_sha256(source)}",
        sizeBytes=source.stat().st_size,
        generatedAtUtc=generated_at,
        producer="imperaos.control_plane.field_evidence",
        redactionStatus="redacted",
        rawPersistence=False,
        signatureStatus="missing",
        requiredForStrictRc=required_for_strict_rc,
    )


def _kind_for_path(path: Path) -> str:
    name = path.name
    if name == "session.json":
        return "session_manifest"
    if name == "claim_guard_matrix.json":
        return "claim_guard_matrix"
    if name == "governed_pilot_workflow_summary.json":
        return "governed_pilot_workflow_report"
    if name == "memory_policy_enforcement_summary.json":
        return "memory_policy_enforcement_summary"
    if name == "security_posture_summary.json":
        return "security_posture_summary"
    if name == "support_bundle_manifest.json":
        return "support_bundle_manifest"
    if name == "provider_runtime_summary.json":
        return "provider_runtime_summary"
    if name == "evidence_index_manifest.json":
        return "evidence_index_manifest"
    return "field_evidence_artifact"


def _bundle_hash(bundle: FieldEvidenceBundle) -> str:
    payload = bundle.model_dump(mode="json", by_alias=True)
    payload["bundleSha256"] = "sha256:pending"
    return canonical_json_hash(payload)


def _contains_secret_marker(items: list[FieldEvidenceItem], root: Path) -> bool:
    for item in items:
        text = (root / item.relative_path).read_text(encoding="utf-8", errors="ignore")
        if any(marker.lower() in text.lower() for marker in SECRET_MARKERS):
            return True
    return False


def _field_pack_markdown(manifest: DesignPartnerFieldPackManifest) -> str:
    lines = [
        "# Design Partner Field Evidence Closure",
        "",
        f"- Status: `{manifest.status}`",
        f"- Session: `{manifest.session_id or 'missing'}`",
        f"- Bundle: `{manifest.bundle_path or 'missing'}`",
        f"- Strict RC: `{manifest.strict_rc_report_path or 'missing'}`",
        "",
    ]
    if manifest.blocking_reasons:
        lines.append("## Blocking Reasons")
        lines.extend(f"- `{reason}`" for reason in manifest.blocking_reasons)
        lines.append("")
    if manifest.warnings:
        lines.append("## Warnings")
        lines.extend(f"- `{reason}`" for reason in manifest.warnings)
        lines.append("")
    return "\n".join(lines)
