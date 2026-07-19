from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from imperaos.release.gate_ledger import write_gate_evidence_ledger
from imperaos.release.gate_models import (
    GateEvidenceLedger,
    GateRunResult,
    ReleaseGateTarget,
)
from imperaos.release.rc_freeze_backfill import build_rc_evidence_backfill_report


def test_backfill_marks_ready_when_missing_freeze_gates_are_in_ledger(tmp_path: Path) -> None:
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
                startedAtUtc=datetime.now(UTC),
                finishedAtUtc=datetime.now(UTC),
                durationMs=1,
            ),
            GateRunResult(
                gateId="design-partner-handoff-gate",
                status="pass",
                startedAtUtc=datetime.now(UTC),
                finishedAtUtc=datetime.now(UTC),
                durationMs=1,
            ),
        ],
        requiredGateIds=["control-plane-gate", "design-partner-handoff-gate"],
        status="ready",
        artifactRoot="artifacts/release-gates/mainline-rc",
    )
    ledger_path = write_gate_evidence_ledger(ledger=ledger, repo_root=tmp_path)

    report = build_rc_evidence_backfill_report(
        gate_ledger_path=ledger_path,
        repo_root=tmp_path,
        missing_gate_ids=["control-plane-gate", "design-partner-handoff-gate"],
    )

    assert report.status == "ready"
    assert report.ready_for_rc_freeze is True
    assert report.resolved_gate_ids == ["control-plane-gate", "design-partner-handoff-gate"]
