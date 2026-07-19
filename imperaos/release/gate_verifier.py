from __future__ import annotations

from pathlib import Path

from imperaos.control_plane.storage import file_sha256
from imperaos.release.gate_artifacts import resolve_artifact_path
from imperaos.release.gate_models import (
    GateArtifactRef,
    GateEvidenceLedger,
    GateEvidenceVerificationReport,
)
from imperaos.release.gate_scanner import scan_file_for_raw_or_secret


def verify_gate_evidence_ledger(
    *,
    ledger_path: Path,
    repo_root: Path,
) -> GateEvidenceVerificationReport:
    path = Path(ledger_path)
    if not path.exists():
        return GateEvidenceVerificationReport(
            status="blocked",
            reasonCodes=["LEDGER_MISSING"],
        )
    findings = scan_file_for_raw_or_secret(path)
    if findings:
        return GateEvidenceVerificationReport(
            status="blocked",
            secretOrRawFindings=findings,
            reasonCodes=["LEDGER_INVALID"],
        )
    try:
        ledger = GateEvidenceLedger.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception:
        return GateEvidenceVerificationReport(
            status="blocked",
            reasonCodes=["LEDGER_INVALID"],
        )
    missing_gate_ids = sorted(
        set(ledger.required_gate_ids) - {item.gate_id for item in ledger.gate_results}
    )
    missing_artifact_ids: list[str] = []
    tampered: list[str] = []
    secret_or_raw: list[str] = []
    for result in ledger.gate_results:
        missing_artifact_ids.extend(result.missing_artifact_requirements)
        secret_or_raw.extend(result.blocking_reasons)
        for artifact in result.artifact_refs:
            artifact_path = resolve_artifact_path(repo_root, artifact.path)
            if not artifact_path.exists():
                missing_artifact_ids.append(_normalized(artifact.path))
                continue
            if file_sha256(artifact_path) != artifact.sha256:
                tampered.append(_normalized(artifact.path))
            secret_or_raw.extend(scan_file_for_raw_or_secret(artifact_path))
    reason_codes: list[str] = []
    if missing_gate_ids:
        reason_codes.append("MISSING_REQUIRED_GATE")
    if missing_artifact_ids:
        reason_codes.append("MISSING_REQUIRED_ARTIFACT")
    if tampered:
        reason_codes.append("ARTIFACT_HASH_MISMATCH")
    if secret_or_raw:
        reason_codes.append("RAW_OR_SECRET_MARKER_FOUND")
    if tampered or secret_or_raw or ledger.status == "blocked":
        status = "blocked"
    elif missing_gate_ids or missing_artifact_ids or ledger.status in {"conditional", "fail"}:
        status = "conditional" if ledger.status != "fail" else "fail"
    else:
        status = "ready"
    return GateEvidenceVerificationReport(
        ledgerRef=GateArtifactRef(
            path=str(path).replace("\\", "/"),
            sha256=file_sha256(path),
            sizeBytes=path.stat().st_size,
            kind="json",
            scanStatus="pass",
        ),
        status=status,
        verifiedGateCount=len(ledger.gate_results),
        missingGateIds=missing_gate_ids,
        missingArtifactIds=sorted(set(missing_artifact_ids)),
        tamperedArtifactRefs=sorted(set(tampered)),
        secretOrRawFindings=sorted(set(secret_or_raw)),
        claimImpact="rc_freeze_ready" if status == "ready" else "rc_freeze_not_ready",
        readyForRcFreeze=status == "ready",
        reasonCodes=sorted(set(reason_codes)),
        warnings=ledger.warnings,
    )


def _normalized(value: str) -> str:
    return value.replace("\\", "/")
