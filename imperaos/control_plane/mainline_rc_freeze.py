from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import Field

from imperaos.control_plane.mainline_stack import (
    MergeRehearsalReport,
    StackGraphVerificationReport,
)
from imperaos.control_plane.release_artifact_scan import ArtifactScanReport, scan_release_artifacts
from imperaos.control_plane.release_train import ClaimBoundarySummary
from imperaos.control_plane.storage import canonical_json_hash, file_sha256
from imperaos.memory.models import StrictModel
from imperaos.release.gate_verifier import verify_gate_evidence_ledger

RcFreezeStatus = Literal["ready", "conditional", "blocked"]


class GateEvidenceItem(StrictModel):
    gate_id: str = Field(alias="gateId")
    command: str
    status: Literal["pass", "conditional", "blocked", "missing"]
    artifact_path: str | None = Field(default=None, alias="artifactPath")
    sha256: str | None = None
    required: bool = True


class GateEvidenceSummary(StrictModel):
    schema_version: Literal["control-plane.gate-evidence-summary/v1"] = Field(
        default="control-plane.gate-evidence-summary/v1",
        alias="schemaVersion",
    )
    status: Literal["pass", "conditional", "blocked", "missing"]
    items: list[GateEvidenceItem] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class RcFreezeManifest(StrictModel):
    schema_version: Literal["control-plane.rc-freeze-manifest/v1"] = Field(
        default="control-plane.rc-freeze-manifest/v1",
        alias="schemaVersion",
    )
    generated_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        alias="generatedAtUtc",
    )
    freeze_id: str = Field(alias="freezeId")
    profile: str
    status: RcFreezeStatus
    evidence_mode: Literal["hash_only"] = Field(default="hash_only", alias="evidenceMode")
    raw_persistence: Literal[False] = Field(default=False, alias="rawPersistence")
    stack: dict[str, object]
    merge_rehearsal: dict[str, object] = Field(alias="mergeRehearsal")
    gate_evidence: dict[str, object] = Field(alias="gateEvidence")
    claim_boundaries: ClaimBoundarySummary = Field(alias="claimBoundaries")
    artifact_scan: dict[str, object] = Field(alias="artifactScan")
    manifest_sha256: str | None = Field(default=None, alias="manifestSha256")
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class RcFreezeVerificationReport(StrictModel):
    schema_version: Literal["control-plane.rc-freeze-verification/v1"] = Field(
        default="control-plane.rc-freeze-verification/v1",
        alias="schemaVersion",
    )
    generated_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        alias="generatedAtUtc",
    )
    status: RcFreezeStatus
    manifest_path: str = Field(alias="manifestPath")
    manifest_sha256: str | None = Field(default=None, alias="manifestSha256")
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class MainlineRcFreezeSnapshot(StrictModel):
    schema_version: Literal["control-plane.mainline-rc-freeze-snapshot/v1"] = Field(
        default="control-plane.mainline-rc-freeze-snapshot/v1",
        alias="schemaVersion",
    )
    status: Literal["missing", "conditional", "ready", "blocked"] = "missing"
    freeze_id: str | None = Field(default=None, alias="freezeId")
    manifest_path: str | None = Field(default=None, alias="manifestPath")
    stack_status: str = Field(default="missing", alias="stackStatus")
    merge_rehearsal_status: str = Field(default="missing", alias="mergeRehearsalStatus")
    gate_evidence_status: str = Field(default="missing", alias="gateEvidenceStatus")
    artifact_scan_status: str = Field(default="missing", alias="artifactScanStatus")
    evidence_mode: str = Field(default="hash_only", alias="evidenceMode")
    raw_persistence: bool = Field(default=False, alias="rawPersistence")
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    last_generated_at_utc: datetime | None = Field(default=None, alias="lastGeneratedAtUtc")


def build_gate_evidence_summary(
    *,
    artifact_root: Path = Path("artifacts"),
    required_gates: list[GateEvidenceItem] | None = None,
) -> GateEvidenceSummary:
    items = required_gates or [
        GateEvidenceItem(
            gateId="design-partner-handoff-gate",
            command="make design-partner-handoff-gate",
            status="missing",
        ),
        GateEvidenceItem(
            gateId="control-plane-gate",
            command="make control-plane-gate",
            status="missing",
        ),
    ]
    enriched: list[GateEvidenceItem] = []
    blockers: list[str] = []
    warnings: list[str] = []
    for item in items:
        status = item.status
        sha = item.sha256
        if item.artifact_path:
            path = Path(item.artifact_path)
            if not path.is_absolute():
                path = Path(artifact_root).parent / path
            if path.exists() and path.is_file():
                sha = f"sha256:{file_sha256(path)}"
            elif item.required:
                status = "missing"
        if item.required and status == "blocked":
            blockers.append(f"REQUIRED_GATE_BLOCKED:{item.gate_id}")
        elif item.required and status == "missing":
            warnings.append(f"REQUIRED_GATE_MISSING:{item.gate_id}")
        enriched.append(item.model_copy(update={"status": status, "sha256": sha}))
    return GateEvidenceSummary(
        status="blocked" if blockers else "conditional" if warnings else "pass",
        items=enriched,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
    )


def build_rc_freeze_manifest(
    *,
    profile: str,
    output_root: Path,
    stack_report: StackGraphVerificationReport,
    rehearsal_report: MergeRehearsalReport,
    gate_evidence: GateEvidenceSummary,
    claim_boundaries: ClaimBoundarySummary,
    artifact_scan: ArtifactScanReport | None = None,
    evidence_root: Path = Path("artifacts"),
    freeze_id: str | None = None,
) -> RcFreezeManifest:
    artifact_scan = artifact_scan or scan_release_artifacts(artifact_root=evidence_root)
    blockers: list[str] = []
    warnings: list[str] = []
    if stack_report.status == "blocked":
        blockers.extend(stack_report.blockers or ["STACK_BLOCKED"])
    elif stack_report.status == "conditional":
        warnings.extend(stack_report.warnings or ["STACK_CONDITIONAL"])
    if rehearsal_report.status == "blocked":
        blockers.extend(rehearsal_report.blockers or ["MERGE_REHEARSAL_BLOCKED"])
    if rehearsal_report.worktree_mutated:
        blockers.append("MERGE_REHEARSAL_MUTATED_WORKTREE")
    if gate_evidence.status == "blocked":
        blockers.extend(gate_evidence.blockers or ["GATE_EVIDENCE_BLOCKED"])
    elif gate_evidence.status in {"conditional", "missing"}:
        warnings.extend(gate_evidence.warnings or ["GATE_EVIDENCE_CONDITIONAL"])
    if artifact_scan.status == "blocked":
        blockers.extend(artifact_scan.blockers or ["ARTIFACT_SCAN_BLOCKED"])
    if claim_boundaries.unsupported_claim_allowed:
        blockers.append("UNSUPPORTED_CLAIM_ALLOWED")
    if claim_boundaries.public_desktop != "blocked":
        blockers.append("PUBLIC_DESKTOP_BOUNDARY_OPEN")
    if claim_boundaries.live_computer_use != "blocked":
        blockers.append("LIVE_COMPUTER_USE_BOUNDARY_OPEN")
    status: RcFreezeStatus = "blocked" if blockers else "conditional" if warnings else "ready"
    effective_freeze_id = freeze_id or _default_freeze_id(rehearsal_report.head_sha)
    manifest = RcFreezeManifest(
        freezeId=effective_freeze_id,
        profile=profile,
        status=status,
        stack=stack_report.model_dump(mode="json", by_alias=True),
        mergeRehearsal=rehearsal_report.model_dump(mode="json", by_alias=True),
        gateEvidence=gate_evidence.model_dump(mode="json", by_alias=True),
        claimBoundaries=claim_boundaries,
        artifactScan=artifact_scan.model_dump(mode="json", by_alias=True),
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
    )
    _ = output_root
    return manifest.model_copy(update={"manifest_sha256": _manifest_hash(manifest)})


def write_rc_freeze_manifest(manifest: RcFreezeManifest, output_root: Path) -> Path:
    output_root = Path(output_root)
    if "artifacts" not in output_root.parts:
        raise ValueError("RC freeze output root must be under artifacts")
    output_root.mkdir(parents=True, exist_ok=True)
    path = output_root / "manifest.json"
    _write_json(path, manifest.model_dump(mode="json", by_alias=True))
    _write_decision(output_root / "RC_FREEZE_DECISION.md", manifest)
    return path


def verify_rc_freeze_manifest(*, manifest_path: Path) -> RcFreezeVerificationReport:
    path = Path(manifest_path)
    blockers: list[str] = []
    warnings: list[str] = []
    if not path.exists():
        return RcFreezeVerificationReport(
            status="blocked",
            manifestPath=str(path),
            blockers=["MANIFEST_MISSING"],
        )
    try:
        manifest = RcFreezeManifest.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return RcFreezeVerificationReport(
            status="blocked",
            manifestPath=str(path),
            blockers=[f"MANIFEST_INVALID:{type(exc).__name__}"],
        )
    manifest_hash = f"sha256:{file_sha256(path)}"
    blockers.extend(manifest.blockers)
    warnings.extend(manifest.warnings)
    if manifest.raw_persistence:
        blockers.append("RAW_PERSISTENCE_ENABLED")
    if manifest.evidence_mode != "hash_only":
        blockers.append("EVIDENCE_MODE_NOT_HASH_ONLY")
    if manifest.status == "ready" and (
        blockers
        or manifest.stack.get("status") != "ready"
        or manifest.merge_rehearsal.get("status") != "pass"
        or manifest.gate_evidence.get("status") != "pass"
        or manifest.artifact_scan.get("status") != "pass"
        or manifest.claim_boundaries.unsupported_claim_allowed
    ):
        blockers.append("FALSE_READY_RC_FREEZE")
    status: RcFreezeStatus
    if blockers:
        status = "blocked"
    elif warnings or manifest.status != "ready":
        status = "conditional"
    else:
        status = "ready"
    return RcFreezeVerificationReport(
        status=status,
        manifestPath=str(path),
        manifestSha256=manifest_hash,
        blockers=sorted(set(blockers)),
        warnings=sorted(set(warnings)),
    )


def verify_rc_freeze_manifest_with_gate_ledger(
    *,
    manifest_path: Path,
    gate_ledger_path: Path,
    repo_root: Path = Path("."),
) -> RcFreezeVerificationReport:
    report = verify_rc_freeze_manifest(manifest_path=manifest_path)
    if report.status == "blocked":
        return report
    gate_report = verify_gate_evidence_ledger(ledger_path=gate_ledger_path, repo_root=repo_root)
    if gate_report.status == "blocked":
        return report.model_copy(
            update={
                "status": "blocked",
                "blockers": sorted(set(report.blockers + gate_report.reason_codes)),
            }
        )
    missing_gate_warnings = [
        item for item in report.warnings if item.startswith("REQUIRED_GATE_MISSING:")
    ]
    unresolved = [
        item.split(":", 1)[1]
        for item in missing_gate_warnings
        if item.split(":", 1)[1] in gate_report.missing_gate_ids
    ]
    remaining_warnings = [
        item for item in report.warnings if not item.startswith("REQUIRED_GATE_MISSING:")
    ]
    if gate_report.ready_for_rc_freeze and missing_gate_warnings and not unresolved:
        status: RcFreezeStatus = "ready" if not remaining_warnings else "conditional"
        return report.model_copy(update={"status": status, "warnings": remaining_warnings})
    return report.model_copy(
        update={
            "status": "conditional",
            "warnings": sorted(
                set(report.warnings + [f"RELEASE_GATE_LEDGER_{gate_report.status.upper()}"])
            ),
        }
    )


def build_mainline_rc_freeze_snapshot(
    *,
    artifact_root: Path = Path("artifacts"),
) -> MainlineRcFreezeSnapshot:
    manifest_path = Path(artifact_root) / "mainline-rc-freeze" / "manifest.json"
    if not manifest_path.exists():
        return MainlineRcFreezeSnapshot(
            status="missing",
            warnings=["MAINLINE_RC_FREEZE_MISSING"],
        )
    verification = verify_rc_freeze_manifest(manifest_path=manifest_path)
    if verification.status == "blocked":
        return MainlineRcFreezeSnapshot(
            status="blocked",
            manifestPath=str(manifest_path),
            blockers=verification.blockers,
            warnings=verification.warnings,
        )
    manifest = RcFreezeManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    return MainlineRcFreezeSnapshot(
        status=verification.status,
        freezeId=manifest.freeze_id,
        manifestPath=str(manifest_path),
        stackStatus=str(manifest.stack.get("status", "unknown")),
        mergeRehearsalStatus=str(manifest.merge_rehearsal.get("status", "unknown")),
        gateEvidenceStatus=str(manifest.gate_evidence.get("status", "unknown")),
        artifactScanStatus=str(manifest.artifact_scan.get("status", "unknown")),
        evidenceMode=manifest.evidence_mode,
        rawPersistence=manifest.raw_persistence,
        blockers=verification.blockers,
        warnings=verification.warnings,
        lastGeneratedAtUtc=manifest.generated_at_utc,
    )


def export_rc_freeze_pack(*, manifest_path: Path, output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(manifest_path, output)
    return output


def _manifest_hash(manifest: RcFreezeManifest) -> str:
    payload = manifest.model_dump(mode="json", by_alias=True)
    payload["manifestSha256"] = None
    return canonical_json_hash(payload)


def _default_freeze_id(head_sha: str | None) -> str:
    suffix = (head_sha or "unknown")[:8]
    return f"mainline-rc-freeze-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{suffix}"


def _write_json(path: Path, payload: object) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def _write_decision(path: Path, manifest: RcFreezeManifest) -> None:
    lines = [
        "# Mainline RC Freeze Decision",
        "",
        f"- Freeze ID: `{manifest.freeze_id}`",
        f"- Status: `{manifest.status}`",
        f"- Evidence mode: `{manifest.evidence_mode}`",
        f"- Raw persistence: `{manifest.raw_persistence}`",
        "",
        "## Blockers",
        "",
        *(f"- `{item}`" for item in manifest.blockers),
        "",
        "## Warnings",
        "",
        *(f"- `{item}`" for item in manifest.warnings),
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
