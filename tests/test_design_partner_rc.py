from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from imperaos.control_plane.design_partner_rc import build_design_partner_rc_status
from imperaos.control_plane.models import (
    AlertSummary,
    DataSourceState,
    DesignPartnerBetaStatus,
    EvidencePackSummary,
    ExecutionSurfaceSummary,
    ProviderGovernanceSnapshot,
    ProviderRegistryEntry,
    ReportSummary,
)


def test_design_partner_rc_blocks_silent_fallback() -> None:
    status = build_design_partner_rc_status(
        data_source=_data_source(mode="preview_fixture", is_mock=True, is_silent_fallback=True),
        claims=_claims("allowed"),
        evidence_packs=[],
        reports=[],
        alerts=[],
        execution_surfaces=_blocked_surfaces(),
        design_partner_beta=_beta_status("ready"),
        generated_at=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
    )

    assert status.status == "blocked"
    assert "runtime-truth" in status.blockers


def test_design_partner_rc_requires_blocked_desktop_boundaries() -> None:
    surfaces = [
        ExecutionSurfaceSummary(
            surface_id="computer-use",
            label="Computer-use automation",
            status="blocked",
            claim_id="computer-use",
            reason_codes=["CLAIM_NOT_SUPPORTED"],
            human_summary="Blocked until qualification evidence exists.",
        ),
        ExecutionSurfaceSummary(
            surface_id="public-desktop-installer",
            label="Public desktop installer",
            status="ready",
            claim_id="public-desktop-installer",
            reason_codes=[],
            human_summary="Incorrectly opened surface.",
        ),
    ]
    status = build_design_partner_rc_status(
        data_source=_data_source(),
        claims=_claims("allowed"),
        evidence_packs=[],
        reports=[],
        alerts=[],
        execution_surfaces=surfaces,
        design_partner_beta=_beta_status("ready"),
        generated_at=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
    )

    assert status.status == "blocked"
    assert "public-desktop-boundary" in status.blockers


def test_design_partner_rc_requires_beta_ready_before_rc_ready() -> None:
    status = build_design_partner_rc_status(
        data_source=_data_source(),
        claims=_claims("allowed"),
        evidence_packs=_ready_evidence_packs(),
        reports=_ready_reports(),
        alerts=_resolved_alerts(),
        execution_surfaces=_blocked_surfaces(),
        design_partner_beta=_beta_status("conditional"),
        generated_at=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
    )

    assert status.status == "conditional"
    assert "design-partner-beta" in status.warnings


def test_design_partner_rc_blocks_when_beta_is_blocked() -> None:
    status = build_design_partner_rc_status(
        data_source=_data_source(),
        claims=_claims("allowed"),
        evidence_packs=_ready_evidence_packs(),
        reports=_ready_reports(),
        alerts=_resolved_alerts(),
        execution_surfaces=_blocked_surfaces(),
        design_partner_beta=_beta_status("blocked"),
        generated_at=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
    )

    assert status.status == "blocked"
    assert "design-partner-beta" in status.blockers


def test_design_partner_rc_ready_when_required_evidence_is_present() -> None:
    status = build_design_partner_rc_status(
        data_source=_data_source(),
        claims=_claims("allowed"),
        evidence_packs=_ready_evidence_packs(),
        reports=_ready_reports(),
        alerts=_resolved_alerts(),
        execution_surfaces=_blocked_surfaces(),
        design_partner_beta=_beta_status("ready"),
        generated_at=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
    )

    assert status.status == "ready"
    assert status.blockers == []
    assert status.warnings == []


def test_design_partner_rc_includes_provider_governance_warning_when_credentials_missing() -> None:
    status = build_design_partner_rc_status(
        data_source=_data_source(),
        claims=_claims("allowed"),
        evidence_packs=_ready_evidence_packs(),
        reports=_ready_reports(),
        alerts=_resolved_alerts(),
        execution_surfaces=_blocked_surfaces(),
        design_partner_beta=_beta_status("ready"),
        provider_governance=ProviderGovernanceSnapshot(
            generated_at_utc=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
            overall_status="conditional",
            blocking_reasons=["blocked_external_credentials"],
            providers=[
                ProviderRegistryEntry(
                    provider_kind="openai_responses",
                    display_name="OpenAI Responses Native Preview",
                    status="blocked",
                    credential_state="missing",
                    canary_only=True,
                    supports_streaming=True,
                    server_tools_policy="denied",
                    custom_tools_policy="proposal_only",
                    retention_policy="hash_only_store_false",
                    last_conformance_status="pass",
                    blocking_reasons=["blocked_external_credentials"],
                )
            ],
        ),
        generated_at=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
    )

    assert status.status == "conditional"
    assert "provider-governance" in status.warnings


def test_design_partner_rc_ignores_expected_blocked_boundary_alerts() -> None:
    status = build_design_partner_rc_status(
        data_source=_data_source(),
        claims=_claims("allowed"),
        evidence_packs=_ready_evidence_packs(),
        reports=_ready_reports(),
        alerts=[
            _active_alert(
                "claim-public-desktop-installer",
                "CLEAN_MACHINE_SMOKE_MISSING",
            ),
            _active_alert(
                "claim-live-macos-computer-use",
                "MACOS_LIVE_DISABLED",
            ),
        ],
        execution_surfaces=_blocked_surfaces(),
        design_partner_beta=_beta_status("ready"),
        generated_at=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
    )

    assert status.status == "ready"
    assert "active-alerts" not in status.warnings


def test_design_partner_rc_keeps_real_active_error_alert_conditional() -> None:
    status = build_design_partner_rc_status(
        data_source=_data_source(),
        claims=_claims("allowed"),
        evidence_packs=_ready_evidence_packs(),
        reports=_ready_reports(),
        alerts=[_active_alert("evidence-tamper", "EVIDENCE_HASH_MISMATCH")],
        execution_surfaces=_blocked_surfaces(),
        design_partner_beta=_beta_status("ready"),
        generated_at=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
    )

    assert status.status == "conditional"
    assert "active-alerts" in status.warnings


def _data_source(
    *,
    mode: str = "cli_live",
    is_mock: bool = False,
    is_silent_fallback: bool = False,
) -> DataSourceState:
    return DataSourceState(
        mode=mode,
        is_mock=is_mock,
        is_silent_fallback=is_silent_fallback,
        last_refresh_utc=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
        age_ms=0,
        freshness="fresh",
        contract_version="control-plane.snapshot/v1",
        source_reason="test",
    )


def _claims(status: str) -> dict[str, object]:
    return {
        "claims": [
            {
                "claim_id": "enterprise-self-hosted-agent-control-plane",
                "status": status,
            }
        ]
    }


def _blocked_surfaces() -> list[ExecutionSurfaceSummary]:
    return [
        ExecutionSurfaceSummary(
            surface_id="computer-use",
            label="Computer-use automation",
            status="blocked",
            claim_id="computer-use",
            reason_codes=["CLAIM_NOT_SUPPORTED"],
            human_summary="Blocked until qualification evidence exists.",
        ),
        ExecutionSurfaceSummary(
            surface_id="public-desktop-installer",
            label="Public desktop installer",
            status="blocked",
            claim_id="public-desktop-installer",
            reason_codes=["CLAIM_NOT_SUPPORTED"],
            human_summary="Blocked until signed installer evidence exists.",
        ),
    ]


def _beta_status(status: Literal["ready", "conditional", "blocked"]) -> DesignPartnerBetaStatus:
    return DesignPartnerBetaStatus(status=status)


def _ready_evidence_packs() -> list[EvidencePackSummary]:
    return [
        EvidencePackSummary(
            pack_id="pack-1",
            run_id="run-1",
            created_at_utc=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
            signature_status="valid",
            hash_chain_status="valid",
            replay_status="passed",
            claim_guard_status="ready",
            redaction_status="passed",
            artifact_count=3,
            export_path="artifacts/evidence-pack/pack-1",
            blocking_reasons=[],
        )
    ]


def _ready_reports() -> list[ReportSummary]:
    return [
        ReportSummary(
            report_id="readiness",
            kind="readiness",
            title="Readiness",
            status="ready",
            path="artifacts/readiness/report.json",
            generated_at_utc=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
            blocking_reasons=[],
        )
    ]


def _resolved_alerts() -> list[AlertSummary]:
    return [
        AlertSummary(
            alert_id="clear",
            severity="info",
            status="resolved",
            title="No active control-plane alerts",
            reason_code="NO_ACTIVE_ALERTS",
            recommended_action="Continue monitoring.",
        )
    ]


def _active_alert(alert_id: str, reason_code: str) -> AlertSummary:
    return AlertSummary(
        alert_id=alert_id,
        severity="error",
        status="active",
        title="Active alert",
        reason_code=reason_code,
        recommended_action="Review evidence.",
    )
