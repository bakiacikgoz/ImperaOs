from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from imperaos.release.gate_ledger import write_gate_evidence_ledger
from imperaos.release.gate_models import (
    GateArtifactRef,
    GateEvidenceLedger,
    GateRunResult,
    ReleaseGateTarget,
)
from imperaos.release.gate_verifier import verify_gate_evidence_ledger


def _target() -> ReleaseGateTarget:
    return ReleaseGateTarget(
        targetId="mainline-rc",
        profile="enterprise",
        mode="rc-focused",
        platform="windows",
        outputRoot="artifacts/release-gates/mainline-rc",
    )


def _pass_result(gate_id: str, path: str, sha: str = "0" * 64) -> GateRunResult:
    return GateRunResult(
        gateId=gate_id,
        status="pass",
        startedAtUtc=datetime.now(UTC),
        finishedAtUtc=datetime.now(UTC),
        durationMs=1,
        artifactRefs=[
            GateArtifactRef(path=path, sha256=sha, sizeBytes=2, kind="json", scanStatus="pass")
        ],
    )


def test_verifier_marks_complete_ledger_ready(tmp_path: Path) -> None:
    path = tmp_path / "artifacts" / "release-gates" / "mainline-rc" / "gate.json"
    path.parent.mkdir(parents=True)
    path.write_text("{}\n", encoding="utf-8")
    from imperaos.control_plane.storage import file_sha256

    ledger = GateEvidenceLedger(
        repoHeadSha="1" * 40,
        branch="codex/test",
        target=_target(),
        gateResults=[
            _pass_result("control-plane-gate", str(path.relative_to(tmp_path)), file_sha256(path)),
            _pass_result(
                "design-partner-handoff-gate",
                str(path.relative_to(tmp_path)),
                file_sha256(path),
            ),
        ],
        requiredGateIds=["control-plane-gate", "design-partner-handoff-gate"],
        status="ready",
        artifactRoot="artifacts/release-gates/mainline-rc",
    )
    ledger_path = write_gate_evidence_ledger(ledger=ledger, repo_root=tmp_path)

    report = verify_gate_evidence_ledger(ledger_path=ledger_path, repo_root=tmp_path)

    assert report.status == "ready"
    assert report.ready_for_rc_freeze is True
    assert report.missing_gate_ids == []


def test_verifier_is_conditional_for_missing_required_gate(tmp_path: Path) -> None:
    ledger = GateEvidenceLedger(
        repoHeadSha="1" * 40,
        branch="codex/test",
        target=_target(),
        gateResults=[],
        requiredGateIds=["control-plane-gate"],
        status="conditional",
        artifactRoot="artifacts/release-gates/mainline-rc",
    )
    ledger_path = write_gate_evidence_ledger(ledger=ledger, repo_root=tmp_path)

    report = verify_gate_evidence_ledger(ledger_path=ledger_path, repo_root=tmp_path)

    assert report.status == "conditional"
    assert report.ready_for_rc_freeze is False
    assert report.missing_gate_ids == ["control-plane-gate"]


def test_verifier_blocks_tampered_artifact_hash(tmp_path: Path) -> None:
    artifact = tmp_path / "artifacts" / "release-gates" / "mainline-rc" / "tampered.json"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("{}\n", encoding="utf-8")
    ledger = GateEvidenceLedger(
        repoHeadSha="1" * 40,
        branch="codex/test",
        target=_target(),
        gateResults=[
            _pass_result("control-plane-gate", str(artifact.relative_to(tmp_path)), "f" * 64)
        ],
        requiredGateIds=["control-plane-gate"],
        status="ready",
        artifactRoot="artifacts/release-gates/mainline-rc",
    )
    ledger_path = write_gate_evidence_ledger(ledger=ledger, repo_root=tmp_path)

    report = verify_gate_evidence_ledger(ledger_path=ledger_path, repo_root=tmp_path)

    assert report.status == "blocked"
    assert report.tampered_artifact_refs == [str(artifact.relative_to(tmp_path)).replace("\\", "/")]
    assert "ARTIFACT_HASH_MISMATCH" in report.reason_codes


def test_verifier_blocks_raw_marker_fixture(tmp_path: Path) -> None:
    ledger_path = tmp_path / "ledger.json"
    ledger_path.write_text(
        json.dumps(
            {
                "schemaVersion": "release.gate-evidence-ledger/v1",
                "repoHeadSha": "1" * 40,
                "branch": "codex/test",
                "target": _target().model_dump(mode="json", by_alias=True),
                "gateResults": [],
                "requiredGateIds": [],
                "status": "ready",
                "artifactRoot": "artifacts/release-gates/mainline-rc",
                "blockingReasons": [],
                "warnings": [],
                "generatedAtUtc": datetime.now(UTC).isoformat(),
                "ledgerSha256": None,
                "rawPrompt": "do not persist",
            }
        ),
        encoding="utf-8",
    )

    report = verify_gate_evidence_ledger(ledger_path=ledger_path, repo_root=tmp_path)

    assert report.status == "blocked"
    assert "LEDGER_INVALID" in report.reason_codes
