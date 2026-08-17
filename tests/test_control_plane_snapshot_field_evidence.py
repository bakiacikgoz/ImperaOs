from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from imperaos.control_plane.field_evidence import (
    collect_field_evidence_bundle,
    prepare_field_evidence_session,
    validate_independent_operator_attestation,
    verify_field_evidence_bundle,
)
from imperaos.control_plane.pilot_workflow import (
    load_governed_pilot_workflow_spec,
    run_governed_pilot_workflow,
)
from imperaos.control_plane.snapshot import build_control_plane_snapshot
from imperaos.control_plane.strict_rc_promotion import promote_strict_rc
from imperaos.runtime.config import RuntimeConfig

SPEC = Path("examples/pilot_workflows/enterprise_governed_memory_provider.yaml")


def test_control_plane_snapshot_exposes_missing_field_evidence(tmp_path: Path) -> None:
    snapshot = build_control_plane_snapshot(
        root_dir=tmp_path / "state",
        evidence_root=tmp_path / "artifacts",
        profile="enterprise",
    )

    assert snapshot.design_partner_field_evidence.status == "missing"
    assert snapshot.design_partner_field_evidence.attestation_status == "missing"


def test_control_plane_snapshot_exposes_ready_field_evidence(tmp_path: Path) -> None:
    evidence_root = _seed_ready_field_evidence(tmp_path)

    snapshot = build_control_plane_snapshot(
        root_dir=tmp_path / "state",
        evidence_root=evidence_root,
        profile="enterprise",
    )

    assert snapshot.design_partner_field_evidence.status == "ready"
    assert snapshot.design_partner_field_evidence.strict_rc_status == "ready"
    assert snapshot.design_partner_field_evidence.attestation_status == "valid"


def _seed_ready_field_evidence(tmp_path: Path) -> Path:
    evidence_root = tmp_path / "artifacts"
    evidence_root.mkdir()
    (evidence_root / "security_posture.json").write_text(
        json.dumps({"status": "pass", "rawPersistence": False}) + "\n",
        encoding="utf-8",
    )
    (evidence_root / "support_bundle_manifest.json").write_text(
        json.dumps({"status": "ready", "rawPersistence": False}) + "\n",
        encoding="utf-8",
    )
    run_governed_pilot_workflow(
        load_governed_pilot_workflow_spec(SPEC),
        profile="enterprise",
        output_root=evidence_root / "governed-pilot-workflow",
    )
    field_root = evidence_root / "design-partner-field-evidence"
    session = prepare_field_evidence_session(
        config=RuntimeConfig.from_profile("enterprise"),
        mode="target_environment",
        environment_label="Partner QA Workstation",
        output_root=field_root,
        force_new_session=True,
    )
    bundle = collect_field_evidence_bundle(
        session=session,
        evidence_root=evidence_root,
        output_root=field_root,
    )
    verification = verify_field_evidence_bundle(
        bundle_path=field_root / "target_evidence_bundle.json"
    )
    (field_root / "verification.json").write_text(
        json.dumps(verification.model_dump(mode="json", by_alias=True), indent=2) + "\n",
        encoding="utf-8",
    )
    attestation_path = field_root / "operator_attestation.json"
    attestation_path.write_text(
        json.dumps(
            {
                "schemaVersion": "imperaos-non-developer-operator-attestation/v2",
                "sessionId": session.session_id,
                "releasePackId": "design-partner-rc-v1",
                "targetEnvironmentLabelHash": session.target_environment.environment_label_hash,
                "bundleSha256": bundle.bundle_sha256,
                "operatorDisplayName": "Field Operator One",
                "operatorRole": "Design Partner Operations Reviewer",
                "nonDeveloperOperator": True,
                "reviewedRunbook": True,
                "completedValidation": True,
                "signedAtUtc": datetime.now(UTC).isoformat(),
                "notesRedacted": "Reviewed hash-only field pack.",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    attestation = validate_independent_operator_attestation(
        attestation_path=attestation_path,
        session=session,
        bundle=bundle,
    )
    (field_root / "attestation_validation.json").write_text(
        json.dumps(attestation.model_dump(mode="json", by_alias=True), indent=2) + "\n",
        encoding="utf-8",
    )
    promote_strict_rc(
        profile="enterprise",
        field_root=field_root,
        rc_root=evidence_root / "design-partner-rc",
        output_root=field_root,
    )
    return evidence_root
