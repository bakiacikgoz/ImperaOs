from __future__ import annotations

from pathlib import Path

from imperaos.release.gate_models import GateEvidenceLedger


def test_release_gate_contract_fixtures_validate() -> None:
    fixture_root = Path("contracts/release/fixtures")

    for path in sorted(fixture_root.glob("gate_evidence_ledger_*.json")):
        ledger = GateEvidenceLedger.model_validate_json(path.read_text(encoding="utf-8"))
        assert ledger.schema_version == "release.gate-evidence-ledger/v1"
        assert ledger.target.target_id == "mainline-rc"
