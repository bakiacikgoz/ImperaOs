from __future__ import annotations

import json
from pathlib import Path

from imperaos.control_plane.pilot_workflow import (
    load_governed_pilot_workflow_spec,
    run_governed_pilot_workflow,
    validate_governed_pilot_workflow_spec,
)
from imperaos.control_plane.pilot_workflow_verifier import (
    verify_governed_pilot_workflow_report,
)

SPEC = Path("examples/pilot_workflows/enterprise_governed_memory_provider.yaml")


def test_governed_pilot_workflow_runs_hash_only_proof(tmp_path: Path) -> None:
    validation = validate_governed_pilot_workflow_spec(SPEC)

    assert validation.status == "pass"
    report = run_governed_pilot_workflow(
        load_governed_pilot_workflow_spec(SPEC),
        output_root=tmp_path / "governed-pilot-workflow",
    )

    assert report.status == "pass"
    assert report.raw_persistence is False
    assert report.raw_leak_detected is False
    assert report.unsupported_claim_allowed is False
    assert report.steps[0].memory.status == "pass"
    assert report.steps[0].provider.status == "pass"
    assert report.steps[0].approval.metrics["executedMutations"] == 0
    report_text = Path(report.report_path or "").read_text(encoding="utf-8")
    assert "Draft a remediation plan" not in report_text
    assert "hash only policy evidence" not in report_text

    verification = verify_governed_pilot_workflow_report(report.report_path or "")
    assert verification.status == "pass"
    assert verification.raw_leak_detected is False


def test_governed_pilot_workflow_verifier_blocks_raw_leak_fixture(tmp_path: Path) -> None:
    report = run_governed_pilot_workflow(
        load_governed_pilot_workflow_spec(SPEC),
        output_root=tmp_path / "governed-pilot-workflow",
    )
    path = Path(report.report_path or "")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["steps"][0]["evidence"]["metrics"]["leak"] = "BEGIN RAW prompt data"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    verification = verify_governed_pilot_workflow_report(path)

    assert verification.status == "fail"
    assert verification.raw_leak_detected is True
    assert "RAW_LEAK_DETECTED" in verification.blocking_reasons


def test_governed_pilot_workflow_validation_blocks_live_claim_under_test(
    tmp_path: Path,
) -> None:
    spec_path = tmp_path / "overreach.yaml"
    spec_path.write_text(
        SPEC.read_text(encoding="utf-8").replace(
            "claimsUnderTest:\n  - enterprise-self-hosted-agent-control-plane",
            "claimsUnderTest:\n  - live-macos-computer-use",
        ),
        encoding="utf-8",
    )

    validation = validate_governed_pilot_workflow_spec(spec_path)

    assert validation.status == "blocked"
    assert "UNSUPPORTED_CLAIM_DECLARED_AS_UNDER_TEST" in validation.blocking_reasons
