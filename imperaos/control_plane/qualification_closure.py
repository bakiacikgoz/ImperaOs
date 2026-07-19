from __future__ import annotations

import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from imperaos import __version__
from imperaos.enterprise.qualification import (
    MIN_GREEN_SOAK_SECONDS,
    OPTIONAL_WORKLOADS,
    REQUIRED_WORKLOADS,
    evaluate_qualification_evidence,
    render_qualification_markdown,
)
from imperaos.enterprise.signing import load_signed_artifact, write_signed_json
from imperaos.runtime.config import RuntimeConfig

ENTERPRISE_HAT_A_CLOSURE_VERSION = "control-plane.enterprise-hat-a-closure/v1"
MAX_QUALIFICATION_EVIDENCE_AGE = timedelta(days=14)


class EnterpriseHatAEvidenceClosure(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    version: Literal["control-plane.enterprise-hat-a-closure/v1"] = (
        ENTERPRISE_HAT_A_CLOSURE_VERSION
    )
    closure_id: str
    profile: str = "enterprise"
    commit_sha: str
    generated_at_utc: datetime = Field(alias="generatedAtUtc")
    qualification_report_path: str = Field(alias="qualificationReportPath")
    signature_status: Literal["valid", "invalid", "missing"] = Field(alias="signatureStatus")
    signature_mode: str = Field(alias="signatureMode")
    baseline_status: Literal["pass", "fail", "conditional", "unknown"] = Field(
        alias="baselineStatus"
    )
    workload_status: Literal["pass", "fail", "partial", "unknown"] = Field(
        alias="workloadStatus"
    )
    claim_status: Literal["ready", "conditional", "blocked"] = Field(alias="claimStatus")
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")
    warnings: list[str] = Field(default_factory=list)
    artifact_path: str | None = Field(default=None, alias="artifactPath")
    markdown_path: str | None = Field(default=None, alias="markdownPath")


def generate_enterprise_hat_a_closure(
    *,
    profile: str,
    output_root: Path,
    qualification_root: Path | None = None,
    require_signature: bool = True,
    now: datetime | None = None,
    config: RuntimeConfig | None = None,
) -> EnterpriseHatAEvidenceClosure:
    """Produce a signed Enterprise Hat A closure artifact without opening live claims."""

    generated_at = now or datetime.now(UTC)
    resolved_config = config or RuntimeConfig.from_profile(profile)
    output_root.mkdir(parents=True, exist_ok=True)
    report_path = _resolve_qualification_report_path(qualification_root)

    blocking: list[str] = []
    warnings: list[str] = []
    signature_status: Literal["valid", "invalid", "missing"] = "missing"
    signature_mode = "missing"
    baseline_status: Literal["pass", "fail", "conditional", "unknown"] = "unknown"
    workload_status: Literal["pass", "fail", "partial", "unknown"] = "unknown"

    if profile != "enterprise":
        blocking.append("ENTERPRISE_PROFILE_REQUIRED")

    report_payload: dict[str, Any] | None = None
    if report_path is None:
        warnings.append("QUALIFICATION_REPORT_MISSING")
        resolved_report_path = "missing"
    else:
        resolved_report_path = str(report_path)
        signed = load_signed_artifact(path=report_path, config=resolved_config)
        signature_mode = str(signed.get("signature_mode") or "missing")
        report_payload = signed.get("data") if isinstance(signed.get("data"), dict) else None
        if bool(signed.get("signature_verified")) and signature_mode != "env_hmac_compat":
            signature_status = "valid"
        elif signature_mode == "env_hmac_compat":
            signature_status = "invalid"
            blocking.append("COMPAT_HMAC_NOT_ENTERPRISE_READY")
        elif signed.get("present") and signed.get("verified"):
            signature_status = "missing"
        else:
            signature_status = "invalid"

        if require_signature and signature_status != "valid":
            blocking.append("QUALIFICATION_SIGNATURE_INVALID")

        if report_payload is None:
            blocking.append("QUALIFICATION_REPORT_PAYLOAD_INVALID")
        else:
            baseline_status, workload_status = _evaluate_report_payload(report_payload)
            stale_reason = _stale_reason(report_payload, generated_at)
            if stale_reason is not None:
                blocking.append(stale_reason)
            if str(report_payload.get("profile") or "") != "enterprise":
                blocking.append("QUALIFICATION_PROFILE_MISMATCH")
            if baseline_status != "pass":
                blocking.append("ENTERPRISE_BASELINE_NOT_PASSING")
            if workload_status != "pass":
                blocking.append("ENTERPRISE_WORKLOADS_NOT_PASSING")
            warnings.extend(str(item) for item in report_payload.get("residual_risks") or [])

    claim_status: Literal["ready", "conditional", "blocked"]
    if blocking:
        claim_status = "blocked"
    elif report_path is None or signature_status == "missing":
        claim_status = "conditional"
    else:
        claim_status = "ready"

    closure = EnterpriseHatAEvidenceClosure(
        closure_id=f"hat_a_{generated_at.strftime('%Y%m%d%H%M%S')}",
        profile=profile,
        commit_sha=_git_commit(),
        generatedAtUtc=generated_at,
        qualificationReportPath=resolved_report_path,
        signatureStatus=signature_status,
        signatureMode=signature_mode,
        baselineStatus=baseline_status,
        workloadStatus=workload_status,
        claimStatus=claim_status,
        blockingReasons=sorted(set(blocking)),
        warnings=sorted(set(warnings)),
    )
    artifact_path = output_root / "enterprise_hat_a_closure.json"
    markdown_path = output_root / "ENTERPRISE_HAT_A_CLOSURE.md"
    _write_closure_artifact(
        closure=closure,
        path=artifact_path,
        config=resolved_config,
        status="ok" if closure.claim_status == "ready" else closure.claim_status,
    )
    markdown_path.write_text(render_enterprise_hat_a_closure_markdown(closure), encoding="utf-8")
    return closure.model_copy(
        update={"artifact_path": str(artifact_path), "markdown_path": str(markdown_path)}
    )


def verify_enterprise_hat_a_closure(
    *,
    input_path: Path,
    config: RuntimeConfig | None = None,
) -> dict[str, Any]:
    bundle = load_signed_artifact(path=input_path, config=config)
    data = bundle.get("data") if isinstance(bundle.get("data"), dict) else None
    blocking: list[str] = []
    if not bundle.get("present"):
        blocking.append("CLOSURE_ARTIFACT_MISSING")
    if not bundle.get("verified"):
        blocking.append(str(bundle.get("error_code") or "CLOSURE_INTEGRITY_INVALID"))
    if not bundle.get("signature_verified"):
        blocking.append("CLOSURE_SIGNATURE_INVALID")
    if data is None:
        blocking.append("CLOSURE_PAYLOAD_INVALID")
    else:
        closure = EnterpriseHatAEvidenceClosure.model_validate(data)
        blocking.extend(closure.blocking_reasons)
        if closure.claim_status != "ready":
            blocking.append(f"CLOSURE_NOT_READY:{closure.claim_status}")
    return {
        "version": "control-plane.enterprise-hat-a-closure-verify/v1",
        "inputPath": str(input_path),
        "status": "pass" if not blocking else "fail",
        "signatureVerified": bool(bundle.get("signature_verified")),
        "signatureMode": bundle.get("signature_mode"),
        "claimStatus": data.get("claimStatus") if isinstance(data, dict) else "blocked",
        "blockingReasons": sorted(set(blocking)),
    }


def write_pilot_qualification_fixture(
    *,
    output_root: Path,
    config: RuntimeConfig,
    now: datetime | None = None,
) -> Path:
    generated_at = now or datetime.now(UTC)
    output_root.mkdir(parents=True, exist_ok=True)
    payload = build_pilot_qualification_fixture_payload(now=generated_at)
    report_path = output_root / "qualification_report.json"
    write_signed_json(
        path=report_path,
        artifact="qualification_report",
        data=payload,
        config=config,
        purpose="qualification-report",
        status="ok",
    )
    (output_root / "QUALIFICATION_REPORT.md").write_text(
        render_qualification_markdown(payload),
        encoding="utf-8",
    )
    return report_path


def build_pilot_qualification_fixture_payload(
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    generated_at = now or datetime.now(UTC)
    workloads = [
        _workload_fixture(name=name, duration_seconds=MIN_GREEN_SOAK_SECONDS)
        for name in REQUIRED_WORKLOADS
    ]
    workloads.extend(
        _workload_fixture(name=name, duration_seconds=86_400, required=False)
        for name in OPTIONAL_WORKLOADS
    )
    evaluation = evaluate_qualification_evidence(
        qualification_payload={
            "profile": "enterprise",
            "workloads": workloads,
            "minimum_green_soak_seconds": MIN_GREEN_SOAK_SECONDS,
        }
    )
    return {
        "version": "1",
        "generated_at": _iso_z(generated_at),
        "runtime_version": __version__,
        "environment_summary": {
            "mode": "deterministic_pilot_rehearsal",
            "provider": "fixture",
            "cwd": str(Path.cwd()),
        },
        "profile": "enterprise",
        "signing_mode": "local_file",
        "identity_mode": "external_assertion",
        "qualification_evidence_mode": "deterministic_pilot_rehearsal",
        "minimum_green_soak_seconds": MIN_GREEN_SOAK_SECONDS,
        "workloads": workloads,
        "artifacts": {},
        **evaluation,
    }


def render_enterprise_hat_a_closure_markdown(
    closure: EnterpriseHatAEvidenceClosure,
) -> str:
    lines = [
        "# Enterprise Hat A Evidence Closure",
        "",
        f"- Status: `{closure.claim_status}`",
        f"- Profile: `{closure.profile}`",
        f"- Commit: `{closure.commit_sha}`",
        f"- Generated: `{closure.generated_at_utc.isoformat()}`",
        f"- Qualification report: `{closure.qualification_report_path}`",
        f"- Signature: `{closure.signature_status}` (`{closure.signature_mode}`)",
        f"- Baseline: `{closure.baseline_status}`",
        f"- Workloads: `{closure.workload_status}`",
        "",
        "## Blocking Reasons",
        "",
    ]
    if closure.blocking_reasons:
        lines.extend(f"- {item}" for item in closure.blocking_reasons)
    else:
        lines.append("- none")
    lines.extend(["", "## Warnings", ""])
    if closure.warnings:
        lines.extend(f"- {item}" for item in closure.warnings)
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "- Computer-use live execution remains blocked.",
            "- Public desktop installer claim remains blocked.",
            "- Dev HMAC compatibility signatures do not satisfy enterprise readiness.",
        ]
    )
    return "\n".join(lines) + "\n"


def _resolve_qualification_report_path(root: Path | None) -> Path | None:
    candidates = []
    if root is not None:
        root = Path(root)
        candidates.extend(
            [
                root / "qualification_report.json",
                root / "artifacts" / "qualification_report.json",
            ]
        )
        candidates.extend(sorted(root.glob("qualification-*/qualification_report.json")))
    candidates.append(Path("artifacts/qualification_report.json"))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _evaluate_report_payload(
    payload: dict[str, Any],
) -> tuple[
    Literal["pass", "fail", "conditional", "unknown"],
    Literal["pass", "fail", "partial", "unknown"],
]:
    if not payload:
        return "unknown", "unknown"
    evaluation = evaluate_qualification_evidence(qualification_payload=payload)
    baseline = "pass" if evaluation.get("qualification_status") == "pass" else "fail"
    workload = "pass" if evaluation.get("qualification_status") == "pass" else "partial"
    return baseline, workload


def _stale_reason(payload: dict[str, Any], now: datetime) -> str | None:
    generated = _parse_datetime(str(payload.get("generated_at") or ""))
    if generated is None:
        return "QUALIFICATION_GENERATED_AT_MISSING"
    if generated.tzinfo is None:
        generated = generated.replace(tzinfo=UTC)
    if now - generated > MAX_QUALIFICATION_EVIDENCE_AGE:
        return "QUALIFICATION_EVIDENCE_STALE"
    return None


def _workload_fixture(
    *,
    name: str,
    duration_seconds: int,
    required: bool = True,
) -> dict[str, Any]:
    return {
        "name": name,
        "purpose": "Design Partner Pilot deterministic qualification fixture.",
        "start_time": "2026-06-02T00:00:00Z",
        "end_time": "2026-06-02T06:00:00Z",
        "duration_seconds": duration_seconds,
        "execution_mode": "deterministic_controlled",
        "required_for_green": required,
        "support_classification": "supported" if required else "conditional",
        "pass_fail": "pass",
        "task_count_total": 3,
        "task_count_success": 3,
        "task_count_failed": 0,
        "failure_class_breakdown": {},
        "replay_verify_status": "pass",
        "signing_verify_status": "pass",
        "approval_latency_summary": {"count": 1, "p50_ms": 1200, "p95_ms": 1200},
        "provider_retry_count": 0,
        "stale_approval_count": 0,
        "stale_resume_count": 0,
        "resume_duplicate_suppressed_count": 0,
        "memory_conflict_count": 0,
        "serialized_due_to_policy_count": 0,
        "fallback_mode_count": 0,
        "operator_intervention_count": 0,
        "support_bundle_sufficient": True,
        "metrics_snapshot_sufficient": True,
        "unclear_errors": [],
        "runbook_gaps": [],
        "notes": [],
        "operational_followups": [],
        "terminal_status": "completed",
        "terminal_job_id": f"fixture-{name}",
        "resume_round_count": 1,
        "approval_rounds": [],
        "artifacts": {"workload_root": f"fixture/{name}"},
        "blocking_findings": [],
        "residual_risks": [],
        "evidence_verified": True,
    }


def _write_closure_artifact(
    *,
    closure: EnterpriseHatAEvidenceClosure,
    path: Path,
    config: RuntimeConfig,
    status: str,
) -> None:
    try:
        write_signed_json(
            path=path,
            artifact="enterprise_hat_a_closure",
            data=closure.model_dump(mode="json", by_alias=True),
            config=config,
            purpose="enterprise-hat-a-closure",
            status=status,
        )
    except Exception:  # noqa: BLE001
        write_signed_json(
            path=path,
            artifact="enterprise_hat_a_closure",
            data=closure.model_dump(mode="json", by_alias=True),
            config=None,
            purpose="enterprise-hat-a-closure",
            status="blocked",
        )


def _parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _iso_z(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _git_commit() -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.stdout.strip() if proc.returncode == 0 else "unknown"
