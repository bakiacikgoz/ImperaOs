from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from imperaos.cli import app
from imperaos.control_plane.pilot_workflow import (
    load_governed_pilot_workflow_spec,
    run_governed_pilot_workflow,
)

runner = CliRunner()
SPEC = Path("examples/pilot_workflows/enterprise_governed_memory_provider.yaml")


def test_pilot_field_prepare_requires_target_environment_ack(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "pilot",
            "field",
            "prepare",
            "--mode",
            "target-environment",
            "--target-environment-label",
            "Partner QA Workstation",
            "--output-root",
            str(tmp_path / "field"),
        ],
    )

    assert result.exit_code == 2
    assert json.loads(result.stdout)["blockingReasons"] == ["TARGET_ENVIRONMENT_ACK_REQUIRED"]


def test_pilot_field_cli_target_ready_path(tmp_path: Path) -> None:
    evidence_root = _seed_evidence(tmp_path)
    field_root = evidence_root / "design-partner-field-evidence"
    prepare = runner.invoke(
        app,
        [
            "pilot",
            "field",
            "prepare",
            "--profile",
            "enterprise",
            "--mode",
            "target-environment",
            "--ack-target-environment",
            "--target-environment-label",
            "Partner QA Workstation",
            "--output-root",
            str(field_root),
            "--force-new-session",
        ],
    )
    assert prepare.exit_code == 0

    collect = runner.invoke(
        app,
        [
            "pilot",
            "field",
            "collect",
            "--session",
            str(field_root / "session.json"),
            "--evidence-root",
            str(evidence_root),
            "--output-root",
            str(field_root),
        ],
    )
    assert collect.exit_code == 0
    bundle = json.loads(collect.stdout)

    verify = runner.invoke(
        app,
        [
            "pilot",
            "field",
            "verify",
            "--bundle",
            str(field_root / "target_evidence_bundle.json"),
            "--output",
            str(field_root / "verification.json"),
        ],
    )
    assert verify.exit_code == 0

    session = json.loads((field_root / "session.json").read_text(encoding="utf-8"))
    attestation_path = field_root / "operator_attestation.json"
    attestation_path.write_text(
        json.dumps(
            {
                "schemaVersion": "imperaos-non-developer-operator-attestation/v2",
                "sessionId": session["sessionId"],
                "releasePackId": "design-partner-rc-v1",
                "targetEnvironmentLabelHash": session["targetEnvironment"]["environmentLabelHash"],
                "bundleSha256": bundle["bundleSha256"],
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
    attest = runner.invoke(
        app,
        [
            "pilot",
            "field",
            "attest-verify",
            "--session",
            str(field_root / "session.json"),
            "--bundle",
            str(field_root / "target_evidence_bundle.json"),
            "--operator-attestation",
            str(attestation_path),
            "--output",
            str(field_root / "attestation_validation.json"),
        ],
    )
    assert attest.exit_code == 0

    promote = runner.invoke(
        app,
        [
            "pilot",
            "field",
            "promote-rc",
            "--profile",
            "enterprise",
            "--field-root",
            str(field_root),
            "--rc-root",
            str(evidence_root / "design-partner-rc"),
        ],
    )
    assert promote.exit_code == 0
    assert json.loads(promote.stdout)["status"] == "ready"


def _seed_evidence(tmp_path: Path) -> Path:
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
    return evidence_root
