from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from imperaos.control_plane.models import (
    AlertSummary,
    PilotLaunchAdminProposalSummary,
    PilotLaunchNextAction,
    PilotLaunchReadinessStatus,
    PilotLaunchStatusTile,
)

EXPECTED_BOUNDARY_REASON_CODES = {
    "CLEAN_MACHINE_SMOKE_MISSING",
    "COMPUTER_USE_NOT_QUALIFIED",
    "HAT_B_EVIDENCE_MISSING",
    "LINUX_COMPUTER_USE_NOT_QUALIFIED",
    "MACOS_LIVE_DISABLED",
    "MACOS_NOTARIZATION_EVIDENCE_MISSING",
    "SIGNED_PLATFORM_QUALIFICATION_MISSING",
    "WINDOWS_COMPUTER_USE_NOT_QUALIFIED",
    "WINDOWS_SIGNED_RC_EVIDENCE_MISSING",
}


def build_pilot_launch_readiness_status(
    *,
    artifact_root: Path,
    claims: dict[str, Any],
    alerts: list[AlertSummary],
    generated_at: datetime | None = None,
) -> PilotLaunchReadinessStatus:
    """Summarize pilot launch artifacts without generating or promoting claims."""

    root = _artifact_root(artifact_root)
    tiles = {
        "enterprise_hat_a": _tile_from_file(
            root / "enterprise-hat-a" / "enterprise_hat_a_closure.json",
            tile_id="enterprise-hat-a",
            label="Enterprise Hat A",
            detail="Signed qualification closure",
            status_keys=("claimStatus", "status"),
        ),
        "install_rehearsal": _tile_from_file(
            root / "install-rehearsal" / "report.json",
            tile_id="install-rehearsal",
            label="Install rehearsal",
            detail="Clean-root source/CLI rehearsal",
            status_keys=("status",),
        ),
        "external_agent_pilot": _tile_from_file(
            root / "design-partner-pilot" / "external-agent-pilot-report.json",
            tile_id="external-agent-pilot",
            label="External agent pilot",
            detail="Gateway examples and policy outcomes",
            status_keys=("status",),
        ),
        "governance_admin": _tile_from_file(
            root / "design-partner-pilot" / "governance-admin-report.json",
            tile_id="governance-admin",
            label="Governance admin",
            detail="Admin proposals, approvals, and signed audit",
            status_keys=("status",),
        ),
        "security_review": _tile_from_file(
            root / "security-review" / "security_review_pack.json",
            tile_id="security-review",
            label="Security review",
            detail="Threat model, redaction proof, and no-secret scan",
            status_keys=("status",),
        ),
        "evidence_corpus": _tile_from_file(
            root / "evidence-corpus" / "corpus_verification_report.json",
            tile_id="evidence-corpus",
            label="Evidence corpus",
            detail="Valid and negative verification cases",
            status_keys=("status",),
        ),
        "pilot_metrics": _tile_from_file(
            root / "design-partner-pilot" / "pilot_metrics.json",
            tile_id="pilot-metrics",
            label="Pilot metrics",
            detail="Aggregate-only launch telemetry",
            status_keys=("status",),
        ),
    }
    claim_guard = _claim_guard_tile(claims)
    admin_proposals = _admin_proposals(
        root / "design-partner-pilot" / "governance-admin-report.json"
    )

    blocking_tiles = [
        tile.tile_id
        for tile in [*tiles.values(), claim_guard]
        if tile.status == "blocked"
    ]
    warning_tiles = [
        tile.tile_id
        for tile in [*tiles.values(), claim_guard]
        if tile.status in {"conditional", "missing"}
    ]
    critical_alerts = _blocking_alert_ids(alerts)
    blockers = sorted(set(blocking_tiles + critical_alerts))
    warnings = sorted(set(warning_tiles))
    status = "blocked" if blockers else "conditional" if warnings else "ready"

    return PilotLaunchReadinessStatus(
        generated_at_utc=generated_at or datetime.now(UTC),
        status=status,
        headline=_headline(status),
        artifact_root=str(root),
        enterprise_hat_a=tiles["enterprise_hat_a"],
        install_rehearsal=tiles["install_rehearsal"],
        external_agent_pilot=tiles["external_agent_pilot"],
        governance_admin=tiles["governance_admin"],
        security_review=tiles["security_review"],
        claim_guard=claim_guard,
        evidence_corpus=tiles["evidence_corpus"],
        pilot_metrics=tiles["pilot_metrics"],
        admin_proposals=admin_proposals,
        next_actions=_next_actions(blockers=blockers, warnings=warnings),
        blockers=blockers,
        warnings=warnings,
    )


def _blocking_alert_ids(alerts: list[AlertSummary]) -> list[str]:
    return [
        alert.alert_id
        for alert in alerts
        if alert.status == "active"
        and alert.severity in {"critical", "error"}
        and alert.reason_code not in EXPECTED_BOUNDARY_REASON_CODES
    ]


def _artifact_root(path: Path) -> Path:
    parts = path.parts
    if "evidence-corpus" in parts:
        return Path(*parts[: parts.index("evidence-corpus")]) or Path(".")
    return path


def _tile_from_file(
    path: Path,
    *,
    tile_id: str,
    label: str,
    detail: str,
    status_keys: tuple[str, ...],
) -> PilotLaunchStatusTile:
    if not path.exists():
        return PilotLaunchStatusTile(
            tile_id=tile_id,
            label=label,
            status="missing",
            detail=detail,
            path=str(path),
            blocking_reasons=[f"{tile_id.upper().replace('-', '_')}_MISSING"],
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return PilotLaunchStatusTile(
            tile_id=tile_id,
            label=label,
            status="blocked",
            detail="Invalid JSON artifact",
            path=str(path),
            blocking_reasons=[f"{tile_id.upper().replace('-', '_')}_INVALID"],
        )
    if isinstance(payload.get("data"), dict):
        payload = payload["data"]
    status_value = next(
        (str(payload[key]) for key in status_keys if isinstance(payload.get(key), str)),
        "present",
    )
    return PilotLaunchStatusTile(
        tile_id=tile_id,
        label=label,
        status=_normalize_status(status_value),
        detail=detail,
        path=str(path),
        blocking_reasons=_string_list(
            payload.get("blockingReasons") or payload.get("blocking_reasons")
        ),
    )


def _claim_guard_tile(claims: dict[str, Any]) -> PilotLaunchStatusTile:
    claim_by_id = {
        str(item.get("claim_id")): item
        for item in claims.get("claims", [])
        if isinstance(item, dict)
    }
    enterprise = str(
        claim_by_id.get("enterprise-self-hosted-agent-control-plane", {}).get(
            "status",
            "conditional",
        )
    )
    public_desktop = str(claim_by_id.get("public-desktop-installer", {}).get("status", "blocked"))
    computer_use = [
        str(claim_by_id.get(claim_id, {}).get("status", "blocked"))
        for claim_id in (
            "live-macos-computer-use",
            "live-windows-computer-use",
            "live-linux-computer-use",
        )
    ]
    blockers = []
    if enterprise != "allowed":
        blockers.append("ENTERPRISE_HAT_A_NOT_READY")
    if public_desktop != "blocked":
        blockers.append("PUBLIC_DESKTOP_FALSE_READY")
    if any(status != "blocked" for status in computer_use):
        blockers.append("COMPUTER_USE_FALSE_READY")
    return PilotLaunchStatusTile(
        tile_id="claim-guard",
        label="Claim guard",
        status="ready" if not blockers else "blocked",
        detail=(
            f"enterprise={enterprise}, publicDesktop={public_desktop}, "
            f"computerUseBlocked={all(status == 'blocked' for status in computer_use)}"
        ),
        path=None,
        blocking_reasons=blockers,
    )


def _admin_proposals(path: Path) -> list[PilotLaunchAdminProposalSummary]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    raw_items = payload.get("proposals") if isinstance(payload.get("proposals"), list) else []
    proposals: list[PilotLaunchAdminProposalSummary] = []
    for item in raw_items[:8]:
        if not isinstance(item, dict):
            continue
        proposals.append(
            PilotLaunchAdminProposalSummary(
                proposal_id=str(item.get("proposalId") or item.get("proposal_id") or "proposal"),
                kind=str(item.get("kind") or "unknown"),
                operation=str(item.get("operation") or "unknown"),
                status=str(item.get("status") or "unknown"),
                permission_required=str(
                    item.get("permissionRequired")
                    or item.get("permission_required")
                    or "admin.write"
                ),
                approval_id=(
                    str(item["approvalId"])
                    if item.get("approvalId") is not None
                    else str(item["approval_id"])
                    if item.get("approval_id") is not None
                    else None
                ),
                audit_envelope_path=(
                    str(item["auditEnvelopePath"])
                    if item.get("auditEnvelopePath") is not None
                    else str(item["audit_envelope_path"])
                    if item.get("audit_envelope_path") is not None
                    else None
                ),
            )
        )
    return proposals


def _normalize_status(status: str) -> str:
    if status in {"ready", "pass", "passed", "valid", "allowed", "present"}:
        return "ready"
    if status in {"blocked", "fail", "failed", "invalid", "denied"}:
        return "blocked"
    if status == "missing":
        return "missing"
    return "conditional"


def _string_list(value: Any) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


def _headline(status: str) -> str:
    if status == "ready":
        return "Pilot launch candidate is ready."
    if status == "blocked":
        return "Pilot launch candidate is blocked."
    return "Pilot launch candidate is conditional."


def _next_actions(*, blockers: list[str], warnings: list[str]) -> list[PilotLaunchNextAction]:
    if blockers:
        return [
            PilotLaunchNextAction(label=blocker, severity="blocking", target="Reports")
            for blocker in blockers[:5]
        ]
    if warnings:
        return [
            PilotLaunchNextAction(label=warning, severity="warning", target="Reports")
            for warning in warnings[:5]
        ]
    return [
        PilotLaunchNextAction(
            label="Review pilot launch report",
            severity="info",
            target="Reports",
        )
    ]
