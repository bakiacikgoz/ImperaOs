from __future__ import annotations

import json
from pathlib import Path

from imperaos.control_plane.mainline_rc_freeze import (
    GateEvidenceItem,
    GateEvidenceSummary,
    build_mainline_rc_freeze_snapshot,
    build_rc_freeze_manifest,
    verify_rc_freeze_manifest,
    verify_rc_freeze_manifest_with_gate_ledger,
    write_rc_freeze_manifest,
)
from imperaos.control_plane.mainline_stack import (
    MergeRehearsalReport,
    StackGraphVerificationReport,
)
from imperaos.control_plane.release_artifact_scan import ArtifactScanReport
from imperaos.control_plane.release_train import ClaimBoundarySummary
from imperaos.release.gate_ledger import write_gate_evidence_ledger
from imperaos.release.gate_models import GateEvidenceLedger, GateRunResult, ReleaseGateTarget


def test_rc_freeze_manifest_ready_requires_clean_evidence(tmp_path: Path) -> None:
    manifest = build_rc_freeze_manifest(
        profile="enterprise",
        output_root=tmp_path / "artifacts" / "mainline-rc-freeze",
        stack_report=StackGraphVerificationReport(
            status="ready",
            stackName="design-partner-rc",
            baseBranch="main",
            headBranch="codex/design-partner-rc-handoff-ops-readiness-v1",
            stackOrder=["codex/a"],
        ),
        rehearsal_report=MergeRehearsalReport(
            status="pass",
            baseRef="main",
            headRef="codex/design-partner-rc-handoff-ops-readiness-v1",
            mode="dry-run",
            worktreeMutated=False,
        ),
        gate_evidence=GateEvidenceSummary(
            status="pass",
            items=[GateEvidenceItem(gateId="unit", command="pytest", status="pass")],
        ),
        claim_boundaries=ClaimBoundarySummary(
            publicDesktop="blocked",
            liveComputerUse="blocked",
            approvalFreeIrreversibleMutation="blocked",
            unsupportedClaimAllowed=False,
        ),
        artifact_scan=ArtifactScanReport(status="pass"),
        freeze_id="freeze-test",
    )

    path = write_rc_freeze_manifest(manifest, tmp_path / "artifacts" / "mainline-rc-freeze")
    verification = verify_rc_freeze_manifest(manifest_path=path)

    assert manifest.status == "ready"
    assert manifest.raw_persistence is False
    assert verification.status == "ready"
    assert verification.manifest_sha256.startswith("sha256:")


def test_rc_freeze_verifier_blocks_false_ready(tmp_path: Path) -> None:
    root = tmp_path / "artifacts" / "mainline-rc-freeze"
    root.mkdir(parents=True)
    payload = {
        "schemaVersion": "control-plane.rc-freeze-manifest/v1",
        "freezeId": "freeze-false-ready",
        "profile": "enterprise",
        "status": "ready",
        "evidenceMode": "hash_only",
        "rawPersistence": False,
        "stack": {"status": "blocked", "blockers": ["STACK_BASE_MISMATCH:a"]},
        "mergeRehearsal": {"status": "pass", "worktreeMutated": False},
        "gateEvidence": {"status": "pass", "items": []},
        "claimBoundaries": {
            "publicDesktop": "blocked",
            "liveComputerUse": "blocked",
            "approvalFreeIrreversibleMutation": "blocked",
            "unsupportedClaimAllowed": False,
        },
        "artifactScan": {"status": "pass"},
        "blockers": ["STACK_BASE_MISMATCH:a"],
        "warnings": [],
        "generatedAtUtc": "2026-06-15T00:00:00Z",
    }
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    verification = verify_rc_freeze_manifest(manifest_path=manifest_path)

    assert verification.status == "blocked"
    assert "FALSE_READY_RC_FREEZE" in verification.blockers


def test_mainline_rc_freeze_snapshot_missing_is_fail_closed(tmp_path: Path) -> None:
    snapshot = build_mainline_rc_freeze_snapshot(artifact_root=tmp_path / "artifacts")

    assert snapshot.status == "missing"
    assert "MAINLINE_RC_FREEZE_MISSING" in snapshot.warnings


def test_rc_freeze_verifier_uses_gate_ledger_to_resolve_missing_gate_warnings(
    tmp_path: Path,
) -> None:
    manifest = build_rc_freeze_manifest(
        profile="enterprise",
        output_root=tmp_path / "artifacts" / "mainline-rc-freeze",
        stack_report=StackGraphVerificationReport(
            status="ready",
            stackName="design-partner-rc",
            baseBranch="main",
            headBranch="codex/design-partner-rc-handoff-ops-readiness-v1",
            stackOrder=["codex/a"],
        ),
        rehearsal_report=MergeRehearsalReport(
            status="pass",
            baseRef="main",
            headRef="codex/design-partner-rc-handoff-ops-readiness-v1",
            mode="dry-run",
            worktreeMutated=False,
        ),
        gate_evidence=GateEvidenceSummary(
            status="conditional",
            warnings=[
                "REQUIRED_GATE_MISSING:control-plane-gate",
                "REQUIRED_GATE_MISSING:design-partner-handoff-gate",
            ],
            items=[],
        ),
        claim_boundaries=ClaimBoundarySummary(
            publicDesktop="blocked",
            liveComputerUse="blocked",
            approvalFreeIrreversibleMutation="blocked",
            unsupportedClaimAllowed=False,
        ),
        artifact_scan=ArtifactScanReport(status="pass"),
        freeze_id="freeze-with-ledger",
    )
    manifest_path = write_rc_freeze_manifest(
        manifest,
        tmp_path / "artifacts" / "mainline-rc-freeze",
    )
    target = ReleaseGateTarget(
        targetId="mainline-rc",
        profile="enterprise",
        mode="rc-focused",
        platform="windows",
        outputRoot="artifacts/release-gates/mainline-rc",
    )
    ledger = GateEvidenceLedger(
        repoHeadSha="1" * 40,
        branch="codex/test",
        target=target,
        gateResults=[
            GateRunResult(
                gateId="control-plane-gate",
                status="pass",
                startedAtUtc=manifest.generated_at_utc,
                finishedAtUtc=manifest.generated_at_utc,
                durationMs=1,
            ),
            GateRunResult(
                gateId="design-partner-handoff-gate",
                status="pass",
                startedAtUtc=manifest.generated_at_utc,
                finishedAtUtc=manifest.generated_at_utc,
                durationMs=1,
            ),
        ],
        requiredGateIds=["control-plane-gate", "design-partner-handoff-gate"],
        status="ready",
        artifactRoot="artifacts/release-gates/mainline-rc",
    )
    ledger_path = write_gate_evidence_ledger(ledger=ledger, repo_root=tmp_path)

    report = verify_rc_freeze_manifest_with_gate_ledger(
        manifest_path=manifest_path,
        gate_ledger_path=ledger_path,
        repo_root=tmp_path,
    )

    assert report.status == "ready"
    assert report.warnings == []
