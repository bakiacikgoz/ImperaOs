from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import yaml

from imperaos.control_plane.claim_guard import ClaimGuard
from imperaos.control_plane.pilot_workflow_evidence import (
    PilotWorkflowEvidenceWriter,
    find_raw_leaks,
    mirror_latest,
    safe_hash_payload,
    sha256_file,
    sha256_text,
)
from imperaos.control_plane.pilot_workflow_models import (
    GovernedPilotScenario,
    GovernedPilotWorkflowReport,
    GovernedPilotWorkflowSnapshot,
    GovernedPilotWorkflowSpec,
    PilotWorkflowComponentResult,
    PilotWorkflowStepResult,
    PilotWorkflowValidationResult,
)
from imperaos.control_plane.pilot_workflow_verifier import (
    verify_governed_pilot_workflow_report,
)
from imperaos.control_plane.provider_invocation import (
    ProviderInvocationCoordinator,
    ProviderInvocationRequest,
)
from imperaos.memory.runtime_bridge import RuntimeMemoryRequest
from imperaos.memory.runtime_policy_fixtures import build_memory_runtime_policy_fixture
from imperaos.runtime.config import RuntimeConfig

BLOCKED_CLAIM_STATUSES = {"blocked", "deferred"}
UNSUPPORTED_LIVE_CLAIMS = {
    "public-desktop-installer",
    "live-macos-computer-use",
    "live-windows-computer-use",
    "live-linux-computer-use",
    "multi-tenant-cloud-control-plane",
}


def load_governed_pilot_workflow_spec(path: str | Path) -> GovernedPilotWorkflowSpec:
    spec_path = Path(path)
    payload = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("workflow spec must be a mapping")
    return GovernedPilotWorkflowSpec.model_validate(payload)


def validate_governed_pilot_workflow_spec(path: str | Path) -> PilotWorkflowValidationResult:
    try:
        spec = load_governed_pilot_workflow_spec(path)
    except Exception as exc:  # noqa: BLE001
        return PilotWorkflowValidationResult(
            status="blocked",
            blockingReasons=[f"SPEC_INVALID:{type(exc).__name__}:{exc}"],
        )
    blocking: list[str] = []
    warnings: list[str] = []
    if spec.mode == "target_rehearsal":
        blocking.append("TARGET_REHEARSAL_REQUIRES_SEPARATE_SIGNED_EVIDENCE")
    if any(claim in spec.claims_under_test for claim in UNSUPPORTED_LIVE_CLAIMS):
        blocking.append("UNSUPPORTED_CLAIM_DECLARED_AS_UNDER_TEST")
    for scenario in spec.scenarios:
        if scenario.provider.runtime_mode != "dry_run":
            blocking.append(f"PROVIDER_RUNTIME_NOT_DRY_RUN:{scenario.scenario_id}")
        if scenario.evidence.raw_persistence:
            blocking.append(f"RAW_PERSISTENCE_REQUESTED:{scenario.scenario_id}")
    return PilotWorkflowValidationResult(
        status="blocked" if blocking else "pass",
        workflowId=spec.workflow_id,
        specHash=safe_hash_payload(spec.model_dump(mode="json", by_alias=True)),
        scenarioCount=len(spec.scenarios),
        blockingReasons=sorted(set(blocking)),
        warnings=warnings,
    )


def run_governed_pilot_workflow(
    spec: GovernedPilotWorkflowSpec,
    *,
    profile: str | None = None,
    mode: str | None = None,
    output_root: str | Path = "artifacts/governed-pilot-workflow",
    now: datetime | None = None,
) -> GovernedPilotWorkflowReport:
    effective_profile = profile or spec.profile
    effective_mode = mode or spec.mode
    validation = validate_governed_pilot_workflow_spec_payload(spec)
    if validation.status != "pass":
        raise ValueError(",".join(validation.blocking_reasons))
    if effective_mode not in {"deterministic", "dry_run"}:
        raise ValueError("governed pilot workflow only supports deterministic dry-run execution")

    generated_at = now or datetime.now(UTC)
    run_id = f"{spec.workflow_id}-{generated_at.strftime('%Y%m%d%H%M%S')}"
    root = Path(output_root)
    run_storage_id = safe_hash_payload({"runId": run_id}).split(":")[-1][:12]
    run_root = root / f"run-{run_storage_id}"
    writer = PilotWorkflowEvidenceWriter(run_root)
    spec_hash = safe_hash_payload(spec.model_dump(mode="json", by_alias=True))
    config = RuntimeConfig.from_profile(effective_profile)
    evidence_refs: list[str] = []

    claim_matrix = ClaimGuard(config=config).evaluate(evidence_root=root)
    claim_ref = writer.write_json(
        "claim_guard.json",
        claim_matrix.model_dump(mode="json"),
    )
    evidence_refs.append(claim_ref)
    claim_status_by_id = {claim.claim_id: str(claim.status) for claim in claim_matrix.claims}
    blocked_claims = [
        claim_id
        for claim_id in spec.blocked_claims
        if claim_status_by_id.get(claim_id) in BLOCKED_CLAIM_STATUSES
    ]
    unsupported_allowed = any(
        claim_status_by_id.get(claim_id) == "allowed" for claim_id in spec.blocked_claims
    )

    steps: list[PilotWorkflowStepResult] = []
    for scenario in spec.scenarios:
        step, refs = _run_scenario(
            scenario,
            profile=effective_profile,
            run_id=run_id,
            run_root=run_root,
            generated_at=generated_at,
        )
        steps.append(step)
        evidence_refs.extend(refs)

    blocking = []
    if unsupported_allowed:
        blocking.append("UNSUPPORTED_CLAIM_ALLOWED")
    if len(blocked_claims) != len(spec.blocked_claims):
        missing = sorted(set(spec.blocked_claims) - set(blocked_claims))
        blocking.extend(f"EXPECTED_BLOCKED_CLAIM_NOT_BLOCKED:{claim}" for claim in missing)
    blocking.extend(reason for step in steps for reason in step.blocking_reasons)
    step_payloads = [step.model_dump(mode="json", by_alias=True) for step in steps]
    raw_leak_detected = bool(find_raw_leaks(step_payloads))
    if raw_leak_detected:
        blocking.append("RAW_LEAK_DETECTED")

    status = "blocked" if blocking else "pass"
    claim_guard_status = "fail" if unsupported_allowed else "pass"
    manifest_path = writer.write_manifest(evidence_refs)
    report = GovernedPilotWorkflowReport(
        generatedAtUtc=generated_at,
        workflowId=spec.workflow_id,
        runId=run_id,
        profile=effective_profile,
        mode=effective_mode,
        status=status,
        specHash=spec_hash,
        rawLeakDetected=raw_leak_detected,
        claimGuardStatus=claim_guard_status,
        claimGuardEvidenceRef=claim_ref,
        blockedClaims=blocked_claims,
        unsupportedClaimAllowed=unsupported_allowed,
        steps=steps,
        evidenceManifestPath=manifest_path,
        blockingReasons=sorted(set(blocking)),
    )
    report_path = run_root / "report.json"
    report.report_path = str(report_path)
    summary_path = run_root / "REPORT.md"
    report.summary_path = str(summary_path)
    writer.write_text("REPORT.md", _render_report_markdown(report))
    writer.write_json("report.json", report.model_dump(mode="json", by_alias=True))
    report.report_hash = sha256_file(report_path)
    writer.write_json("report.json", report.model_dump(mode="json", by_alias=True))
    verification = verify_governed_pilot_workflow_report(report_path)
    writer.write_json("verification.json", verification.model_dump(mode="json", by_alias=True))
    mirror_latest(run_root, root / "latest")
    return report


def validate_governed_pilot_workflow_spec_payload(
    spec: GovernedPilotWorkflowSpec,
) -> PilotWorkflowValidationResult:
    tmp_hash = safe_hash_payload(spec.model_dump(mode="json", by_alias=True))
    blocking: list[str] = []
    if spec.mode == "target_rehearsal":
        blocking.append("TARGET_REHEARSAL_REQUIRES_SEPARATE_SIGNED_EVIDENCE")
    if any(claim in spec.claims_under_test for claim in UNSUPPORTED_LIVE_CLAIMS):
        blocking.append("UNSUPPORTED_CLAIM_DECLARED_AS_UNDER_TEST")
    for scenario in spec.scenarios:
        if scenario.provider.runtime_mode != "dry_run":
            blocking.append(f"PROVIDER_RUNTIME_NOT_DRY_RUN:{scenario.scenario_id}")
    return PilotWorkflowValidationResult(
        status="blocked" if blocking else "pass",
        workflowId=spec.workflow_id,
        specHash=tmp_hash,
        scenarioCount=len(spec.scenarios),
        blockingReasons=sorted(set(blocking)),
    )


def build_governed_pilot_workflow_snapshot(
    *,
    artifact_root: str | Path = "artifacts",
    generated_at: datetime | None = None,
) -> GovernedPilotWorkflowSnapshot:
    root = Path(artifact_root)
    report_path = root / "governed-pilot-workflow" / "latest" / "report.json"
    summary_path = root / "governed-pilot-workflow" / "latest" / "REPORT.md"
    if not report_path.exists():
        return GovernedPilotWorkflowSnapshot(
            generatedAtUtc=generated_at or datetime.now(UTC),
            enabled=False,
            status="missing",
            blockingReasons=["GOVERNED_PILOT_WORKFLOW_NOT_RUN"],
        )
    try:
        report = GovernedPilotWorkflowReport.model_validate_json(
            report_path.read_text(encoding="utf-8")
        )
        verification = verify_governed_pilot_workflow_report(report_path)
    except Exception as exc:  # noqa: BLE001
        return GovernedPilotWorkflowSnapshot(
            generatedAtUtc=generated_at or datetime.now(UTC),
            enabled=True,
            status="blocked",
            verifierStatus="fail",
            latestReportPath=str(report_path),
            latestSummaryPath=str(summary_path) if summary_path.exists() else None,
            blockingReasons=[f"GOVERNED_PILOT_WORKFLOW_INVALID:{type(exc).__name__}"],
        )
    status = "blocked" if report.status in {"blocked", "fail"} else report.status
    return GovernedPilotWorkflowSnapshot(
        generatedAtUtc=generated_at or report.generated_at_utc,
        enabled=True,
        status=status,
        workflowId=report.workflow_id,
        runId=report.run_id,
        mode=report.mode,
        rawPersistence=report.raw_persistence,
        claimGuardStatus=report.claim_guard_status,
        blockedClaims=report.blocked_claims,
        latestReportPath=str(report_path),
        latestSummaryPath=str(summary_path) if summary_path.exists() else None,
        verifierStatus=verification.status,
        blockingReasons=report.blocking_reasons + verification.blocking_reasons,
        warnings=report.warnings + verification.warnings,
    )


def _run_scenario(
    scenario: GovernedPilotScenario,
    *,
    profile: str,
    run_id: str,
    run_root: Path,
    generated_at: datetime,
) -> tuple[PilotWorkflowStepResult, list[str]]:
    refs: list[str] = []
    writer = PilotWorkflowEvidenceWriter(run_root / "scenarios" / scenario.scenario_id)
    fixture_id = safe_hash_payload({"scenarioId": scenario.scenario_id}).split(":")[-1][:12]
    fixture = build_memory_runtime_policy_fixture(
        run_root / "fixtures" / fixture_id,
        profile=profile,
        semantic_mode=scenario.memory.semantic_runtime_mode,
        semantic_enabled=scenario.memory.semantic_runtime_mode != "disabled",
    )
    request = RuntimeMemoryRequest(
        run_id=run_id,
        query=scenario.memory.query,
        actor_id=scenario.memory.actor_id,
        requester_role=scenario.memory.requester_role,
        agent_id=scenario.memory.agent_id,
        team_id=scenario.memory.team_id,
        workspace_id=scenario.memory.workspace_id,
        principal_id=scenario.memory.principal_id,
    )
    context_pack = fixture.bridge.retrieve_context(request)
    write_result = fixture.bridge.propose_post_run_write(
        run_id=run_id,
        actor_id=scenario.memory.actor_id,
        role=scenario.memory.requester_role,
        user_input=scenario.user_intent,
        assistant_output="Governed dry-run remediation proposal withheld pending approval.",
        scope="team",
        owner="team-alpha",
        memory_target="governed-pilot-workflow",
        agent_id=scenario.memory.agent_id,
    )
    memory_ref = writer.write_json(
        "memory.json",
        {
            "schemaVersion": "control-plane.governed-pilot-workflow-memory-evidence/v1",
            "runId": run_id,
            "contextStatus": context_pack.status,
            "hitCount": len(context_pack.hits),
            "rawContentIncluded": context_pack.raw_content_included,
            "writeStatus": write_result.status,
            "queryHash": sha256_text(scenario.memory.query),
            "userIntentHash": sha256_text(scenario.user_intent),
            "evidenceMode": "hash_only",
            "rawPersistence": False,
            "generatedAtUtc": generated_at.isoformat(),
        },
    )
    refs.append(memory_ref)
    memory_reasons: list[str] = []
    if context_pack.status not in set(scenario.memory.required_statuses):
        memory_reasons.append("MEMORY_CONTEXT_STATUS_UNEXPECTED")
    if context_pack.raw_content_included:
        memory_reasons.append("MEMORY_RAW_CONTENT_INCLUDED")
    if write_result.status != scenario.memory.write_expectation:
        memory_reasons.append("MEMORY_WRITE_STATUS_UNEXPECTED")
    memory_status = "pass" if not memory_reasons else "blocked"

    provider_result = ProviderInvocationCoordinator(
        output_dir=run_root / "provider-runtime" / "invocations"
    ).invoke(
        ProviderInvocationRequest(
            provider_kind=scenario.provider.provider_kind,
            model=scenario.provider.model,
            profile=profile,
            runtime_mode=scenario.provider.runtime_mode,
            prompt=scenario.user_intent,
            agent_id=scenario.memory.agent_id,
            workflow_id=run_id,
        )
    )
    provider_ref = provider_result.artifact_path
    if provider_ref:
        refs.append(provider_ref)
    provider_reasons = []
    if provider_result.status != scenario.provider.expected_status:
        provider_reasons.append("PROVIDER_STATUS_UNEXPECTED")
    if provider_result.raw_persistence:
        provider_reasons.append("PROVIDER_RAW_PERSISTENCE")
    provider_status = "pass" if not provider_reasons else "blocked"

    approval_reasons: list[str] = []
    executed_mutations = 0
    approval_status = "proposal_only" if write_result.status == "proposal_only" else "blocked"
    if approval_status != scenario.approval.expected_status:
        approval_reasons.append("APPROVAL_STATUS_UNEXPECTED")
    approval_component_status = "pass" if not approval_reasons else "blocked"
    approval_ref = writer.write_json(
        "approval.json",
        {
            "schemaVersion": "control-plane.governed-pilot-workflow-approval-evidence/v1",
            "runId": run_id,
            "status": approval_status,
            "executedMutations": executed_mutations,
            "proposalHash": safe_hash_payload(
                {
                    "scenarioId": scenario.scenario_id,
                    "writeStatus": write_result.status,
                    "providerInvocationId": provider_result.invocation_id,
                }
            ),
            "evidenceMode": "hash_only",
            "rawPersistence": False,
        },
    )
    refs.append(approval_ref)

    evidence_reasons = []
    if scenario.evidence.evidence_mode != "hash_only" or scenario.evidence.raw_persistence:
        evidence_reasons.append("EVIDENCE_EXPECTATION_NOT_HASH_ONLY")
    evidence_status = "pass" if not evidence_reasons else "blocked"
    evidence_ref = writer.write_json(
        "evidence.json",
        {
            "schemaVersion": "control-plane.governed-pilot-workflow-evidence-proof/v1",
            "runId": run_id,
            "artifactHashes": [sha256_file(Path(ref)) for ref in refs if Path(ref).exists()],
            "evidenceMode": "hash_only",
            "rawPersistence": False,
        },
    )
    refs.append(evidence_ref)

    blocking = memory_reasons + provider_reasons + approval_reasons + evidence_reasons
    status = "pass" if not blocking else "blocked"
    step = PilotWorkflowStepResult(
        scenarioId=scenario.scenario_id,
        status=status,
        userIntentHash=sha256_text(scenario.user_intent),
        memory=PilotWorkflowComponentResult(
            componentId="memory-runtime-policy",
            status=memory_status,
            reasonCodes=memory_reasons or ["MEMORY_POLICY_HASH_ONLY_PASS"],
            evidenceRefs=[memory_ref],
            metrics={"hitCount": len(context_pack.hits), "writeStatus": write_result.status},
        ),
        provider=PilotWorkflowComponentResult(
            componentId="provider-runtime-dry-run",
            status=provider_status,
            reasonCodes=provider_reasons or ["PROVIDER_DRY_RUN_HASH_ONLY_PASS"],
            evidenceRefs=[provider_ref] if provider_ref else [],
            metrics={"runtimeMode": provider_result.runtime_mode},
        ),
        approval=PilotWorkflowComponentResult(
            componentId="approval-gate",
            status=approval_component_status,
            reasonCodes=approval_reasons or ["APPROVAL_PROPOSAL_ONLY_PASS"],
            evidenceRefs=[approval_ref],
            metrics={"executedMutations": executed_mutations},
        ),
        evidence=PilotWorkflowComponentResult(
            componentId="hash-only-evidence",
            status=evidence_status,
            reasonCodes=evidence_reasons or ["HASH_ONLY_EVIDENCE_PASS"],
            evidenceRefs=[evidence_ref],
            metrics={"artifactCount": len(refs)},
        ),
        blockingReasons=blocking,
    )
    return step, refs


def _render_report_markdown(report: GovernedPilotWorkflowReport) -> str:
    lines = [
        "# Governed Pilot Workflow Proof",
        "",
        f"- Workflow: `{report.workflow_id}`",
        f"- Run: `{report.run_id}`",
        f"- Status: `{report.status}`",
        f"- Evidence mode: `{report.evidence_mode}`",
        f"- Raw persistence: `{report.raw_persistence}`",
        f"- Claim guard: `{report.claim_guard_status}`",
        "",
        "## Scenarios",
    ]
    for step in report.steps:
        lines.extend(
            [
                "",
                f"### {step.scenario_id}",
                f"- Status: `{step.status}`",
                f"- User intent hash: `{step.user_intent_hash}`",
                f"- Memory: `{step.memory.status}`",
                f"- Provider: `{step.provider.status}`",
                f"- Approval: `{step.approval.status}`",
                f"- Evidence: `{step.evidence.status}`",
            ]
        )
    if report.blocking_reasons:
        lines.extend(["", "## Blocking Reasons"])
        lines.extend(f"- `{reason}`" for reason in report.blocking_reasons)
    lines.append("")
    return "\n".join(lines)
