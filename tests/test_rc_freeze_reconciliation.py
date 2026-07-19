from __future__ import annotations

from pathlib import Path

from imperaos.release.gate_ledger import write_gate_evidence_ledger
from imperaos.release.gate_models import GateEvidenceLedger
from imperaos.release_decision.reconciler import build_reconciliation_input, reconcile_rc_freeze


def _copy_fixture(name: str, tmp_path: Path) -> Path:
    source = Path("contracts/release/fixtures") / name
    target = tmp_path / "artifacts" / "release-gates" / "mainline-rc" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    return target


def test_reconcile_ready_ledger_closes_missing_artifact_conditionals(tmp_path: Path) -> None:
    ledger_fixture = _copy_fixture("gate_evidence_ledger_pass.json", tmp_path)
    ledger = GateEvidenceLedger.model_validate_json(ledger_fixture.read_text(encoding="utf-8"))
    ledger_path = write_gate_evidence_ledger(ledger=ledger, repo_root=tmp_path)
    freeze = tmp_path / "artifacts" / "mainline-rc-freeze" / "manifest.json"
    freeze.parent.mkdir(parents=True)
    freeze.write_text(
        '{"schemaVersion":"control-plane.rc-freeze-manifest/v1","status":"conditional",'
        '"warnings":["REQUIRED_GATE_MISSING:control-plane-gate",'
        '"REQUIRED_GATE_MISSING:design-partner-handoff-gate"],"blockers":[]}',
        encoding="utf-8",
    )

    report = reconcile_rc_freeze(
        build_reconciliation_input(
            gate_ledger_path=ledger_path,
            freeze_manifest_path=freeze,
            repo_root=tmp_path,
        )
    )

    assert report.status == "ready"
    assert report.reconciled_status == "ready"
    assert "REQUIRED_GATE_MISSING:control-plane-gate" in report.closed_conditional_reasons
    assert report.remaining_conditional_reasons == []


def test_reconcile_blocks_hash_mismatch(tmp_path: Path) -> None:
    ledger = _copy_fixture("gate_evidence_ledger_tampered_hash.json", tmp_path)
    freeze = tmp_path / "artifacts" / "mainline-rc-freeze" / "manifest.json"
    freeze.parent.mkdir(parents=True)
    freeze.write_text('{"status":"conditional","warnings":[],"blockers":[]}', encoding="utf-8")

    report = reconcile_rc_freeze(
        build_reconciliation_input(
            gate_ledger_path=ledger,
            freeze_manifest_path=freeze,
            repo_root=tmp_path,
        )
    )

    assert report.status == "blocked"
    assert "ARTIFACT_HASH_MISMATCH" in report.blocking_reasons
