from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from imperaos import __version__
from imperaos.contracts.version import OPERATOR_PANEL_CONTRACT_VERSION
from imperaos.control_plane.agent_registry_v2 import agent_registry_v2_item
from imperaos.control_plane.claim_guard import ClaimGuard
from imperaos.control_plane.design_partner_handoff import build_design_partner_handoff_snapshot
from imperaos.control_plane.design_partner_rc import build_design_partner_rc_status
from imperaos.control_plane.enterprise_workspace_snapshot import (
    build_enterprise_workspace_snapshot,
)
from imperaos.control_plane.field_evidence import build_design_partner_field_evidence_snapshot
from imperaos.control_plane.mainline_rc_freeze import build_mainline_rc_freeze_snapshot
from imperaos.control_plane.models import (
    AdminSummary,
    AgentSummary,
    AlertSummary,
    ApprovalSnapshotSummary,
    ControlPlaneSnapshot,
    DashboardSummary,
    DataSourceState,
    DesignPartnerFieldEvidenceSnapshot,
    DesignPartnerHandoffSnapshot,
    EvidencePackManifest,
    EvidencePackSummary,
    ExecutionSurfaceSummary,
    LogEventSummary,
    MainlineRcFreezeSnapshot,
    OperationDescriptor,
    OperationResultSummary,
    PolicyPackSummary,
    ProviderInvocationArtifact,
    ProviderRuntimeSnapshot,
    ProviderWorkflowProofArtifact,
    QuickActionSummary,
    ReportSummary,
    RunSnapshotSummary,
    SystemHealthState,
    SystemSummary,
    TargetEvidenceBundle,
    TargetEvidenceClosureSummary,
)
from imperaos.control_plane.pilot_launch_readiness import build_pilot_launch_readiness_status
from imperaos.control_plane.pilot_operations import (
    build_code_intelligence_summary,
    build_design_partner_beta_status,
    build_pilot_operations_status,
)
from imperaos.control_plane.pilot_workflow import build_governed_pilot_workflow_snapshot
from imperaos.control_plane.provider_registry import build_provider_governance_snapshot
from imperaos.control_plane.rbac_admin import build_admin_summary
from imperaos.control_plane.registry import AgentRegistry
from imperaos.control_plane.run_coordinator import ControlPlaneRunCoordinator
from imperaos.control_plane.storage import file_sha256
from imperaos.enterprise.identity import describe_actor
from imperaos.enterprise.signing import key_status
from imperaos.governance.approval_store import ApprovalStore
from imperaos.governance.policy import load_policy
from imperaos.memory.runtime_policy_snapshot import (
    MemoryPolicyEnforcementSnapshot,
    build_memory_policy_enforcement_snapshot,
)
from imperaos.memory.runtime_snapshot import (
    build_memory_runtime_snapshot,
    build_memory_sync_snapshot,
)
from imperaos.memory.semantic import MemorySemanticIndexSnapshot, build_memory_semantic_snapshot
from imperaos.memory.snapshot import build_memory_governance_snapshot
from imperaos.memory.workspace_authority import build_workspace_memory_authority
from imperaos.memory.workspace_models import WorkspaceMemoryAuthorityHealth
from imperaos.release.gate_models import RcGateEvidenceSnapshot
from imperaos.release.snapshot import build_rc_gate_evidence_snapshot
from imperaos.release_decision.snapshot import build_rc_release_decision_snapshot
from imperaos.runtime.config import RuntimeConfig
from imperaos.runtime.paths import CONTROL_PLANE_STATE_ROOT

SNAPSHOT_CONTRACT_VERSION = "control-plane.snapshot/v1"
STALE_AFTER_MS = 5 * 60 * 1000


def classify_data_source(
    *,
    runtime_mode: str,
    bridge_mode: str,
    used_fixture: bool,
    cli_available: bool,
    generated_at: datetime | None,
    now: datetime | None = None,
) -> DataSourceState:
    current = now or datetime.now(UTC)
    if generated_at is None:
        age_ms = None
    else:
        source_time = generated_at if generated_at.tzinfo else generated_at.replace(tzinfo=UTC)
        age_ms = max(0, int((current - source_time).total_seconds() * 1000))

    live_requested = runtime_mode in {"tauri", "live"} or bridge_mode == "tauri"
    if used_fixture:
        mode = "preview_fixture"
        source_reason = "explicit preview fixture"
    elif not cli_available:
        mode = "error"
        source_reason = "CLI unavailable"
    elif live_requested:
        mode = "tauri_live"
        source_reason = "Tauri bridge invoked live CLI snapshot"
    else:
        mode = "cli_live"
        source_reason = "CLI generated live snapshot"

    if mode != "error" and age_ms is not None and age_ms > STALE_AFTER_MS:
        mode = "stale_cache"
        freshness = "stale"
    elif mode == "error":
        freshness = "unknown"
    else:
        freshness = "fresh"

    return DataSourceState(
        mode=mode,
        is_mock=used_fixture,
        is_silent_fallback=used_fixture and live_requested,
        last_refresh_utc=generated_at,
        age_ms=age_ms,
        freshness=freshness,
        contract_version=SNAPSHOT_CONTRACT_VERSION,
        source_reason=source_reason,
    )


def build_control_plane_snapshot(
    *,
    root_dir: str | Path = CONTROL_PLANE_STATE_ROOT,
    profile: str = "enterprise",
    evidence_root: str | Path = "artifacts",
    include_debug: bool = False,
    now: datetime | None = None,
    runtime_mode: str = "cli",
    bridge_mode: str = "cli",
    used_fixture: bool = False,
    cli_available: bool = True,
) -> ControlPlaneSnapshot:
    _ = include_debug
    generated_at = now or datetime.now(UTC)
    config = RuntimeConfig.from_profile(profile)
    root = Path(root_dir)
    registry = AgentRegistry(root_dir=root)
    coordinator = ControlPlaneRunCoordinator(
        config=config,
        registry=registry,
        root_dir=root,
    )
    data_source = classify_data_source(
        runtime_mode=runtime_mode,
        bridge_mode=bridge_mode,
        used_fixture=used_fixture,
        cli_available=cli_available,
        generated_at=generated_at,
        now=generated_at,
    )

    partial_reasons: list[str] = []
    agents = _agent_summaries(registry)
    runs = _run_summaries(coordinator)
    approvals = _approval_summaries(config)
    claims = ClaimGuard(config=config).evaluate(evidence_root=evidence_root)
    evidence_packs = _evidence_pack_summaries(
        evidence_root=Path(evidence_root),
        claims_status=_enterprise_claim_status(claims.model_dump(mode="json")),
    )
    policy_packs = [_active_policy_pack(config)]
    reports = _report_summaries(Path(evidence_root), evidence_packs=evidence_packs)
    execution_surfaces = _execution_surfaces(claims.model_dump(mode="json"), config=config)
    alerts = _alerts(
        generated_at=generated_at,
        claims=claims.model_dump(mode="json"),
        reports=reports,
        data_source=data_source,
    )
    code_intelligence = build_code_intelligence_summary(
        evidence_root=evidence_root,
        generated_at=generated_at,
    )
    pilot_operations = build_pilot_operations_status(
        evidence_root=evidence_root,
        generated_at=generated_at,
    )
    design_partner_beta = build_design_partner_beta_status(
        evidence_root=evidence_root,
        generated_at=generated_at,
    )
    provider_governance = build_provider_governance_snapshot(
        profile=profile,
        generated_at=generated_at,
    )
    provider_runtime = _provider_runtime_snapshot(Path(evidence_root), generated_at=generated_at)
    target_evidence_closure = _target_evidence_closure_snapshot(
        Path(evidence_root),
        generated_at=generated_at,
    )
    field_evidence_snapshot = build_design_partner_field_evidence_snapshot(
        artifact_root=Path(evidence_root),
        generated_at=generated_at,
    )
    design_partner_field_evidence = DesignPartnerFieldEvidenceSnapshot.model_validate(
        field_evidence_snapshot.model_dump(mode="json", by_alias=True)
    )
    handoff_snapshot = build_design_partner_handoff_snapshot(
        artifact_root=Path(evidence_root),
    )
    design_partner_handoff = DesignPartnerHandoffSnapshot.model_validate(
        handoff_snapshot.model_dump(mode="json", by_alias=True)
    )
    mainline_rc_freeze_snapshot = build_mainline_rc_freeze_snapshot(
        artifact_root=Path(evidence_root),
    )
    mainline_rc_freeze = MainlineRcFreezeSnapshot.model_validate(
        mainline_rc_freeze_snapshot.model_dump(mode="json", by_alias=True)
    )
    rc_gate_evidence_snapshot = build_rc_gate_evidence_snapshot(
        evidence_root=Path(evidence_root),
        profile=profile,
    )
    rc_gate_evidence = RcGateEvidenceSnapshot.model_validate(
        rc_gate_evidence_snapshot.model_dump(mode="json", by_alias=True)
    )
    rc_release_decision = build_rc_release_decision_snapshot(
        evidence_root=Path(evidence_root),
        profile=profile,
    )
    enterprise_workspace = build_enterprise_workspace_snapshot(
        config=config,
        root_dir=root,
    )
    memory_governance = build_memory_governance_snapshot(config=config, evidence_root=evidence_root)
    memory_runtime = build_memory_runtime_snapshot(
        config=config,
        evidence_root=evidence_root,
        generated_at=generated_at,
    )
    memory_sync = build_memory_sync_snapshot(
        config=config,
        evidence_root=evidence_root,
        generated_at=generated_at,
    )
    try:
        memory_authority = build_workspace_memory_authority(
            config,
            evidence_root=Path(evidence_root) / "memory-authority",
        ).health()
    except Exception as exc:  # pragma: no cover - snapshot must stay diagnosable
        memory_authority = WorkspaceMemoryAuthorityHealth(
            status="blocked",
            blockingReasons=[f"MEMORY_AUTHORITY_SNAPSHOT_FAILED:{type(exc).__name__}"],
        )
    try:
        memory_semantic_index = build_memory_semantic_snapshot(
            config=config,
            evidence_root=evidence_root,
            generated_at=generated_at,
        )
    except Exception as exc:  # pragma: no cover - snapshot must stay diagnosable
        memory_semantic_index = MemorySemanticIndexSnapshot(
            status="blocked",
            enabled=False,
            reasonCodes=[f"MEMORY_SEMANTIC_SNAPSHOT_FAILED:{type(exc).__name__}"],
        )
    try:
        memory_policy_enforcement = build_memory_policy_enforcement_snapshot(
            config=config,
            evidence_root=evidence_root,
            generated_at=generated_at,
        )
    except Exception as exc:  # pragma: no cover - snapshot must stay diagnosable
        memory_policy_enforcement = MemoryPolicyEnforcementSnapshot(
            generatedAtUtc=generated_at,
            status="blocked",
            enabled=config.memory.runtime.policy_enforcement_enabled,
            semanticRuntimeMode=config.memory.runtime.semantic_runtime_mode,
            reasonCodes=[f"MEMORY_POLICY_SNAPSHOT_FAILED:{type(exc).__name__}"],
        )
    governed_pilot_workflow = build_governed_pilot_workflow_snapshot(
        artifact_root=evidence_root,
        generated_at=generated_at,
    )
    design_partner_rc = build_design_partner_rc_status(
        data_source=data_source,
        claims=claims.model_dump(mode="json"),
        evidence_packs=evidence_packs,
        reports=reports,
        alerts=alerts,
        execution_surfaces=execution_surfaces,
        design_partner_beta=design_partner_beta,
        provider_governance=provider_governance,
        generated_at=generated_at,
    )
    pilot_launch = build_pilot_launch_readiness_status(
        artifact_root=Path(evidence_root),
        claims=claims.model_dump(mode="json"),
        alerts=alerts,
        generated_at=generated_at,
    )
    logs = _logs(generated_at=generated_at, runs=runs, approvals=approvals, alerts=alerts)
    operations = _operation_descriptors(config=config, generated_at=generated_at)
    admin = _admin_summary(config)
    missing_signals = _missing_system_signals(reports)
    if missing_signals:
        partial_reasons.extend(missing_signals)
    if data_source.mode in {"preview_fixture", "stale_cache", "error"}:
        partial_reasons.append(f"DATA_SOURCE_{str(data_source.mode).upper()}")

    system = _system_summary(
        config=config,
        root_dir=root,
        data_source=data_source,
        claims=claims.model_dump(mode="json"),
        missing_signals=missing_signals,
    )
    dashboard = DashboardSummary(
        agent_count=len(agents),
        run_count=len(runs),
        pending_approval_count=sum(1 for item in approvals if item.status == "pending"),
        evidence_pack_count=len(evidence_packs),
        active_alert_count=sum(1 for item in alerts if item.status == "active"),
        blocked_claim_count=_claim_count(claims.model_dump(mode="json"), "blocked"),
        conditional_claim_count=_claim_count(claims.model_dump(mode="json"), "conditional"),
    )

    return ControlPlaneSnapshot(
        generated_at_utc=generated_at,
        data_source=data_source,
        system=system,
        dashboard=dashboard,
        agents=agents,
        runs=runs,
        approvals=approvals,
        evidence_packs=evidence_packs,
        policy_packs=policy_packs,
        execution_surfaces=execution_surfaces,
        logs=logs,
        alerts=alerts,
        reports=reports,
        operations=operations,
        admin=admin,
        design_partner_rc=design_partner_rc,
        pilot_launch=pilot_launch,
        code_intelligence=code_intelligence,
        pilot_operations=pilot_operations,
        design_partner_beta=design_partner_beta,
        provider_governance=provider_governance,
        provider_runtime=provider_runtime,
        target_evidence_closure=target_evidence_closure,
        design_partner_field_evidence=design_partner_field_evidence,
        design_partner_handoff=design_partner_handoff,
        mainline_rc_freeze=mainline_rc_freeze,
        rc_gate_evidence=rc_gate_evidence,
        rc_release_decision=rc_release_decision,
        enterprise_workspace=enterprise_workspace,
        memory_governance=memory_governance,
        memory_runtime=memory_runtime,
        memory_sync=memory_sync,
        memory_authority=memory_authority,
        memory_semantic_index=memory_semantic_index,
        memory_policy_enforcement=memory_policy_enforcement,
        governed_pilot_workflow=governed_pilot_workflow,
        quick_actions=_quick_actions(approvals=approvals, evidence_packs=evidence_packs),
        partial_reasons=sorted(set(partial_reasons)),
    )


def _provider_runtime_snapshot(
    evidence_root: Path,
    *,
    generated_at: datetime,
) -> ProviderRuntimeSnapshot:
    runtime_root = evidence_root / "provider-runtime"
    invocations: list[ProviderInvocationArtifact] = []
    for path in sorted((runtime_root / "invocations").glob("*.json"))[-5:]:
        try:
            invocations.append(
                ProviderInvocationArtifact.model_validate_json(path.read_text(encoding="utf-8"))
            )
        except ValueError:
            continue
    proofs: list[ProviderWorkflowProofArtifact] = []
    for path in sorted((runtime_root / "workflow-proof").glob("*.json"))[-5:]:
        try:
            proofs.append(
                ProviderWorkflowProofArtifact.model_validate_json(path.read_text(encoding="utf-8"))
            )
        except ValueError:
            continue
    return ProviderRuntimeSnapshot(
        generatedAtUtc=generated_at,
        enabled=bool(invocations or proofs),
        latestInvocations=invocations,
        workflowProofs=proofs,
        blockingReasons=[],
    )


def _target_evidence_closure_snapshot(
    evidence_root: Path,
    *,
    generated_at: datetime,
) -> TargetEvidenceClosureSummary:
    target_root = evidence_root / "design-partner-target-evidence"
    bundle_path = target_root / "target_evidence_bundle.json"
    attestation_path = target_root / "operator_attestation.json"
    if not bundle_path.exists():
        return TargetEvidenceClosureSummary(
            generatedAtUtc=generated_at,
            status="unknown",
            blockingReasons=[],
            warnings=["TARGET_EVIDENCE_NOT_COLLECTED"],
            blockedClaims=[],
            attestationStatus="missing",
        )
    try:
        bundle = TargetEvidenceBundle.model_validate_json(bundle_path.read_text(encoding="utf-8"))
    except ValueError:
        return TargetEvidenceClosureSummary(
            generatedAtUtc=generated_at,
            status="blocked",
            blockingReasons=["TARGET_EVIDENCE_BUNDLE_INVALID"],
            warnings=[],
            blockedClaims=[],
            attestationStatus="invalid",
        )
    mode = None
    session_path = target_root / "session.json"
    if session_path.exists():
        try:
            session_payload = json.loads(session_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            mode = None
        else:
            session_mode = session_payload.get("mode")
            if session_mode in {"rehearsal", "target"}:
                mode = session_mode
    attestation_status = "missing"
    if attestation_path.exists():
        attestation_status = "present"
        try:
            payload = json.loads(attestation_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            attestation_status = "invalid"
        else:
            if payload.get("signedAtUtc"):
                attestation_status = "signed"
    return TargetEvidenceClosureSummary(
        generatedAtUtc=generated_at,
        status=bundle.status,
        sessionId=bundle.session_id,
        mode=mode,
        evidenceMode="hash_only",
        rawPersistence=False,
        blockingReasons=bundle.blocking_reasons,
        warnings=bundle.warnings,
        blockedClaims=bundle.claim_boundary.blocked_claims,
        attestationStatus=attestation_status,
    )


def _agent_summaries(registry: AgentRegistry) -> list[AgentSummary]:
    items: list[AgentSummary] = []
    for record in registry.list_agents():
        registry_item = agent_registry_v2_item(record)
        items.append(
            AgentSummary(
                agent_id=record.agent_id,
                display_name=record.spec.display_name,
                runtime_kind=str(record.spec.runtime_kind),
                agent_type=registry_item.agent_type,
                status=str(record.status),
                readiness=str(record.readiness),
                owner_team=record.spec.owner.team,
                policy_pack_id=registry_item.policy_pack_id,
                risk_profile=registry_item.risk_profile,
                last_run_id=record.last_run_id,
                last_evidence_pack_id=record.last_evidence_pack_id,
                last_evidence_status=registry_item.last_evidence_status,
            )
        )
    return items


def _run_summaries(coordinator: ControlPlaneRunCoordinator) -> list[RunSnapshotSummary]:
    return [
        RunSnapshotSummary(
            run_id=item.run_id,
            agent_id=item.agent_id,
            profile=item.profile,
            status=str(item.status),
            submitted_by=item.submitted_by,
            identity_ref=item.identity_ref,
            input_hash=item.input_hash,
            policy_hash=item.policy_hash,
            started_at=item.started_at,
            completed_at=item.completed_at,
            approval_ids=item.approval_ids,
            artifact_refs=item.artifact_refs,
            evidence_pack_id=item.evidence_pack_id,
            blocking_reasons=item.blocking_reasons,
            next_actions=item.next_actions,
        )
        for item in coordinator.list_runs()
    ]


def _approval_summaries(config: RuntimeConfig) -> list[ApprovalSnapshotSummary]:
    store = ApprovalStore(config.governance.approval_store_path)
    items: list[ApprovalSnapshotSummary] = []
    for ticket in store.list_pending(
        workspace_id=config.memory.workspace_authority.default_workspace_id
    ):
        items.append(
            ApprovalSnapshotSummary(
                approval_id=ticket.approval_id,
                run_id=ticket.run_id,
                status=str(ticket.status),
                target_kind=ticket.target_kind,
                target_ref=ticket.target_ref,
                action_hash=ticket.action_hash,
                policy_hash=ticket.policy_hash,
                request_hash=ticket.request_hash,
                snapshot_hash=ticket.snapshot_hash,
                execution_status=str(ticket.execution_status),
                created_at=ticket.created_at,
                expires_at=ticket.expires_at,
                actor=ticket.actor,
                disabled_reason=None,
            )
        )
    return items


def _evidence_pack_summaries(
    *,
    evidence_root: Path,
    claims_status: str,
) -> list[EvidencePackSummary]:
    packs: list[EvidencePackSummary] = []
    for path in sorted((evidence_root / "control-plane" / "evidence").glob("*/manifest.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            manifest = EvidencePackManifest.model_validate(
                {key: value for key, value in payload.items() if key != "integrity"}
            )
        except Exception:  # noqa: BLE001
            packs.append(
                EvidencePackSummary(
                    pack_id=path.parent.name,
                    run_id=None,
                    created_at_utc=None,
                    signature_status="invalid",
                    hash_chain_status="broken",
                    replay_status="failed",
                    claim_guard_status="blocked",
                    redaction_status="unknown",
                    artifact_count=0,
                    export_path=str(path.parent),
                    blocking_reasons=["EVIDENCE_MANIFEST_INVALID"],
                )
            )
            continue

        signature_status = (
            "valid"
            if manifest.verification.signature_verified
            else "missing"
            if manifest.signature.mode == "unsigned"
            else "pending"
        )
        packs.append(
            EvidencePackSummary(
                pack_id=manifest.pack_id,
                run_id=manifest.run_id,
                created_at_utc=manifest.generated_at,
                signature_status=signature_status,
                hash_chain_status="valid"
                if manifest.verification.hash_chain_verified
                else "pending",
                replay_status="passed"
                if manifest.verification.replay_verified
                else "not_available",
                claim_guard_status="ready" if claims_status == "allowed" else claims_status,
                redaction_status="passed"
                if manifest.redaction_summary.secrets_redacted
                and manifest.redaction_summary.pii_redaction_enabled
                else "warning",
                artifact_count=len(manifest.items),
                export_path=str(path.parent),
                blocking_reasons=list(manifest.warnings),
            )
        )
    return packs


def _active_policy_pack(config: RuntimeConfig) -> PolicyPackSummary:
    policy_path = Path(config.governance.policy_path)
    exists = policy_path.exists()
    rule_count = 0
    blocking_reasons: list[str] = [] if exists else ["POLICY_FILE_MISSING"]
    if exists:
        try:
            policy = load_policy(policy_path).policy
            rule_count = (
                len(policy.task_rules)
                + len(policy.tool_rules)
                + len(policy.approval_rules)
                + len(policy.handoff_rules)
                + len(policy.memory_scope_rules)
            )
        except Exception:  # noqa: BLE001
            blocking_reasons.append("POLICY_FILE_INVALID")
    return PolicyPackSummary(
        pack_id="active-runtime-policy",
        label="Active runtime policy",
        version=config.governance.decision_engine_version,
        status="active" if exists else "missing",
        policy_hash=f"sha256:{file_sha256(policy_path)}" if exists else None,
        rule_count=rule_count,
        source_path=str(policy_path),
        blocking_reasons=blocking_reasons,
    )


def _execution_surfaces(
    claims: dict[str, Any],
    *,
    config: RuntimeConfig,
) -> list[ExecutionSurfaceSummary]:
    claim_by_id = {
        str(item.get("claim_id")): item
        for item in claims.get("claims", [])
        if isinstance(item, dict)
    }

    def from_claim(surface_id: str, label: str, claim_id: str) -> ExecutionSurfaceSummary:
        claim = claim_by_id.get(claim_id, {})
        status = _surface_status(str(claim.get("status", "blocked")))
        reasons = [str(item) for item in claim.get("blocking_reasons", [])]
        return ExecutionSurfaceSummary(
            surface_id=surface_id,
            label=label,
            status=status,
            claim_id=claim_id,
            reason_codes=reasons,
            human_summary=_surface_summary(status, reasons),
        )

    return [
        ExecutionSurfaceSummary(
            surface_id="core-runtime",
            label="Core Runtime",
            status="ready",
            claim_id=None,
            reason_codes=[],
            human_summary="Core CLI runtime is available for self-hosted operation.",
        ),
        ExecutionSurfaceSummary(
            surface_id="team-runtime",
            label="Team Runtime",
            status="ready" if config.team.enabled else "blocked",
            claim_id=None,
            reason_codes=[] if config.team.enabled else ["TEAM_RUNTIME_DISABLED"],
            human_summary="Team runtime is enabled."
            if config.team.enabled
            else "Team runtime is disabled by configuration.",
        ),
        from_claim(
            "computer-use",
            "Computer-use",
            "live-macos-computer-use",
        ),
        from_claim(
            "public-desktop-installer",
            "Public Desktop Installer",
            "public-desktop-installer",
        ),
    ]


def _report_summaries(
    evidence_root: Path,
    *,
    evidence_packs: list[EvidencePackSummary],
) -> list[ReportSummary]:
    artifact_root = _pilot_artifact_root(evidence_root)
    candidates = [
        (
            "security-baseline",
            "security",
            "Security baseline",
            artifact_root / "security_posture.json",
        ),
        (
            "qualification",
            "qualification",
            "Qualification report",
            artifact_root / "qualification_report.json",
        ),
        (
            "ga-readiness",
            "readiness",
            "GA readiness report",
            artifact_root / "ga_readiness_report.json",
        ),
        ("metrics", "metrics", "Metrics snapshot", artifact_root / "metrics_snapshot.json"),
        (
            "support-bundle",
            "support",
            "Support bundle manifest",
            artifact_root / "support_bundle_manifest.json",
        ),
        (
            "team-pilot",
            "readiness",
            "Team pilot report",
            artifact_root / "team_pilot_report.json",
        ),
        (
            "pilot-launch",
            "readiness",
            "Pilot launch report",
            artifact_root / "design-partner-pilot" / "PILOT_LAUNCH_REPORT.md",
        ),
        (
            "enterprise-hat-a",
            "qualification",
            "Enterprise Hat A closure",
            artifact_root / "enterprise-hat-a" / "ENTERPRISE_HAT_A_CLOSURE.md",
        ),
        (
            "install-rehearsal",
            "readiness",
            "Install rehearsal report",
            artifact_root / "install-rehearsal" / "INSTALL_REHEARSAL_REPORT.md",
        ),
        (
            "evidence-corpus",
            "evidence",
            "Evidence corpus report",
            artifact_root / "evidence-corpus" / "corpus_verification_report.json",
        ),
        (
            "security-review",
            "security",
            "Security review pack",
            artifact_root / "security-review" / "SECURITY_REVIEW_SUMMARY.md",
        ),
        (
            "pilot-metrics",
            "metrics",
            "Pilot metrics",
            artifact_root / "design-partner-pilot" / "pilot_metrics.json",
        ),
    ]
    reports = [
        ReportSummary(
            report_id=report_id,
            kind=kind,
            title=title,
            status="ready" if path.exists() else "missing",
            path=str(path) if path.exists() else None,
            generated_at_utc=_mtime(path) if path.exists() else None,
            blocking_reasons=[]
            if path.exists()
            else [f"{report_id.upper().replace('-', '_')}_MISSING"],
        )
        for report_id, kind, title, path in candidates
    ]
    for pack in evidence_packs:
        reports.append(
            ReportSummary(
                report_id=f"evidence-{pack.pack_id}",
                kind="evidence",
                title=f"Evidence pack {pack.pack_id}",
                status="ready" if pack.signature_status in {"valid", "pending"} else "conditional",
                path=pack.export_path,
                generated_at_utc=pack.created_at_utc,
                blocking_reasons=pack.blocking_reasons,
            )
        )
    return reports


def _alerts(
    *,
    generated_at: datetime,
    claims: dict[str, Any],
    reports: list[ReportSummary],
    data_source: DataSourceState,
) -> list[AlertSummary]:
    alerts: list[AlertSummary] = []
    if data_source.is_silent_fallback:
        alerts.append(
            AlertSummary(
                alert_id="silent-mock-fallback",
                severity="critical",
                status="active",
                title="Silent mock fallback detected",
                reason_code="SILENT_MOCK_FALLBACK",
                recommended_action=(
                    "Stop the pilot gate and restore live bridge data before continuing."
                ),
            )
        )
    for claim in claims.get("claims", []):
        if not isinstance(claim, dict):
            continue
        status = str(claim.get("status", ""))
        reasons = [str(item) for item in claim.get("blocking_reasons", [])]
        if status in {"blocked", "conditional"} and reasons:
            alerts.append(
                AlertSummary(
                    alert_id=f"claim-{claim.get('claim_id')}",
                    severity="error" if status == "blocked" else "warning",
                    status="active",
                    title=f"Claim {claim.get('claim_id')} is {status}",
                    reason_code=reasons[0],
                    recommended_action=(
                        "Attach the required signed evidence or keep the claim blocked."
                    ),
                )
            )
    for report in reports:
        if report.status == "missing" and report.kind in {"qualification", "metrics"}:
            alerts.append(
                AlertSummary(
                    alert_id=f"missing-{report.report_id}",
                    severity="warning",
                    status="active",
                    title=f"{report.title} is missing",
                    reason_code=report.blocking_reasons[0],
                    recommended_action=(
                        "Generate the report before promoting the pilot readiness claim."
                    ),
                )
            )
    if not alerts:
        alerts.append(
            AlertSummary(
                alert_id="snapshot-ok",
                severity="info",
                status="resolved",
                title="No active control-plane alerts",
                reason_code="NO_ACTIVE_ALERTS",
                recommended_action=(
                    "Continue monitoring snapshot freshness and evidence verification."
                ),
            )
        )
    _ = generated_at
    return alerts


def _logs(
    *,
    generated_at: datetime,
    runs: list[RunSnapshotSummary],
    approvals: list[ApprovalSnapshotSummary],
    alerts: list[AlertSummary],
) -> list[LogEventSummary]:
    logs = [
        LogEventSummary(
            event_id="snapshot-generated",
            timestamp=generated_at,
            severity="info",
            source="control-plane.snapshot",
            message="Control-plane snapshot generated.",
        )
    ]
    for run in runs[:5]:
        logs.append(
            LogEventSummary(
                event_id=f"run-{run.run_id}",
                timestamp=run.started_at,
                severity="warning" if run.blocking_reasons else "info",
                source="control-plane.run",
                message=f"Run {run.run_id} is {run.status}.",
                run_id=run.run_id,
                evidence_pack_id=run.evidence_pack_id,
            )
        )
    for approval in approvals[:5]:
        logs.append(
            LogEventSummary(
                event_id=f"approval-{approval.approval_id}",
                timestamp=approval.created_at,
                severity="warning",
                source="governance.approval",
                message=f"Approval {approval.approval_id} is pending.",
                run_id=approval.run_id,
            )
        )
    for alert in alerts[:5]:
        logs.append(
            LogEventSummary(
                event_id=f"alert-{alert.alert_id}",
                timestamp=generated_at,
                severity=alert.severity,
                source="control-plane.alerts",
                message=alert.title,
                run_id=alert.linked_run_id,
                evidence_pack_id=alert.linked_evidence_pack_id,
            )
        )
    return logs


def _operation_descriptors(
    *,
    config: RuntimeConfig,
    generated_at: datetime,
) -> list[OperationDescriptor]:
    identity = _describe_actor_safe(config)
    signing = key_status(config)

    return [
        OperationDescriptor(
            operation_id="auth.whoami",
            category="identity",
            label="Resolve operator identity",
            description="Reads the current signed operator assertion.",
            risk_level="read_only",
            permission="config.read",
            supports_dry_run=True,
            enabled=True,
            last_result=_result_from_bool(
                bool(identity.get("verified") or not config.identity.enabled),
                generated_at=generated_at,
                passed="Identity assertion is usable.",
                failed=str(identity.get("error_code") or "IDENTITY_UNVERIFIED"),
            ),
        ),
        OperationDescriptor(
            operation_id="security.baseline",
            category="security",
            label="Evaluate security baseline",
            description="Runs the enterprise security baseline in read-only mode.",
            risk_level="read_only",
            permission="audit.read",
            supports_dry_run=True,
            enabled=True,
            last_result=OperationResultSummary(
                status="not_run",
                summary="Available as a read-only preflight command.",
                generated_at_utc=generated_at,
            ),
        ),
        OperationDescriptor(
            operation_id="qualification.run",
            category="qualification",
            label="Run qualification preflight",
            description=(
                "Runs a constrained qualification preflight and summarizes missing evidence."
            ),
            risk_level="low",
            permission="qualification.run",
            supports_dry_run=True,
            enabled=True,
            last_result=OperationResultSummary(
                status="not_run",
                summary="Qualification has not been run from this snapshot.",
                generated_at_utc=generated_at,
            ),
        ),
        OperationDescriptor(
            operation_id="install.rehearsal",
            category="qualification",
            label="Run install rehearsal",
            description="Runs the design partner source/CLI install rehearsal in a scoped root.",
            risk_level="low",
            permission="qualification.run",
            supports_dry_run=True,
            enabled=True,
            last_result=OperationResultSummary(
                status="not_run",
                summary="Available through the pilot launch operations surface.",
                generated_at_utc=generated_at,
            ),
        ),
        OperationDescriptor(
            operation_id="keys.status",
            category="keys",
            label="Check signing keys",
            description=(
                "Inspects signing provider readiness without exposing private key material."
            ),
            risk_level="read_only",
            permission="keys.read",
            supports_dry_run=True,
            enabled=True,
            last_result=_result_from_bool(
                bool(signing.get("enterprise_compatible") or config.keys.provider == "disabled"),
                generated_at=generated_at,
                passed="Signing provider status is readable.",
                failed="Signing provider is not enterprise compatible.",
            ),
        ),
        OperationDescriptor(
            operation_id="support.bundle.export",
            category="support",
            label="Export support bundle",
            description="Creates a redacted support bundle for pilot debugging.",
            risk_level="low",
            permission="support.export",
            supports_dry_run=False,
            enabled=True,
            last_result=OperationResultSummary(
                status="not_run",
                summary="No support bundle export has been requested from this snapshot.",
                generated_at_utc=generated_at,
            ),
        ),
        OperationDescriptor(
            operation_id="security.review",
            category="security",
            label="Generate security review",
            description="Generates the pilot security review pack and no-secret scan.",
            risk_level="read_only",
            permission="audit.read",
            supports_dry_run=True,
            enabled=True,
            last_result=OperationResultSummary(
                status="not_run",
                summary="Available as a security review pack generation command.",
                generated_at_utc=generated_at,
            ),
        ),
        OperationDescriptor(
            operation_id="backup.create",
            category="backup",
            label="Create backup",
            description=(
                "Creates a self-hosted runtime backup. "
                "The UI keeps this action confirmation-gated."
            ),
            risk_level="medium",
            permission="backup.create",
            supports_dry_run=False,
            enabled=False,
            disabled_reason="CONFIRMATION_REQUIRED",
            last_result=None,
        ),
        OperationDescriptor(
            operation_id="restore.verify",
            category="restore",
            label="Verify restore",
            description="Verifies a restore target without mutating production state.",
            risk_level="medium",
            permission="restore.verify",
            supports_dry_run=True,
            enabled=False,
            disabled_reason="RESTORE_TARGET_REQUIRED",
            last_result=None,
        ),
        OperationDescriptor(
            operation_id="migration.apply",
            category="migration",
            label="Apply migration",
            description="Production migration execution is out of scope for pilot UI.",
            risk_level="destructive",
            permission="config.write",
            supports_dry_run=True,
            enabled=False,
            disabled_reason="DESTRUCTIVE_OPERATION_DISABLED",
            last_result=None,
        ),
    ]


def _admin_summary(config: RuntimeConfig) -> AdminSummary:
    return build_admin_summary(config, policy_pack=_active_policy_pack(config))


def _describe_actor_safe(config: RuntimeConfig) -> dict[str, Any]:
    if not config.identity.enabled:
        return {
            "identity_enabled": False,
            "verified": True,
            "actor": {
                "actor_id": "identity-disabled",
                "subject": "identity disabled",
                "issuer": None,
                "roles": ["viewer"],
                "permissions": ["config.read"],
            },
        }
    return describe_actor(config)


def _system_summary(
    *,
    config: RuntimeConfig,
    root_dir: Path,
    data_source: DataSourceState,
    claims: dict[str, Any],
    missing_signals: list[str],
) -> SystemSummary:
    claim_blockers = sorted(
        {
            str(reason)
            for claim in claims.get("claims", [])
            if isinstance(claim, dict)
            for reason in claim.get("blocking_reasons", [])
        }
    )
    doctor_status = "healthy"
    if any(reason in {"SIGNING_UNAVAILABLE", "POLICY_UNAVAILABLE"} for reason in claim_blockers):
        doctor_status = "blocked"
    health = _health_state(
        data_source=data_source,
        doctor_status=doctor_status,
        missing_signals=missing_signals,
        blocking_reasons=claim_blockers,
    )
    return SystemSummary(
        profile=config.profile_name,
        root_dir=str(root_dir),
        core_version=__version__,
        contract_version=OPERATOR_PANEL_CONTRACT_VERSION,
        health=health,
        doctor={
            "status": doctor_status,
            "profile": config.profile_name,
            "blocking_reasons": claim_blockers,
        },
        capabilities={
            "controlPlaneSnapshot": True,
            "evidenceExport": True,
            "claimGuard": True,
            "computerUseLive": False,
        },
        config_summary={
            "governanceEnabled": config.governance.enabled,
            "policyFailMode": config.governance.policy_fail_mode,
            "identityEnabled": config.identity.enabled,
            "keysProvider": config.keys.provider,
            "privacyMode": config.privacy_mode,
            "piiRedactionEnabled": config.governance.pii_redaction_enabled,
        },
        source_map={
            "agents": "control-plane registry",
            "runs": "control-plane run store",
            "approvals": "governance approval store",
            "claims": "claim guard",
            "reports": "artifacts directory",
        },
        warnings=missing_signals,
    )


def _health_state(
    *,
    data_source: DataSourceState,
    doctor_status: str,
    missing_signals: list[str],
    blocking_reasons: list[str],
) -> SystemHealthState:
    if data_source.mode == "error":
        status = "unknown"
        confidence = "low"
        summary = "Snapshot source is unavailable."
    elif data_source.is_silent_fallback:
        status = "blocked"
        confidence = "low"
        summary = "Live mode fell back to mock data and must fail closed."
    elif doctor_status == "blocked":
        status = "blocked"
        confidence = "medium"
        summary = "Control plane has blocking readiness reasons."
    elif missing_signals or data_source.mode in {"preview_fixture", "stale_cache"}:
        status = "partial"
        confidence = "medium" if data_source.mode != "preview_fixture" else "low"
        summary = "Control plane is reachable but required pilot-readiness signals are incomplete."
    else:
        status = "healthy"
        confidence = "high"
        summary = "Required control-plane signals are present."
    return SystemHealthState(
        status=status,
        confidence=confidence,
        missing_signals=missing_signals,
        blocking_reasons=blocking_reasons,
        last_doctor_status=doctor_status,
        human_summary=summary,
    )


def _quick_actions(
    *,
    approvals: list[ApprovalSnapshotSummary],
    evidence_packs: list[EvidencePackSummary],
) -> list[QuickActionSummary]:
    return [
        QuickActionSummary(
            action_id="approval.review",
            label="Review pending approvals",
            enabled=bool(approvals),
            disabled_reason=None if approvals else "NO_PENDING_APPROVALS",
        ),
        QuickActionSummary(
            action_id="evidence.verify",
            label="Verify latest evidence pack",
            enabled=bool(evidence_packs),
            disabled_reason=None if evidence_packs else "NO_EVIDENCE_PACKS",
        ),
        QuickActionSummary(
            action_id="computer-use.live-start",
            label="Start live computer-use",
            enabled=False,
            disabled_reason="COMPUTER_USE_CLAIM_BLOCKED",
        ),
    ]


def _missing_system_signals(reports: list[ReportSummary]) -> list[str]:
    by_id = {item.report_id: item for item in reports}
    missing: list[str] = []
    if by_id.get("metrics") and by_id["metrics"].status == "missing":
        missing.append("metrics_snapshot")
    if by_id.get("qualification") and by_id["qualification"].status == "missing":
        missing.append("qualification_report")
    return missing


def _enterprise_claim_status(claims: dict[str, Any]) -> str:
    for claim in claims.get("claims", []):
        if (
            isinstance(claim, dict)
            and claim.get("claim_id") == "enterprise-self-hosted-agent-control-plane"
        ):
            return str(claim.get("status", "conditional"))
    return "conditional"


def _pilot_artifact_root(path: Path) -> Path:
    parts = path.parts
    if "evidence-corpus" in parts:
        return Path(*parts[: parts.index("evidence-corpus")]) or Path(".")
    return path


def _surface_status(claim_status: str) -> str:
    if claim_status == "allowed":
        return "ready"
    if claim_status in {"conditional", "blocked", "deferred"}:
        return "conditional" if claim_status == "conditional" else "blocked"
    return "blocked"


def _surface_summary(status: str, reasons: list[str]) -> str:
    if status == "ready":
        return "Required evidence is present for this surface."
    if not reasons:
        return "Surface is not ready for pilot operation."
    return f"Blocked by {', '.join(reasons[:3])}."


def _claim_count(claims: dict[str, Any], status: str) -> int:
    return sum(
        1
        for claim in claims.get("claims", [])
        if isinstance(claim, dict) and claim.get("status") == status
    )


def _result_from_bool(
    value: bool,
    *,
    generated_at: datetime,
    passed: str,
    failed: str,
) -> OperationResultSummary:
    return OperationResultSummary(
        status="passed" if value else "blocked",
        summary=passed if value else failed,
        generated_at_utc=generated_at,
        error_code=None if value else failed,
    )


def _mtime(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
