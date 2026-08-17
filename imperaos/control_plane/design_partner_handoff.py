from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator

from imperaos.control_plane.pilot_ops_drill import (
    PilotOpsDrillReport,
    load_pilot_ops_drill_report,
)
from imperaos.control_plane.release_train import (
    ClaimBoundarySummary,
    ReleaseTrainVerificationReport,
    build_release_train_manifest,
    load_release_train_manifest,
    verify_release_train,
    write_release_train_manifest,
    write_release_train_verification,
)
from imperaos.control_plane.storage import file_sha256
from imperaos.control_plane.strict_rc_promotion import StrictRCPromotionReport
from imperaos.memory.models import StrictModel

HandoffStatus = Literal["ready", "conditional", "blocked"]
SECRET_RE = re.compile(r"(sk-|ghp_|xoxb-|api_key|token=|password=|private_key|BEGIN RAW)", re.I)


class ArtifactRef(StrictModel):
    artifact_id: str = Field(alias="artifactId")
    path: str
    sha256: str | None = None
    required: bool = True
    exists: bool = True

    @field_validator("path")
    @classmethod
    def _path_safe(cls, value: str) -> str:
        path = Path(value)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("artifact path must be repo-relative")
        return value


class HandoffComponentSummary(StrictModel):
    status: str
    path: str | None = None
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class DesignPartnerHandoffManifest(StrictModel):
    schema_version: Literal["control-plane.design-partner-handoff/v1"] = Field(
        default="control-plane.design-partner-handoff/v1",
        alias="schemaVersion",
    )
    generated_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        alias="generatedAtUtc",
    )
    status: HandoffStatus
    profile: str
    environment_label: str = Field(alias="environmentLabel")
    release_train: HandoffComponentSummary = Field(alias="releaseTrain")
    strict_rc: HandoffComponentSummary = Field(alias="strictRc")
    field_evidence: HandoffComponentSummary = Field(alias="fieldEvidence")
    operator_attestation: HandoffComponentSummary = Field(alias="operatorAttestation")
    first_run_drill: HandoffComponentSummary = Field(alias="firstRunDrill")
    support_bundle: ArtifactRef | None = Field(default=None, alias="supportBundle")
    claim_boundaries: ClaimBoundarySummary = Field(alias="claimBoundaries")
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class DesignPartnerHandoffVerificationReport(StrictModel):
    schema_version: Literal["control-plane.design-partner-handoff-verification/v1"] = Field(
        default="control-plane.design-partner-handoff-verification/v1",
        alias="schemaVersion",
    )
    generated_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        alias="generatedAtUtc",
    )
    status: HandoffStatus
    manifest_path: str = Field(alias="manifestPath")
    artifact_count: int = Field(default=0, alias="artifactCount")
    missing_artifacts: list[str] = Field(default_factory=list, alias="missingArtifacts")
    hash_mismatches: list[str] = Field(default_factory=list, alias="hashMismatches")
    raw_leak_detected: bool = Field(default=False, alias="rawLeakDetected")
    secret_leak_detected: bool = Field(default=False, alias="secretLeakDetected")
    unsupported_claim_allowed: bool = Field(default=False, alias="unsupportedClaimAllowed")
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class DesignPartnerHandoffSnapshot(StrictModel):
    schema_version: Literal["control-plane.design-partner-handoff-snapshot/v1"] = Field(
        default="control-plane.design-partner-handoff-snapshot/v1",
        alias="schemaVersion",
    )
    status: Literal["ready", "conditional", "blocked", "missing"] = "missing"
    handoff_pack_path: str | None = Field(default=None, alias="handoffPackPath")
    release_train_status: str = Field(default="missing", alias="releaseTrainStatus")
    first_run_drill_status: str = Field(default="missing", alias="firstRunDrillStatus")
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    last_generated_at_utc: datetime | None = Field(default=None, alias="lastGeneratedAtUtc")
    claim_boundary_summary: dict[str, str] = Field(
        default_factory=dict,
        alias="claimBoundarySummary",
    )


def build_design_partner_handoff_pack(
    *,
    profile: str,
    output_root: Path,
    environment_label: str,
    artifact_root: Path = Path("artifacts"),
    release_train_report: ReleaseTrainVerificationReport | None = None,
    drill_report: PilotOpsDrillReport | None = None,
    now: datetime | None = None,
) -> DesignPartnerHandoffManifest:
    output_root = Path(output_root)
    artifact_root = Path(artifact_root)
    _guard_output_root(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    release_train_report = release_train_report or _load_or_build_release_train(
        profile=profile,
        output_root=output_root,
        artifact_root=artifact_root,
    )
    drill_report = drill_report or _load_drill(output_root)
    _write_json(
        output_root / "RELEASE_TRAIN_REPORT.json",
        release_train_report.model_dump(mode="json", by_alias=True),
    )
    _write_json(
        output_root / "PILOT_OPS_DRILL_REPORT.json",
        drill_report.model_dump(mode="json", by_alias=True),
    )
    strict_rc = _load_strict_rc(artifact_root / "design-partner-field-evidence")
    artifacts = _artifact_refs(output_root=output_root, artifact_root=artifact_root)
    support = next(
        (artifact for artifact in artifacts if artifact.artifact_id == "support-bundle"), None
    )
    blockers: list[str] = []
    warnings: list[str] = []
    if release_train_report.status == "blocked":
        blockers.append("RELEASE_TRAIN_BLOCKED")
    elif release_train_report.status == "conditional":
        warnings.append("RELEASE_TRAIN_CONDITIONAL")
    if strict_rc.status == "blocked":
        blockers.append("STRICT_RC_BLOCKED")
    elif strict_rc.status != "ready":
        warnings.append("STRICT_RC_NOT_READY")
    if drill_report.status == "blocked":
        blockers.append("PILOT_OPS_DRILL_BLOCKED")
    elif drill_report.status == "conditional":
        warnings.append("PILOT_OPS_DRILL_CONDITIONAL")
    missing_required = [
        artifact.artifact_id for artifact in artifacts if artifact.required and not artifact.exists
    ]
    warnings.extend(f"HANDOFF_ARTIFACT_MISSING:{item}" for item in missing_required)
    if (
        release_train_report.status == "pass"
        and strict_rc.status == "ready"
        and drill_report.status == "pass"
        and not missing_required
    ):
        status: HandoffStatus = "ready"
    elif blockers:
        status = "blocked"
    else:
        status = "conditional"
    manifest = DesignPartnerHandoffManifest(
        generatedAtUtc=now or datetime.now(UTC),
        status=status,
        profile=profile,
        environmentLabel=environment_label,
        releaseTrain=HandoffComponentSummary(
            status=release_train_report.status,
            path=_manifest_path(output_root / "RELEASE_TRAIN_REPORT.json"),
            blockers=release_train_report.blockers,
            warnings=release_train_report.warnings,
        ),
        strictRc=HandoffComponentSummary(
            status=strict_rc.status,
            path=_manifest_path(
                artifact_root / "design-partner-field-evidence" / "strict_rc_promotion.json"
            ),
            blockers=strict_rc.blockers,
            warnings=strict_rc.warnings,
        ),
        fieldEvidence=HandoffComponentSummary(
            status=strict_rc.target_evidence_status,
            path=_manifest_path(
                artifact_root / "design-partner-field-evidence" / "target_evidence_bundle.json"
            ),
        ),
        operatorAttestation=HandoffComponentSummary(
            status=strict_rc.attestation_status,
            path=_manifest_path(
                artifact_root / "design-partner-field-evidence" / "attestation_validation.json"
            ),
        ),
        firstRunDrill=HandoffComponentSummary(
            status=drill_report.status,
            path=_manifest_path(output_root / "PILOT_OPS_DRILL_REPORT.json"),
            blockers=drill_report.blockers,
            warnings=drill_report.warnings,
        ),
        supportBundle=support,
        claimBoundaries=release_train_report_to_claim_boundaries(output_root),
        artifacts=artifacts,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
    )
    _write_json(output_root / "manifest.json", manifest.model_dump(mode="json", by_alias=True))
    _write_markdown_files(output_root, manifest)
    return manifest


def verify_design_partner_handoff_pack(
    *,
    manifest_path: Path,
    strict: bool = False,
) -> DesignPartnerHandoffVerificationReport:
    path = Path(manifest_path)
    blockers: list[str] = []
    warnings: list[str] = []
    if not path.exists():
        return DesignPartnerHandoffVerificationReport(
            status="blocked",
            manifestPath=str(path),
            blockers=["MANIFEST_MISSING"],
        )
    try:
        manifest = DesignPartnerHandoffManifest.model_validate_json(
            path.read_text(encoding="utf-8")
        )
    except Exception as exc:
        return DesignPartnerHandoffVerificationReport(
            status="blocked",
            manifestPath=str(path),
            blockers=[f"MANIFEST_INVALID:{type(exc).__name__}"],
        )
    root = path.parent
    missing: list[str] = []
    mismatches: list[str] = []
    secret_leak = _scan_secret(path)
    for artifact in manifest.artifacts:
        artifact_path = _resolve_artifact_path(root=root, artifact_path=artifact.path)
        if not artifact_path.exists():
            if artifact.required:
                missing.append(artifact.artifact_id)
            continue
        if artifact.sha256 and f"sha256:{file_sha256(artifact_path)}" != artifact.sha256:
            mismatches.append(artifact.artifact_id)
        secret_leak = secret_leak or _scan_secret(artifact_path)
    if missing:
        warnings.extend(f"HANDOFF_ARTIFACT_MISSING:{item}" for item in missing)
    if mismatches:
        blockers.extend(f"HANDOFF_ARTIFACT_HASH_MISMATCH:{item}" for item in mismatches)
    if secret_leak:
        blockers.append("HANDOFF_SECRET_OR_RAW_MARKER_DETECTED")
    if manifest.claim_boundaries.unsupported_claim_allowed:
        blockers.append("UNSUPPORTED_CLAIM_ALLOWED")
    if manifest.status == "ready" and (
        manifest.strict_rc.status != "ready"
        or manifest.operator_attestation.status != "valid"
        or manifest.field_evidence.status != "pass"
    ):
        blockers.append("FALSE_READY_HANDOFF_CLAIM")
    if strict and manifest.status != "ready":
        blockers.append("HANDOFF_NOT_READY_STRICT")
    status: HandoffStatus = (
        "blocked"
        if blockers
        else "conditional"
        if warnings or manifest.status != "ready"
        else "ready"
    )
    return DesignPartnerHandoffVerificationReport(
        status=status,
        manifestPath=str(path),
        artifactCount=len(manifest.artifacts),
        missingArtifacts=missing,
        hashMismatches=mismatches,
        rawLeakDetected=secret_leak,
        secretLeakDetected=secret_leak,
        unsupportedClaimAllowed=manifest.claim_boundaries.unsupported_claim_allowed,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings + manifest.warnings)),
    )


def build_design_partner_handoff_snapshot(
    *,
    artifact_root: Path = Path("artifacts"),
) -> DesignPartnerHandoffSnapshot:
    manifest_path = Path(artifact_root) / "design-partner-handoff" / "manifest.json"
    if not manifest_path.exists():
        return DesignPartnerHandoffSnapshot(
            status="missing",
            warnings=["DESIGN_PARTNER_HANDOFF_MISSING"],
        )
    try:
        manifest = DesignPartnerHandoffManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
    except Exception as exc:
        return DesignPartnerHandoffSnapshot(
            status="blocked",
            handoffPackPath=str(manifest_path),
            blockers=[f"DESIGN_PARTNER_HANDOFF_INVALID:{type(exc).__name__}"],
        )
    return DesignPartnerHandoffSnapshot(
        status=manifest.status,
        handoffPackPath=str(manifest_path),
        releaseTrainStatus=manifest.release_train.status,
        firstRunDrillStatus=manifest.first_run_drill.status,
        blockers=manifest.blockers,
        warnings=manifest.warnings,
        lastGeneratedAtUtc=manifest.generated_at_utc,
        claimBoundarySummary={
            "publicDesktop": manifest.claim_boundaries.public_desktop,
            "liveComputerUse": manifest.claim_boundaries.live_computer_use,
            "approvalFreeIrreversibleMutation": (
                manifest.claim_boundaries.approval_free_irreversible_mutation
            ),
        },
    )


def load_design_partner_handoff_manifest(path: Path) -> DesignPartnerHandoffManifest:
    return DesignPartnerHandoffManifest.model_validate_json(Path(path).read_text(encoding="utf-8"))


def release_train_report_to_claim_boundaries(output_root: Path) -> ClaimBoundarySummary:
    manifest_path = output_root / "release_train_manifest.json"
    if manifest_path.exists():
        return load_release_train_manifest(manifest_path).claim_boundaries
    manifest = build_release_train_manifest(profile="enterprise")
    return manifest.claim_boundaries


def _load_or_build_release_train(
    *,
    profile: str,
    output_root: Path,
    artifact_root: Path,
) -> ReleaseTrainVerificationReport:
    manifest_path = output_root / "release_train_manifest.json"
    if manifest_path.exists():
        manifest = load_release_train_manifest(manifest_path)
    else:
        manifest = build_release_train_manifest(profile=profile, artifact_root=artifact_root)
        write_release_train_manifest(manifest=manifest, output_path=manifest_path)
    report = verify_release_train(manifest, manifest_path=manifest_path)
    write_release_train_verification(
        report=report,
        output_path=output_root / "RELEASE_TRAIN_REPORT.json",
    )
    return report


def _load_drill(output_root: Path) -> PilotOpsDrillReport:
    path = output_root / "PILOT_OPS_DRILL_REPORT.json"
    if path.exists():
        return load_pilot_ops_drill_report(path)
    from imperaos.control_plane.pilot_ops_drill import run_pilot_ops_drill

    return run_pilot_ops_drill(profile="enterprise", output_root=output_root)


def _load_strict_rc(field_root: Path) -> StrictRCPromotionReport:
    path = field_root / "strict_rc_promotion.json"
    if path.exists():
        return StrictRCPromotionReport.model_validate_json(path.read_text(encoding="utf-8"))
    return StrictRCPromotionReport(
        status="conditional",
        ready=False,
        sessionId="missing",
        mode="rehearsal",
        targetEvidenceStatus="conditional",
        attestationStatus="missing",
        claimGuardStatus="pass",
        governedWorkflowStatus="missing",
        supportBundleStatus="missing",
        securityBaselineStatus="missing",
        warnings=["STRICT_RC_PROMOTION_MISSING"],
    )


def _artifact_refs(*, output_root: Path, artifact_root: Path) -> list[ArtifactRef]:
    paths = [
        ("release-train-report", output_root / "RELEASE_TRAIN_REPORT.json", True),
        ("pilot-ops-drill", output_root / "PILOT_OPS_DRILL_REPORT.json", True),
        (
            "strict-rc-promotion",
            artifact_root / "design-partner-field-evidence" / "strict_rc_promotion.json",
            True,
        ),
        (
            "field-evidence-bundle",
            artifact_root / "design-partner-field-evidence" / "target_evidence_bundle.json",
            True,
        ),
        ("support-bundle", artifact_root / "support_bundle_manifest.json", True),
        ("security-posture", artifact_root / "security_posture.json", True),
    ]
    refs: list[ArtifactRef] = []
    for artifact_id, path, required in paths:
        exists = path.exists()
        refs.append(
            ArtifactRef(
                artifactId=artifact_id,
                path=_manifest_path(path),
                exists=exists,
                required=required,
                sha256=f"sha256:{file_sha256(path)}" if exists and path.is_file() else None,
            )
        )
    return refs


def _write_markdown_files(output_root: Path, manifest: DesignPartnerHandoffManifest) -> None:
    _write_text(
        output_root / "DESIGN_PARTNER_HANDOFF_README.md",
        "\n".join(
            [
                "# Design Partner Handoff",
                "",
                f"- Status: `{manifest.status}`",
                f"- Environment: `{manifest.environment_label}`",
                f"- Release train: `{manifest.release_train.status}`",
                f"- First-run drill: `{manifest.first_run_drill.status}`",
                "",
            ]
        ),
    )
    _write_text(
        output_root / "FIRST_RUN_OPERATOR_CHECKLIST.md",
        "# First-Run Operator Checklist\n\n"
        "1. Verify the handoff manifest.\n"
        "2. Review the claim boundary card.\n"
        "3. Run the pilot operations drill.\n"
        "4. Stop on any blocked status.\n",
    )
    _write_text(
        output_root / "CLAIM_BOUNDARY_CARD.md",
        "# Claim Boundary Card\n\n"
        f"- Public desktop: `{manifest.claim_boundaries.public_desktop}`\n"
        f"- Live computer-use: `{manifest.claim_boundaries.live_computer_use}`\n"
        "- Public desktop release, live computer-use, and destructive mutation "
        "remain out of scope.\n",
    )
    _write_text(
        output_root / "SUPPORT_ESCALATION_GUIDE.md",
        "# Support Escalation Guide\n\n"
        "- Include manifest path, artifact hashes, blockers, and warnings.\n"
        "- Do not include raw prompts, responses, screenshots, secrets, or PII.\n",
    )


def _guard_output_root(output_root: Path) -> None:
    parts = output_root.resolve().parts
    if "artifacts" not in parts:
        raise ValueError("handoff output_root must be under artifacts")


def _manifest_path(path: Path) -> str:
    path = Path(path)
    if not path.is_absolute():
        return str(path)
    parts = path.parts
    if "artifacts" in parts:
        index = parts.index("artifacts")
        return str(Path(*parts[index:]))
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return path.name


def _resolve_artifact_path(*, root: Path, artifact_path: str) -> Path:
    path = Path(artifact_path)
    candidates = [
        root / path,
        root.parent.parent / path,
        path,
    ]
    return next((candidate for candidate in candidates if candidate.exists()), candidates[0])


def _scan_secret(path: Path) -> bool:
    if path.is_dir():
        return any(_scan_secret(child) for child in path.rglob("*") if child.is_file())
    if path.suffix.lower() in {".png", ".jpg", ".jpeg"}:
        return True
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    return bool(SECRET_RE.search(text))


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)
