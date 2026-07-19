from __future__ import annotations

import json
import subprocess
from pathlib import Path

from imperaos.control_plane.storage import canonical_json_hash, file_sha256
from imperaos.release_decision.markdown import render_release_decision_summary
from imperaos.release_decision.models import (
    EvidenceRef,
    HumanSignoffVerificationReport,
    NoShipRegister,
    RcFreezeReconciliationReport,
    ReleaseDecisionDossier,
    ReleaseDecisionVerificationReport,
)
from imperaos.release_decision.no_ship import build_no_ship_register
from imperaos.release_decision.reconciler import (
    build_reconciliation_input,
    missing_reconciliation,
    reconcile_rc_freeze,
)
from imperaos.release_decision.scanner import scan_file
from imperaos.release_decision.signoff import DEFAULT_REQUIRED_ROLES, verify_human_signoffs


def build_release_decision_dossier(
    *,
    profile: str,
    branch: str | None,
    head_sha: str | None,
    reconciliation: RcFreezeReconciliationReport,
    no_ship_register: NoShipRegister,
    signoff_report: HumanSignoffVerificationReport,
    evidence_refs: list[EvidenceRef],
) -> ReleaseDecisionDossier:
    blockers = list(reconciliation.blocking_reasons)
    blockers.extend(
        item.reason_code
        for item in no_ship_register.items
        if item.status == "open" and item.severity == "blocker"
    )
    blockers.extend(signoff_report.blocking_reasons)
    signoff_status = signoff_report.status
    if blockers:
        status = "blocked"
        hat_a = "blocked"
        design_partner = "blocked"
    elif reconciliation.status != "ready" or signoff_status != "verified":
        status = "conditional"
        hat_a = "conditional"
        design_partner = "conditional"
    else:
        status = "approved_for_design_partner_rc"
        hat_a = "approved"
        design_partner = "approved"
    return ReleaseDecisionDossier(
        decisionId=f"rc-decision-{profile}",
        profile=profile,
        headSha=head_sha,
        branch=branch,
        status=status,
        hatAStatus=hat_a,
        hatBStatus="blocked_external_credentials",
        designPartnerRcStatus=design_partner,
        rcFreezeReconciliation=reconciliation,
        noShipRegister=no_ship_register,
        signoffStatus=signoff_status,
        requiredSignoffRoles=list(DEFAULT_REQUIRED_ROLES),
        evidenceRefs=evidence_refs,
        blockingReasons=sorted(set(blockers)),
        warnings=sorted(set(reconciliation.warnings + signoff_report.warnings)),
    )


def build_release_decision_from_artifacts(
    *,
    profile: str,
    artifact_root: Path,
    output_root: Path | None = None,
    signoff_root: Path | None = None,
) -> ReleaseDecisionDossier:
    root = Path(artifact_root)
    repo_root = Path.cwd()
    ledger = root / "release-gates" / "mainline-rc" / "gate_evidence_ledger.json"
    freeze = root / "mainline-rc-freeze" / "manifest.json"
    evidence_refs: list[EvidenceRef] = []
    if ledger.exists() and freeze.exists():
        reconciliation = reconcile_rc_freeze(
            build_reconciliation_input(
                gate_ledger_path=ledger,
                freeze_manifest_path=freeze,
                repo_root=repo_root,
                profile=profile,
            )
        )
        evidence_refs.extend(reconciliation.evidence_refs)
    else:
        missing = []
        if not ledger.exists():
            missing.append("GATE_LEDGER_MISSING")
        if not freeze.exists():
            missing.append("RC_FREEZE_MANIFEST_MISSING")
        reconciliation = missing_reconciliation(",".join(missing))
    dossier_hash = "0" * 64
    signoff_report = verify_human_signoffs(
        dossier_hash=dossier_hash,
        signoff_root=signoff_root or ((output_root or root / "rc-release-decision") / "signoff"),
    )
    no_ship = build_no_ship_register(
        gate_ledger_ready=reconciliation.status == "ready",
        rc_freeze_reconciled=reconciliation.status == "ready",
        signoff_verified=signoff_report.status == "verified",
    )
    return build_release_decision_dossier(
        profile=profile,
        branch=_git(["branch", "--show-current"]),
        head_sha=_git(["rev-parse", "HEAD"]),
        reconciliation=reconciliation,
        no_ship_register=no_ship,
        signoff_report=signoff_report,
        evidence_refs=evidence_refs,
    )


def verify_release_decision_dossier(
    dossier: ReleaseDecisionDossier,
    *,
    allow_conditional: bool = False,
    dossier_path: Path | None = None,
) -> ReleaseDecisionVerificationReport:
    blockers: list[str] = []
    warnings: list[str] = []
    if dossier.status == "blocked":
        blockers.extend(dossier.blocking_reasons or ["DOSSIER_STATUS_BLOCKED"])
    if dossier.status.startswith("approved") and dossier.signoff_status != "verified":
        blockers.append("APPROVED_WITHOUT_VERIFIED_SIGNOFF")
    if dossier.status.startswith("approved") and dossier.blocking_reasons:
        blockers.append("APPROVED_WITH_BLOCKERS")
    if dossier.hat_b_status == "approved":
        blockers.append("HAT_B_APPROVED_WITHOUT_PUBLIC_DESKTOP_EVIDENCE")
    if dossier.no_ship_register.blocking_count and dossier.status != "blocked":
        blockers.append("NO_SHIP_BLOCKERS_NOT_REFLECTED")
    if dossier_path:
        findings = scan_file(dossier_path)
        blockers.extend(findings)
        dossier_sha = file_sha256(dossier_path) if dossier_path.exists() else None
    else:
        dossier_sha = canonical_json_hash(
            dossier.model_dump(mode="json", by_alias=True),
            prefixed=False,
        )
    status = (
        "blocked"
        if blockers
        else "conditional"
        if dossier.status == "conditional"
        else "ready"
    )
    if status == "conditional" and not allow_conditional:
        warnings.append("CONDITIONAL_RELEASE_DECISION")
    return ReleaseDecisionVerificationReport(
        status=status,
        dossierSha256=dossier_sha,
        blockingReasons=sorted(set(blockers)),
        warnings=warnings,
        allowConditional=allow_conditional,
    )


def write_release_decision_pack(
    dossier: ReleaseDecisionDossier,
    *,
    output_root: Path,
) -> dict[str, object]:
    output_root.mkdir(parents=True, exist_ok=True)
    dossier_path = output_root / "release_decision_dossier.json"
    summary_path = output_root / "release_decision_summary.md"
    no_ship_path = output_root / "no_ship_register.json"
    reconciliation_path = output_root / "rc_freeze_reconciliation.json"
    dossier_path.write_text(
        json.dumps(dossier.model_dump(mode="json", by_alias=True), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    summary_path.write_text(render_release_decision_summary(dossier), encoding="utf-8")
    no_ship_path.write_text(
        json.dumps(
            dossier.no_ship_register.model_dump(mode="json", by_alias=True),
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    reconciliation_path.write_text(
        json.dumps(
            dossier.rc_freeze_reconciliation.model_dump(mode="json", by_alias=True),
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    sha_lines = []
    for path in [dossier_path, summary_path, no_ship_path, reconciliation_path]:
        sha_lines.append(f"{file_sha256(path)}  {path.name}")
    (output_root / "sha256sums.txt").write_text("\n".join(sha_lines) + "\n", encoding="utf-8")
    manifest = {
        "schemaVersion": "release-decision-pack-manifest/v1",
        "status": dossier.status,
        "dossierPath": str(dossier_path).replace("\\", "/"),
        "summaryPath": str(summary_path).replace("\\", "/"),
        "dossierSha256": file_sha256(dossier_path),
    }
    (output_root / "artifact_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return manifest


def export_release_decision_pack(*, dossier_path: Path, output_root: Path) -> dict[str, object]:
    dossier = ReleaseDecisionDossier.model_validate_json(dossier_path.read_text(encoding="utf-8"))
    return write_release_decision_pack(dossier, output_root=output_root)


def _git(args: list[str]) -> str | None:
    result = subprocess.run(
        ["git", *args],
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        shell=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None
