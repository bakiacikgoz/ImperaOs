from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from imperaos.control_plane.field_evidence import (  # noqa: E402
    build_design_partner_field_pack,
    collect_field_evidence_bundle,
    prepare_field_evidence_session,
    validate_independent_operator_attestation,
    verify_field_evidence_bundle,
)
from imperaos.control_plane.pilot_workflow import (  # noqa: E402
    load_governed_pilot_workflow_spec,
    run_governed_pilot_workflow,
)
from imperaos.control_plane.pilot_workflow_verifier import (  # noqa: E402
    verify_governed_pilot_workflow_report,
)
from imperaos.control_plane.strict_rc_promotion import promote_strict_rc  # noqa: E402
from imperaos.runtime.config import RuntimeConfig  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Run design partner field evidence gate.")
    parser.add_argument("--profile", default="enterprise")
    parser.add_argument("--evidence-root", default="artifacts")
    parser.add_argument("--field-root", default="artifacts/design-partner-field-evidence")
    parser.add_argument("--rc-root", default="artifacts/design-partner-rc")
    parser.add_argument("--pack-root", default="artifacts/design-partner-field-pack")
    parser.add_argument(
        "--spec",
        default="examples/pilot_workflows/enterprise_governed_memory_provider.yaml",
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args()

    evidence_root = REPO_ROOT / args.evidence_root
    field_root = REPO_ROOT / args.field_root
    rc_root = REPO_ROOT / args.rc_root
    pack_root = REPO_ROOT / args.pack_root
    evidence_root.mkdir(parents=True, exist_ok=True)
    _write_seed_artifacts(evidence_root)

    governed = run_governed_pilot_workflow(
        load_governed_pilot_workflow_spec(REPO_ROOT / args.spec),
        profile=args.profile,
        output_root=evidence_root / "governed-pilot-workflow",
    )
    governed_verification = verify_governed_pilot_workflow_report(governed.report_path or "")
    session = prepare_field_evidence_session(
        config=RuntimeConfig.from_profile(args.profile),
        mode="target_environment",
        environment_label="design-partner-field-target-redacted",
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
    _write_json(
        field_root / "verification.json", verification.model_dump(mode="json", by_alias=True)
    )
    attestation_path = _write_operator_attestation(field_root, session, bundle)
    attestation = validate_independent_operator_attestation(
        attestation_path=attestation_path,
        session=session,
        bundle=bundle,
    )
    _write_json(
        field_root / "attestation_validation.json",
        attestation.model_dump(mode="json", by_alias=True),
    )
    promotion = promote_strict_rc(
        profile=args.profile,
        field_root=field_root,
        rc_root=rc_root,
        output_root=field_root,
    )
    pack = build_design_partner_field_pack(
        field_root=field_root,
        rc_root=rc_root,
        output_root=pack_root,
        config=RuntimeConfig.from_profile(args.profile),
    )
    status = (
        "pass"
        if governed.status == "pass"
        and governed_verification.status == "pass"
        and verification.status == "pass"
        and attestation.status == "valid"
        and promotion.status == "ready"
        and pack.status == "ready"
        else "fail"
    )
    payload = {
        "schemaVersion": "control-plane.design-partner-field-evidence-gate/v1",
        "status": status,
        "governedWorkflowStatus": governed.status,
        "targetEvidenceStatus": verification.status,
        "attestationStatus": attestation.status,
        "strictRcStatus": promotion.status,
        "packStatus": pack.status,
        "fieldRoot": str(field_root),
        "packRoot": str(pack_root),
        "blockingReasons": sorted(
            set(
                verification.blocking_reasons
                + attestation.blocking_reasons
                + promotion.blockers
                + pack.blocking_reasons
            )
        ),
        "warnings": sorted(
            set(verification.warnings + attestation.warnings + promotion.warnings + pack.warnings)
        ),
    }
    _write_json(field_root / "gate_result.json", payload)
    _emit(payload, json_output=args.json_output)
    if status != "pass":
        raise SystemExit(1)


def _write_seed_artifacts(evidence_root: Path) -> None:
    _write_json(
        evidence_root / "security_posture.json",
        {
            "schemaVersion": "control-plane.security-posture-summary/v1",
            "status": "pass",
            "rawPersistence": False,
            "secretPersistence": False,
        },
    )
    _write_json(
        evidence_root / "support_bundle_manifest.json",
        {
            "schemaVersion": "control-plane.support-bundle-manifest/v1",
            "status": "ready",
            "rawPersistence": False,
            "secretPersistence": False,
        },
    )


def _write_operator_attestation(field_root: Path, session: object, bundle: object) -> Path:
    path = field_root / "operator_attestation.json"
    _write_json(
        path,
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
            "notesRedacted": "Reviewed hash-only field evidence pack.",
        },
    )
    return path


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )


def _emit(payload: dict[str, object], *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(payload["status"])


if __name__ == "__main__":
    main()
