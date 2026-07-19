from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from imperaos.enterprise.signing import verify_signed_artifact

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "run_managed_kms_adapter_drill.py"
SPEC = importlib.util.spec_from_file_location("run_managed_kms_adapter_drill", SCRIPT_PATH)
assert SPEC is not None
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)
run_drill = MODULE.run_drill


def test_managed_kms_adapter_drill_publishes_pass_evidence(tmp_path: Path) -> None:
    output_root = tmp_path / "managed-kms-drill"

    summary = run_drill(output_root=output_root)

    assert summary["status"] == "pass"
    assert summary["report_verified"] is True
    report_path = output_root / "managed_kms_live_drill.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "pass"
    assert report["integrity"]["signature_mode"] == "managed_kms"
    assert report["data"]["provider"] == "managed_kms"
    assert report["data"]["pkcs11_hsm_status"] == "deferred"
    assert report["data"]["secret_material_persisted_in_evidence"] is False

    assert report["data"]["drills"]["sign_verify"]["status"] == "pass"
    assert report["data"]["drills"]["rotation_dry_run"]["status"] == "pass"
    assert report["data"]["drills"]["revoked_key_reject"]["status"] == "pass"
    assert report["data"]["drills"]["restore_time_historical_verify"]["status"] == "pass"


def test_managed_kms_adapter_drill_revoked_manifest_rejects_signed_artifact(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "managed-kms-drill"

    run_drill(output_root=output_root)

    sample_path = output_root / "managed_kms_sample_artifact.json"
    revoked = verify_signed_artifact(
        path=sample_path,
        trusted_keys_dir=output_root / "trusted_public_keys",
        key_manifest_path=output_root / "key_manifest_revoked_probe.json",
    )
    assert revoked["verified"] is False
    assert revoked["error_code"] == "TRUSTED_KEY_NOT_FOUND"
