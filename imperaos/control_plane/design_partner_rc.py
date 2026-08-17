from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from imperaos.control_plane.models import (
    AlertSummary,
    DataSourceState,
    DesignPartnerBetaStatus,
    DesignPartnerRcCheck,
    DesignPartnerRcStatus,
    EvidencePackSummary,
    ExecutionSurfaceSummary,
    ProviderGovernanceSnapshot,
    ReportSummary,
)

EXPECTED_BLOCKED_BOUNDARY_ALERT_IDS = {
    "claim-public-desktop-installer",
    "claim-live-macos-computer-use",
    "claim-live-windows-computer-use",
    "claim-live-linux-computer-use",
}

EXPECTED_BLOCKED_BOUNDARY_REASONS = {
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

EXPECTED_RC_AUDIT_CONDITIONALS = {
    "design-partner-beta",
    "provider-governance",
    "evidence-index",
    "reports",
    "preview-source",
    "enterprise-hat-a",
    "active-alerts",
    "artifact:external_gateway_smoke.json",
    "artifact:policy_pack_promotion.json",
    "artifact:evidence_index.json",
    "artifact:reports-alerts-logs/manifest.json",
    "artifact:control-plane-snapshot.json",
    "artifact:claim-guard-matrix.json",
    "artifact:design-partner-rc-status.json",
    "artifact:DESIGN_PARTNER_RC_REPORT.md",
}


@dataclass(frozen=True)
class DesignPartnerRcAuditResult:
    strict_status: Literal["pass", "conditional", "blocked"]
    audit_status: Literal["pass", "blocked"]
    expected_conditionals: tuple[str, ...]
    unexpected_warnings: tuple[str, ...]
    blockers: tuple[str, ...]
    exit_mode: Literal["strict", "blocker_only"]

    def to_payload(self) -> dict[str, object]:
        return {
            "schemaVersion": "control-plane.design-partner-rc-audit/v1",
            "strictStatus": self.strict_status,
            "auditStatus": self.audit_status,
            "expectedConditionals": list(self.expected_conditionals),
            "unexpectedWarnings": list(self.unexpected_warnings),
            "blockers": list(self.blockers),
            "exitMode": self.exit_mode,
        }


def evaluate_design_partner_rc_audit(
    rc_manifest: Mapping[str, Any],
    *,
    expected_conditionals: set[str],
    fail_on_unexpected_warning: bool = True,
) -> DesignPartnerRcAuditResult:
    blockers = tuple(sorted(str(item) for item in rc_manifest.get("blockers", []) if item))
    warnings = tuple(sorted(str(item) for item in rc_manifest.get("warnings", []) if item))
    expected = tuple(item for item in warnings if item in expected_conditionals)
    unexpected = tuple(item for item in warnings if item not in expected_conditionals)
    manifest_status = str(
        rc_manifest.get("status", rc_manifest.get("designPartnerRcStatus", "pass"))
    )
    strict_status: Literal["pass", "conditional", "blocked"]
    if blockers or manifest_status == "blocked":
        strict_status = "blocked"
    elif warnings or manifest_status == "conditional":
        strict_status = "conditional"
    else:
        strict_status = "pass"
    audit_blocked = bool(blockers) or (fail_on_unexpected_warning and bool(unexpected))
    return DesignPartnerRcAuditResult(
        strict_status=strict_status,
        audit_status="blocked" if audit_blocked else "pass",
        expected_conditionals=tuple(sorted(expected)),
        unexpected_warnings=tuple(sorted(unexpected)),
        blockers=blockers,
        exit_mode="blocker_only",
    )


def build_design_partner_rc_status(
    *,
    data_source: DataSourceState,
    claims: dict[str, Any],
    evidence_packs: list[EvidencePackSummary],
    reports: list[ReportSummary],
    alerts: list[AlertSummary],
    execution_surfaces: list[ExecutionSurfaceSummary],
    design_partner_beta: DesignPartnerBetaStatus | None = None,
    provider_governance: ProviderGovernanceSnapshot | None = None,
    generated_at: datetime | None = None,
    artifact_root: str = "artifacts/design-partner-rc",
) -> DesignPartnerRcStatus:
    """Aggregate Design Partner RC readiness without opening blocked claims."""

    actionable_alerts = _active_error_alerts(alerts)
    checks = [
        _check(
            "runtime-truth",
            "Runtime truth",
            not data_source.is_silent_fallback and data_source.mode != "error",
            f"mode={data_source.mode} silentFallback={data_source.is_silent_fallback}",
            blocking=True,
        ),
        _conditional_check(
            "preview-source",
            "Preview source boundary",
            data_source.mode != "preview_fixture",
            f"mode={data_source.mode}",
        ),
        _beta_precondition_check(design_partner_beta),
        _provider_governance_check(provider_governance),
        _conditional_check(
            "evidence-index",
            "Evidence coverage",
            len(evidence_packs) > 0,
            f"{len(evidence_packs)} evidence pack(s)",
        ),
        _conditional_check(
            "reports",
            "Report coverage",
            any(report.status == "ready" for report in reports),
            f"{sum(1 for report in reports if report.status == 'ready')} ready report(s)",
        ),
        _check(
            "computer-use-boundary",
            "Computer-use claim boundary",
            _surface_status(execution_surfaces, "computer-use") == "blocked",
            f"computer-use={_surface_status(execution_surfaces, 'computer-use')}",
            blocking=True,
        ),
        _check(
            "public-desktop-boundary",
            "Public desktop claim boundary",
            _surface_status(execution_surfaces, "public-desktop-installer") == "blocked",
            "public-desktop-installer="
            f"{_surface_status(execution_surfaces, 'public-desktop-installer')}",
            blocking=True,
        ),
        _conditional_check(
            "enterprise-hat-a",
            "Enterprise Hat A evidence",
            _claim_status(claims, "enterprise-self-hosted-agent-control-plane") == "allowed",
            f"status={_claim_status(claims, 'enterprise-self-hosted-agent-control-plane')}",
        ),
        _conditional_check(
            "active-alerts",
            "Active alert review",
            not actionable_alerts,
            f"{len(actionable_alerts)} active error/critical alert(s)",
        ),
    ]
    blockers = [check.check_id for check in checks if check.status == "failed" and check.blocking]
    warnings = [check.check_id for check in checks if check.status == "conditional"]
    status = "blocked" if blockers else "conditional" if warnings else "ready"

    return DesignPartnerRcStatus(
        generated_at_utc=generated_at or datetime.now(UTC),
        status=status,
        checks=checks,
        blockers=blockers,
        warnings=warnings,
        artifact_root=artifact_root,
    )


def _check(
    check_id: str,
    label: str,
    passed: bool,
    detail: str,
    *,
    blocking: bool,
) -> DesignPartnerRcCheck:
    return DesignPartnerRcCheck(
        check_id=check_id,
        label=label,
        status="passed" if passed else "failed",
        detail=detail,
        blocking=blocking,
    )


def _conditional_check(
    check_id: str,
    label: str,
    passed: bool,
    detail: str,
) -> DesignPartnerRcCheck:
    return DesignPartnerRcCheck(
        check_id=check_id,
        label=label,
        status="passed" if passed else "conditional",
        detail=detail,
        blocking=False,
    )


def _beta_precondition_check(
    design_partner_beta: DesignPartnerBetaStatus | None,
) -> DesignPartnerRcCheck:
    if design_partner_beta is None:
        return DesignPartnerRcCheck(
            check_id="design-partner-beta",
            label="Design Partner Beta readiness",
            status="conditional",
            detail="status=missing",
            blocking=False,
        )
    if design_partner_beta.status == "blocked":
        return DesignPartnerRcCheck(
            check_id="design-partner-beta",
            label="Design Partner Beta readiness",
            status="failed",
            detail="status=blocked",
            blocking=True,
        )
    return DesignPartnerRcCheck(
        check_id="design-partner-beta",
        label="Design Partner Beta readiness",
        status="passed" if design_partner_beta.status == "ready" else "conditional",
        detail=f"status={design_partner_beta.status}",
        blocking=False,
    )


def _provider_governance_check(
    provider_governance: ProviderGovernanceSnapshot | None,
) -> DesignPartnerRcCheck:
    if provider_governance is None:
        return DesignPartnerRcCheck(
            check_id="provider-governance",
            label="Provider governance",
            status="passed",
            detail="status=not_requested",
            blocking=False,
        )
    external = [
        provider
        for provider in provider_governance.providers
        if provider.provider_kind in {"openai_responses", "anthropic_messages"}
    ]
    conformance_ready = all(provider.last_conformance_status == "pass" for provider in external)
    policies_safe = all(
        provider.server_tools_policy == "denied"
        and provider.custom_tools_policy == "proposal_only"
        and provider.retention_policy == "hash_only_store_false"
        for provider in external
    )
    ready = provider_governance.overall_status == "ready" and conformance_ready and policies_safe
    conditional = (
        provider_governance.overall_status == "conditional" and conformance_ready and policies_safe
    )
    return DesignPartnerRcCheck(
        check_id="provider-governance",
        label="Provider governance",
        status="passed" if ready else "conditional" if conditional else "failed",
        detail=(
            f"status={provider_governance.overall_status} "
            f"externalProviders={len(external)} "
            f"blockingReasons={','.join(provider_governance.blocking_reasons) or 'none'}"
        ),
        blocking=not (ready or conditional),
    )


def _claim_status(claims: dict[str, Any], claim_id: str) -> str:
    for claim in claims.get("claims", []):
        if isinstance(claim, dict) and claim.get("claim_id") == claim_id:
            return str(claim.get("status", "conditional"))
    return "conditional"


def _surface_status(surfaces: list[ExecutionSurfaceSummary], surface_id: str) -> str:
    for surface in surfaces:
        if surface.surface_id == surface_id:
            return surface.status
    return "missing"


def _active_error_alerts(alerts: list[AlertSummary]) -> list[AlertSummary]:
    return [
        alert
        for alert in alerts
        if alert.status == "active"
        and alert.severity in {"error", "critical"}
        and not is_expected_blocked_claim_boundary_alert(alert)
    ]


def is_expected_blocked_claim_boundary_alert(alert: AlertSummary) -> bool:
    return (
        alert.alert_id in EXPECTED_BLOCKED_BOUNDARY_ALERT_IDS
        and alert.reason_code in EXPECTED_BLOCKED_BOUNDARY_REASONS
    )
