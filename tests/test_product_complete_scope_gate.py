from __future__ import annotations

import json
from pathlib import Path

from imperaos.release.product_complete import (
    ProductCompleteInput,
    build_product_complete_no_ship_register,
)
from scripts import run_product_complete_scope_gate as scope_gate


def test_product_complete_no_ship_blocks_unsupported_claims() -> None:
    register = build_product_complete_no_ship_register(
        ProductCompleteInput(
            assistant_preview_in_product_mode=True,
            fake_model_discovery=True,
            public_cloud_saas_claim=True,
            unrestricted_live_computer_use_claim=True,
            public_installer_signed_claim_without_evidence=True,
        )
    )

    reason_codes = {item.reason_code for item in register.items}
    assert register.status == "blocked"
    assert register.blocking_count == 5
    assert "ASSISTANT_PREVIEW_IN_PRODUCT_MODE" in reason_codes
    assert "ASSISTANT_MODEL_DISCOVERY_FAKE" in reason_codes
    assert "PUBLIC_CLOUD_SAAS_OUT_OF_SCOPE" in reason_codes
    assert "COMPUTER_USE_UNQUALIFIED_CLAIM" in reason_codes
    assert "PUBLIC_INSTALLER_UNSIGNED_CLAIM" in reason_codes


def test_scope_gate_writes_report_and_detects_scope_docs(tmp_path: Path, monkeypatch) -> None:
    docs_root = tmp_path / "docs"
    docs_root.mkdir()
    (docs_root / "PRODUCT_COMPLETE_SCOPE.md").write_text(
        "Self-hosted enterprise Agent Control Plane\n", encoding="utf-8"
    )
    (docs_root / "PRODUCT_COMPLETE_NO_SHIP_REGISTER.md").write_text(
        "ASSISTANT_PREVIEW_IN_PRODUCT_MODE\n", encoding="utf-8"
    )
    monkeypatch.setattr(scope_gate, "REPO_ROOT", tmp_path)

    report = scope_gate.run_scope_gate(output_root=tmp_path / "out")

    assert report["status"] == "pass"
    assert report["noShipRegister"]["blockingCount"] == 0
    output = tmp_path / "out" / "product_complete_scope_gate.json"
    assert output.exists()
    assert json.loads(output.read_text(encoding="utf-8"))["schemaVersion"] == (
        "product-complete.scope-gate/v1"
    )
