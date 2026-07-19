from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from imperaos.control_plane.models import (
    CodeIntelligenceFindingBucket,
    CodeIntelligenceSummary,
    DesignPartnerBetaStatus,
    PilotLaunchNextAction,
    PilotOperationsChecklistItem,
    PilotOperationsStatus,
    PilotOperationsTimelineEvent,
)

PILOT_OPERATIONS_VERSION = "control-plane.pilot-operations-artifacts/v1"


def build_code_intelligence_summary(
    *,
    evidence_root: str | Path = "artifacts",
    generated_at: datetime | None = None,
) -> CodeIntelligenceSummary:
    base = _artifact_base(evidence_root)
    artifact_root = base / "code-intelligence" / "fallow"
    path = artifact_root / "summary.json"
    payload = _read_json(path)
    if payload is None:
        return CodeIntelligenceSummary(
            generatedAtUtc=generated_at or datetime.now(UTC),
            status="missing",
            verdict="missing",
            artifactRoot=str(artifact_root),
            blockers=["FALLOW_SUMMARY_MISSING"],
            warnings=[],
        )

    buckets = [
        _finding_bucket("dead-code", "Dead code", payload.get("dead_code"), artifact_root),
        _finding_bucket("duplication", "Duplication", payload.get("duplication"), artifact_root),
        _finding_bucket("health", "Health", payload.get("health"), artifact_root),
        _finding_bucket(
            "boundaries",
            "Architecture boundaries",
            payload.get("boundaries"),
            artifact_root,
        ),
    ]
    secret_status = str(payload.get("secret_scan", {}).get("status", "unknown"))
    telemetry_disabled = payload.get("telemetry_disabled") is True
    boundary_violations = int(payload.get("boundaries", {}).get("total") or 0)
    blocking_reasons = [str(item) for item in payload.get("blocking_reasons", [])]
    if secret_status != "pass":
        blocking_reasons.append("FALLOW_SECRET_SCAN_FAILED")
    if not telemetry_disabled:
        blocking_reasons.append("FALLOW_TELEMETRY_NOT_DISABLED")
    if boundary_violations:
        blocking_reasons.append("FALLOW_BOUNDARY_VIOLATIONS")

    warnings = [str(item) for item in payload.get("warnings", [])]
    verdict = str(payload.get("verdict", "warn"))
    if verdict == "fail":
        blocking_reasons.append("FALLOW_VERDICT_FAILED")
    status = (
        "blocked"
        if blocking_reasons
        else "conditional"
        if warnings or verdict != "pass"
        else "ready"
    )
    return CodeIntelligenceSummary(
        generatedAtUtc=_parse_datetime(payload.get("generated_at"))
        or generated_at
        or datetime.now(UTC),
        status=status,
        verdict=verdict,
        tool=str(payload.get("tool", "fallow")),
        toolVersion=payload.get("tool_version"),
        artifactRoot=str(artifact_root),
        telemetryDisabled=telemetry_disabled,
        boundaryViolations=boundary_violations,
        secretScanStatus=secret_status,
        buckets=buckets,
        blockers=sorted(set(blocking_reasons)),
        warnings=warnings,
    )


def build_pilot_operations_status(
    *,
    evidence_root: str | Path = "artifacts",
    generated_at: datetime | None = None,
) -> PilotOperationsStatus:
    generated = generated_at or datetime.now(UTC)
    base = _artifact_base(evidence_root)
    output_root = base / "pilot-ops"
    pilot_manifest = _read_json(base / "design-partner-pilot" / "manifest.json")
    metrics = _read_json(base / "design-partner-pilot" / "pilot_metrics.json") or {}
    external_v1_1 = _read_json(base / "external-agent-v1-1" / "results.json")
    code_intelligence = build_code_intelligence_summary(
        evidence_root=base,
        generated_at=generated,
    )

    checklist = [
        _artifact_item(
            item_id="pilot-launch-pack",
            label="Pilot launch pack",
            path=base / "design-partner-pilot" / "manifest.json",
            payload=pilot_manifest,
            pass_values={"ready", "pass"},
        ),
        _artifact_item(
            item_id="external-agent-v1-1",
            label="External Agent Gateway v1.1",
            path=base / "external-agent-v1-1" / "results.json",
            payload=external_v1_1,
            pass_values={"pass"},
        ),
        PilotOperationsChecklistItem(
            itemId="code-intelligence",
            label="Fallow code intelligence",
            status=code_intelligence.status,
            detail=(
                f"verdict={code_intelligence.verdict}; "
                f"boundaries={code_intelligence.boundary_violations}"
            ),
            path=str(base / "code-intelligence" / "fallow" / "summary.json"),
            blocking=code_intelligence.status == "blocked",
        ),
        _safety_claim_item(pilot_manifest),
        _feedback_item(output_root / "pilot_feedback_bundle.json"),
    ]
    timeline = _timeline(
        base=base,
        checklist=checklist,
        generated_at=generated,
    )
    acceptance_metrics = _acceptance_metrics(
        metrics=metrics,
        external_v1_1=external_v1_1,
        code_intelligence=code_intelligence,
    )
    blockers = [
        item.item_id
        for item in checklist
        if item.blocking or item.status == "blocked"
    ]
    warnings = [
        item.item_id
        for item in checklist
        if item.status in {"conditional", "missing"} and item.item_id != "feedback-bundle"
    ]
    status = "blocked" if blockers else "conditional" if warnings else "ready"
    headline = (
        "Pilot operations are ready."
        if status == "ready"
        else "Pilot operations are blocked."
        if status == "blocked"
        else "Pilot operations are conditional."
    )
    return PilotOperationsStatus(
        generatedAtUtc=generated,
        status=status,
        headline=headline,
        artifactRoot=str(output_root),
        checklist=checklist,
        timeline=timeline,
        acceptanceMetrics=acceptance_metrics,
        feedbackBundlePath=str(output_root / "pilot_feedback_bundle.json"),
        nextActions=_next_actions(blockers=blockers, warnings=warnings),
        blockers=blockers,
        warnings=warnings,
    )


def build_design_partner_beta_status(
    *,
    evidence_root: str | Path = "artifacts",
    generated_at: datetime | None = None,
) -> DesignPartnerBetaStatus:
    generated = generated_at or datetime.now(UTC)
    base = _artifact_base(evidence_root)
    code_intelligence = build_code_intelligence_summary(
        evidence_root=base,
        generated_at=generated,
    )
    pilot_operations = build_pilot_operations_status(
        evidence_root=base,
        generated_at=generated,
    )
    external_v1_1 = _read_json(base / "external-agent-v1-1" / "results.json")
    ci_inventory = _read_json(base / "ci" / "node-action-inventory.json")
    pilot_manifest = _read_json(base / "design-partner-pilot" / "manifest.json")
    checks = [
        PilotOperationsChecklistItem(
            itemId="code-intelligence",
            label="Code intelligence",
            status=code_intelligence.status,
            detail=f"Fallow verdict {code_intelligence.verdict}",
            path=str(base / "code-intelligence" / "fallow" / "summary.json"),
            blocking=code_intelligence.status == "blocked",
        ),
        PilotOperationsChecklistItem(
            itemId="pilot-operations",
            label="Pilot operations loop",
            status=pilot_operations.status,
            detail=pilot_operations.headline,
            path=pilot_operations.feedback_bundle_path,
            blocking=pilot_operations.status == "blocked",
        ),
        _artifact_item(
            item_id="external-agent-v1-1",
            label="External Agent Gateway v1.1",
            path=base / "external-agent-v1-1" / "results.json",
            payload=external_v1_1,
            pass_values={"pass"},
        ),
        _artifact_item(
            item_id="ci-node24-inventory",
            label="CI Node action inventory",
            path=base / "ci" / "node-action-inventory.json",
            payload=ci_inventory,
            pass_values={"pass"},
        ),
        _safety_claim_item(pilot_manifest),
    ]
    blockers = [item.item_id for item in checks if item.blocking or item.status == "blocked"]
    warnings = [item.item_id for item in checks if item.status in {"conditional", "missing"}]
    status = "blocked" if blockers else "conditional" if warnings else "ready"
    headline = (
        "Design Partner Beta Operations Candidate is ready."
        if status == "ready"
        else "Design Partner Beta Operations Candidate is blocked."
        if status == "blocked"
        else "Design Partner Beta Operations Candidate is conditional."
    )
    return DesignPartnerBetaStatus(
        generatedAtUtc=generated,
        status=status,
        headline=headline,
        artifactRoot=str(base / "design-partner-beta"),
        codeIntelligence=code_intelligence,
        pilotOperations=pilot_operations,
        checks=checks,
        blockers=blockers,
        warnings=warnings,
    )


def generate_pilot_operations_artifacts(
    *,
    output_root: str | Path = "artifacts/pilot-ops",
    evidence_root: str | Path = "artifacts",
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    generated = generated_at or datetime.now(UTC)
    output = Path(output_root)
    output.mkdir(parents=True, exist_ok=True)
    feedback_path = output / "pilot_feedback_bundle.json"
    if not feedback_path.exists():
        _write_json(
            feedback_path,
            {
                "version": PILOT_OPERATIONS_VERSION,
                "generatedAtUtc": generated.isoformat(),
                "status": "pending",
                "redaction": "local_only_no_pii_no_raw_screenshots",
            },
        )
    status = build_pilot_operations_status(
        evidence_root=evidence_root,
        generated_at=generated,
    )
    payload = {
        "version": PILOT_OPERATIONS_VERSION,
        "generatedAtUtc": generated.isoformat(),
        "status": status.status,
        "redaction": "local_only_no_pii_no_raw_screenshots",
        "feedbackChannels": ["local-support-bundle", "operator-notes"],
        "checklist": [item.model_dump(mode="json", by_alias=True) for item in status.checklist],
        "timeline": [item.model_dump(mode="json", by_alias=True) for item in status.timeline],
        "acceptanceMetrics": status.acceptance_metrics,
        "blockers": status.blockers,
        "warnings": status.warnings,
    }
    _write_json(
        output / "pilot_operations_status.json",
        status.model_dump(mode="json", by_alias=True),
    )
    _write_json(output / "pilot_timeline.json", payload["timeline"])
    _write_json(output / "pilot_feedback_bundle.json", payload)
    (output / "FIRST_RUN_CHECKLIST.md").write_text(
        _checklist_markdown(status),
        encoding="utf-8",
    )
    (output / "PILOT_FEEDBACK.md").write_text(
        _feedback_markdown(payload),
        encoding="utf-8",
    )
    return payload


def _artifact_base(evidence_root: str | Path) -> Path:
    path = Path(evidence_root)
    if path.name == "valid" and path.parent.name == "evidence-corpus":
        return path.parents[1]
    return path


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _finding_bucket(
    bucket_id: str,
    label: str,
    payload: Any,
    artifact_root: Path,
) -> CodeIntelligenceFindingBucket:
    if not isinstance(payload, dict):
        return CodeIntelligenceFindingBucket(
            bucketId=bucket_id,
            label=label,
            status="missing",
            detail="report missing",
        )
    errors = int(payload.get("errors") or 0)
    warnings = int(payload.get("warnings") or 0)
    count = int(payload.get("total") or 0)
    status = "blocked" if errors else "warn" if warnings or count else "ready"
    return CodeIntelligenceFindingBucket(
        bucketId=bucket_id,
        label=label,
        status=status,
        count=count,
        errors=errors,
        warnings=warnings,
        path=str(artifact_root / f"{bucket_id}.json"),
        detail="; ".join(str(item) for item in payload.get("notes", [])[:3]),
    )


def _artifact_item(
    *,
    item_id: str,
    label: str,
    path: Path,
    payload: dict[str, Any] | None,
    pass_values: set[str],
) -> PilotOperationsChecklistItem:
    if payload is None:
        return PilotOperationsChecklistItem(
            itemId=item_id,
            label=label,
            status="missing",
            detail="artifact missing",
            path=str(path),
            blocking=False,
        )
    raw_status = str(payload.get("status", "unknown"))
    if raw_status in pass_values:
        status = "ready"
    elif raw_status in {"blocked", "fail", "failed"}:
        status = "blocked"
    else:
        status = "conditional"
    return PilotOperationsChecklistItem(
        itemId=item_id,
        label=label,
        status=status,
        detail=f"status={raw_status}",
        path=str(path),
        blocking=status == "blocked",
    )


def _feedback_item(path: Path) -> PilotOperationsChecklistItem:
    return PilotOperationsChecklistItem(
        itemId="feedback-bundle",
        label="Pilot feedback bundle",
        status="ready" if path.exists() else "missing",
        detail="redacted local feedback export" if path.exists() else "not exported yet",
        path=str(path),
        blocking=False,
    )


def _safety_claim_item(pilot_manifest: dict[str, Any] | None) -> PilotOperationsChecklistItem:
    if pilot_manifest is None:
        return PilotOperationsChecklistItem(
            itemId="safety-claims",
            label="Safety claims remain blocked",
            status="missing",
            detail="pilot claim guard artifact missing",
            path=None,
            blocking=False,
        )
    claims = pilot_manifest.get("claimGuard", {}).get("claims", []) if pilot_manifest else []
    by_id = {
        str(item.get("claim_id")): item
        for item in claims
        if isinstance(item, dict)
    }
    public_installer_blocked = by_id.get("public-desktop-installer", {}).get("status") == "blocked"
    computer_use_blocked = by_id.get("live-macos-computer-use", {}).get("status") == "blocked"
    status = "ready" if public_installer_blocked and computer_use_blocked else "blocked"
    return PilotOperationsChecklistItem(
        itemId="safety-claims",
        label="Safety claims remain blocked",
        status=status,
        detail="computer-use live and public desktop installer remain blocked",
        path=None,
        blocking=status == "blocked",
    )


def _timeline(
    *,
    base: Path,
    checklist: list[PilotOperationsChecklistItem],
    generated_at: datetime,
) -> list[PilotOperationsTimelineEvent]:
    events = []
    for item in checklist:
        path = Path(item.path) if item.path else None
        events.append(
            PilotOperationsTimelineEvent(
                eventId=item.item_id,
                label=item.label,
                status="completed"
                if item.status == "ready"
                else "blocked"
                if item.status == "blocked"
                else "warning",
                detail=item.detail,
                artifactRef=item.path,
                occurredAtUtc=_mtime(path) if path and path.exists() else generated_at,
            )
        )
    events.append(
        PilotOperationsTimelineEvent(
            eventId="first-run-review",
            label="First-run review",
            status="pending",
            detail="operator review notes are local-only until explicitly shared",
            artifactRef=str(base / "pilot-ops" / "PILOT_FEEDBACK.md"),
            occurredAtUtc=generated_at,
        )
    )
    return events


def _acceptance_metrics(
    *,
    metrics: dict[str, Any],
    external_v1_1: dict[str, Any] | None,
    code_intelligence: CodeIntelligenceSummary,
) -> dict[str, Any]:
    external_cases = external_v1_1.get("cases", []) if external_v1_1 else []
    passed_cases = [
        case
        for case in external_cases
        if isinstance(case, dict) and case.get("passed") is True
    ]
    return {
        "privacy": "aggregate_only_no_pii",
        "pilotRunCount": metrics.get("runCount", 0),
        "externalAgentRuns": metrics.get("externalAgentRuns", 0),
        "externalAgentV11Cases": len(external_cases),
        "externalAgentV11Passed": len(passed_cases),
        "fallowVerdict": code_intelligence.verdict,
        "fallowBoundaryViolations": code_intelligence.boundary_violations,
        "claimGuard": metrics.get("claimGuard", {}),
        "policyDecisions": metrics.get("policyDecisions", {}),
    }


def _next_actions(*, blockers: list[str], warnings: list[str]) -> list[PilotLaunchNextAction]:
    if blockers:
        return [
            PilotLaunchNextAction(label=blocker, severity="blocking", target="Pilot Ops")
            for blocker in blockers
        ]
    if warnings:
        return [
            PilotLaunchNextAction(label=warning, severity="warning", target="Pilot Ops")
            for warning in warnings
        ]
    return [
        PilotLaunchNextAction(
            label="Review design partner feedback bundle",
            severity="info",
            target="Pilot Ops",
        )
    ]


def _checklist_markdown(status: PilotOperationsStatus) -> str:
    lines = [
        "# Pilot First-run Checklist",
        "",
        f"- Status: `{status.status}`",
        f"- Generated: `{status.generated_at_utc.isoformat()}`",
        "",
    ]
    for item in status.checklist:
        lines.append(f"- [{item.status}] {item.label}: {item.detail}")
    lines.append("")
    return "\n".join(lines)


def _feedback_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Pilot Feedback Export",
        "",
        f"- Status: `{payload['status']}`",
        f"- Redaction: `{payload['redaction']}`",
        f"- Generated: `{payload['generatedAtUtc']}`",
        "- Scope: local-only operator review bundle",
        "- Privacy: no PII, no raw screenshots, no secrets, no private keys",
        "- Operator notes: review and redact before sharing outside the local environment",
        "",
        "## Acceptance Metrics",
        "",
    ]
    for key, value in payload["acceptanceMetrics"].items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Blockers", ""])
    blockers = payload.get("blockers") or []
    lines.extend(f"- {item}" for item in blockers) if blockers else lines.append("- none")
    lines.extend(["", "## Warnings", ""])
    warnings = payload.get("warnings") or []
    lines.extend(f"- {item}" for item in warnings) if warnings else lines.append("- none")
    lines.append("")
    return "\n".join(lines)


def _mtime(path: Path | None) -> datetime | None:
    if path is None or not path.exists():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
