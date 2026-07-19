from __future__ import annotations

import json
from pathlib import Path

from imperaos.control_plane.design_partner_handoff import (
    DesignPartnerHandoffManifest,
    HandoffComponentSummary,
    build_design_partner_handoff_pack,
    build_design_partner_handoff_snapshot,
    verify_design_partner_handoff_pack,
)
from imperaos.control_plane.pilot_ops_drill import PilotOpsDrillMetrics, PilotOpsDrillReport
from imperaos.control_plane.release_train import (
    ClaimBoundarySummary,
    ReleaseTrainVerificationReport,
)
from imperaos.control_plane.strict_rc_promotion import StrictRCPromotionReport


def test_handoff_pack_ready_with_strict_rc_and_pass_drill(tmp_path: Path) -> None:
    artifact_root = _seed_ready_artifacts(tmp_path)
    output_root = artifact_root / "design-partner-handoff"
    release_report = ReleaseTrainVerificationReport(status="pass")
    drill_report = PilotOpsDrillReport(
        status="pass",
        profile="enterprise",
        metrics=PilotOpsDrillMetrics(stepCount=1, passedCount=1),
        artifactRoot=str(output_root),
    )

    manifest = build_design_partner_handoff_pack(
        profile="enterprise",
        output_root=output_root,
        artifact_root=artifact_root,
        environment_label="design-partner-rc-local",
        release_train_report=release_report,
        drill_report=drill_report,
    )
    verification = verify_design_partner_handoff_pack(
        manifest_path=output_root / "manifest.json"
    )

    assert manifest.status == "ready"
    assert verification.status == "ready"
    assert (output_root / "CLAIM_BOUNDARY_CARD.md").exists()


def test_handoff_pack_blocks_secret_marker(tmp_path: Path) -> None:
    artifact_root = _seed_ready_artifacts(tmp_path)
    output_root = artifact_root / "design-partner-handoff"
    manifest = build_design_partner_handoff_pack(
        profile="enterprise",
        output_root=output_root,
        artifact_root=artifact_root,
        environment_label="design-partner-rc-local",
        release_train_report=ReleaseTrainVerificationReport(status="pass"),
        drill_report=PilotOpsDrillReport(
            status="pass",
            profile="enterprise",
            metrics=PilotOpsDrillMetrics(stepCount=1, passedCount=1),
            artifactRoot=str(output_root),
        ),
    )
    support = artifact_root / "support_bundle_manifest.json"
    support.write_text('{"token":"sk-test"}\n', encoding="utf-8")

    verification = verify_design_partner_handoff_pack(
        manifest_path=output_root / "manifest.json"
    )

    assert manifest.status == "ready"
    assert verification.status == "blocked"
    assert "HANDOFF_SECRET_OR_RAW_MARKER_DETECTED" in verification.blockers


def test_handoff_verifier_blocks_false_ready_claim(tmp_path: Path) -> None:
    output_root = tmp_path / "artifacts" / "design-partner-handoff"
    output_root.mkdir(parents=True)
    manifest = DesignPartnerHandoffManifest(
        status="ready",
        profile="enterprise",
        environmentLabel="design-partner-rc-local",
        releaseTrain=HandoffComponentSummary(status="pass"),
        strictRc=HandoffComponentSummary(status="conditional"),
        fieldEvidence=HandoffComponentSummary(status="conditional"),
        operatorAttestation=HandoffComponentSummary(status="missing"),
        firstRunDrill=HandoffComponentSummary(status="pass"),
        supportBundle=None,
        claimBoundaries=_claim_boundaries(),
        artifacts=[],
    )
    (output_root / "manifest.json").write_text(
        json.dumps(manifest.model_dump(mode="json", by_alias=True), indent=2) + "\n",
        encoding="utf-8",
    )

    verification = verify_design_partner_handoff_pack(
        manifest_path=output_root / "manifest.json"
    )

    assert verification.status == "blocked"
    assert "FALSE_READY_HANDOFF_CLAIM" in verification.blockers


def test_handoff_snapshot_missing_is_safe(tmp_path: Path) -> None:
    snapshot = build_design_partner_handoff_snapshot(artifact_root=tmp_path / "artifacts")

    assert snapshot.status == "missing"
    assert "DESIGN_PARTNER_HANDOFF_MISSING" in snapshot.warnings


def _seed_ready_artifacts(tmp_path: Path) -> Path:
    artifact_root = tmp_path / "artifacts"
    field_root = artifact_root / "design-partner-field-evidence"
    field_root.mkdir(parents=True)
    (artifact_root / "support_bundle_manifest.json").write_text(
        '{"status":"ready"}\n',
        encoding="utf-8",
    )
    (artifact_root / "security_posture.json").write_text(
        '{"status":"pass"}\n',
        encoding="utf-8",
    )
    (field_root / "target_evidence_bundle.json").write_text(
        '{"status":"pass"}\n',
        encoding="utf-8",
    )
    strict = StrictRCPromotionReport(
        status="ready",
        ready=True,
        sessionId="field-session",
        mode="target_environment",
        targetEvidenceStatus="pass",
        attestationStatus="valid",
        claimGuardStatus="pass",
        governedWorkflowStatus="pass",
        supportBundleStatus="present",
        securityBaselineStatus="present",
    )
    (field_root / "strict_rc_promotion.json").write_text(
        json.dumps(strict.model_dump(mode="json", by_alias=True), indent=2) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "schemaVersion": "control-plane.release-train-manifest/v1",
        "profile": "enterprise",
        "mode": "local",
        "claimBoundaries": _claim_boundaries().model_dump(mode="json", by_alias=True),
        "generatedAtUtc": "2026-06-14T00:00:00Z",
        "worktreeDirty": False,
    }
    output_root = artifact_root / "design-partner-handoff"
    output_root.mkdir()
    (output_root / "release_train_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    return artifact_root


def _claim_boundaries() -> ClaimBoundarySummary:
    return ClaimBoundarySummary(
        publicDesktop="blocked",
        liveComputerUse="blocked",
        approvalFreeIrreversibleMutation="blocked",
        unsupportedClaimAllowed=False,
    )
