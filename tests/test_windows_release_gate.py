from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "evaluate_windows_release_gate.py"

spec = importlib.util.spec_from_file_location("evaluate_windows_release_gate", SCRIPT_PATH)
assert spec and spec.loader
gate = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = gate
spec.loader.exec_module(gate)

DEFAULT = object()
SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def loaded_json(payload, *, status="present"):
    return gate.LoadedEvidence(path=Path("fixture.json"), status=status, sha256=SHA_A, data=payload)


def loaded_text(text: str, *, status="present"):
    return gate.LoadedEvidence(path=Path("fixture.txt"), status=status, sha256=SHA_A, text=text)


def release_status(**overrides):
    payload = {
        "artifact_type": "nsis",
        "installer_sha256": SHA_A,
        "platform": "windows",
        "signed": True,
        "signtool_verify_status": "pass",
        "status": "signed_verified_external_smoke_required",
        "timestamped": True,
    }
    payload.update(overrides)
    return payload


def installer_smoke(**overrides):
    payload = {
        "allow_unsigned_smoke_used": False,
        "app_launch_status": "pass",
        "bundled_runtime_status": "pass",
        "clean_vm_claimed": True,
        "computer_use_live_enabled": False,
        "computer_use_reason_code": "WINDOWS_COMPUTER_USE_NOT_QUALIFIED",
        "doctor_status": "pass",
        "install_status": "pass",
        "installer_sha256": SHA_A,
        "operator_capabilities_status": "pass",
        "platform": "windows",
        "run_install_used": True,
        "signature_status": "Valid",
        "signtool_verify_status": "pass",
        "signed": True,
        "timestamped": True,
        "webview2_status": "present",
    }
    payload.update(overrides)
    return payload


def operator_capabilities(**overrides):
    computer_use = {
        "enabled": False,
        "failClosed": True,
        "platform": "windows",
        "reasonCode": "WINDOWS_COMPUTER_USE_NOT_QUALIFIED",
        "stage": "not_qualified",
    }
    computer_use.update(overrides)
    return {"features": {"computerUsePilot": computer_use}}


def doctor(**overrides):
    payload = {"status": "degraded_fallback"}
    payload.update(overrides)
    return payload


def runtime_manifest(**overrides) -> str:
    values = {
        "arch": "x86_64",
        "imperaos_version": "0.4.1",
        "created_at_utc": "2026-05-04T00:00:00Z",
        "git_sha": "d" * 40,
        "platform": "windows",
        "python": "python/Scripts/python.exe",
        "python_exe_sha256": SHA_B,
        "source_wheel": "imperaos-0.4.1-py3-none-any.whl",
        "source_wheel_sha256": SHA_A,
        "uv_lock_sha256": SHA_C,
    }
    values.update(overrides)
    return "\n".join(f"{key}={value}" for key, value in values.items()) + "\n"


def bundle_hashes(*, sha=SHA_A):
    return [
        {
            "path": "apps/operator-panel/src-tauri/target/release/bundle/nsis/app.exe",
            "sha256": sha,
        }
    ]


def evaluate(
    release=DEFAULT,
    smoke=DEFAULT,
    capabilities=DEFAULT,
    doctor_payload=DEFAULT,
    manifest=DEFAULT,
    hashes=DEFAULT,
):
    smoke_evidence = (
        gate.LoadedEvidence(path=Path("missing.json"), status="missing")
        if smoke is None
        else loaded_json(installer_smoke() if smoke is DEFAULT else smoke)
    )
    return gate.evaluate_gate(
        release_status=loaded_json(release_status() if release is DEFAULT else release),
        installer_smoke=smoke_evidence,
        operator_capabilities=loaded_json(
            operator_capabilities() if capabilities is DEFAULT else capabilities
        ),
        doctor=loaded_json(doctor() if doctor_payload is DEFAULT else doctor_payload),
        runtime_manifest=loaded_text(runtime_manifest() if manifest is DEFAULT else manifest),
        bundle_hashes=loaded_json(bundle_hashes() if hashes is DEFAULT else hashes),
        generated_at_utc="2026-05-04T00:00:00Z",
    )


def assert_blocked(report, reason: str):
    assert report["public_release_allowed"] is False
    assert reason in report["blocking_reasons"]


def test_all_required_evidence_passes_public_gate():
    report = evaluate()

    assert report["schemaVersion"] == "windows-public-release-gate/v1"
    assert report["status"] == "pass"
    assert report["signed_rc_allowed"] is True
    assert report["public_release_allowed"] is True
    assert report["blocking_reasons"] == []


def test_release_status_public_claim_is_ignored_without_smoke():
    report = evaluate(
        release=release_status(public_release_allowed=True),
        smoke=None,
    )

    assert_blocked(report, "clean_vm_smoke_missing")
    assert report["signed_rc_allowed"] is True
    assert "release_status_public_release_claim_ignored_warning" in report["warnings"]


def test_signing_missing_blocks_public_release():
    report = evaluate(release=release_status(signed=False))

    assert_blocked(report, "artifact_not_signed")
    assert report["signed_rc_allowed"] is False


def test_timestamp_missing_blocks_public_release():
    report = evaluate(release=release_status(timestamped=False))

    assert_blocked(report, "artifact_not_timestamped")
    assert report["signed_rc_allowed"] is False


def test_signtool_verify_fail_blocks_public_release():
    report = evaluate(release=release_status(signtool_verify_status="fail"))

    assert_blocked(report, "signtool_verify_not_pass")
    assert report["signed_rc_allowed"] is False


def test_clean_vm_smoke_missing_blocks_public_but_keeps_signed_rc_allowed():
    report = gate.evaluate_gate(
        release_status=loaded_json(release_status()),
        installer_smoke=gate.LoadedEvidence(path=Path("missing.json"), status="missing"),
        operator_capabilities=loaded_json(operator_capabilities()),
        doctor=loaded_json(doctor()),
        runtime_manifest=loaded_text(runtime_manifest()),
        bundle_hashes=loaded_json(bundle_hashes()),
        generated_at_utc="2026-05-04T00:00:00Z",
    )

    assert report["status"] == "blocked"
    assert report["blocking_reasons"] == ["installer_smoke_missing", "clean_vm_smoke_missing"]
    assert report["signed_rc_allowed"] is True
    assert report["public_release_allowed"] is False


def test_unsigned_internal_smoke_is_not_public_release_eligible():
    report = evaluate(smoke=installer_smoke(allow_unsigned_smoke_used=True, signed=False))

    assert_blocked(report, "unsigned_internal_smoke_not_public_release_eligible")
    assert report["signed_rc_allowed"] is True


def test_runtime_status_fail_blocks_public_release():
    report = evaluate(smoke=installer_smoke(bundled_runtime_status="fail"))

    assert_blocked(report, "bundled_runtime_not_pass")


def test_operator_capabilities_status_fail_blocks_public_release():
    report = evaluate(smoke=installer_smoke(operator_capabilities_status="fail"))

    assert_blocked(report, "operator_capabilities_not_pass")


def test_doctor_fail_blocks_public_release():
    report = evaluate(doctor_payload=doctor(status="fail"))

    assert_blocked(report, "doctor_not_pass")


def test_computer_use_enabled_is_hard_fail():
    report = evaluate(capabilities=operator_capabilities(enabled=True))

    assert report["status"] == "fail"
    assert_blocked(report, "computer_use_enabled")


def test_wrong_computer_use_reason_code_is_hard_fail():
    report = evaluate(capabilities=operator_capabilities(reasonCode="MACOS_COMPUTER_USE_PILOT"))

    assert report["status"] == "fail"
    assert_blocked(report, "computer_use_reason_code_mismatch")


def test_smoke_computer_use_enabled_is_hard_fail():
    report = evaluate(smoke=installer_smoke(computer_use_live_enabled=True))

    assert report["status"] == "fail"
    assert_blocked(report, "smoke_computer_use_enabled")


def test_smoke_computer_use_reason_code_mismatch_is_hard_fail():
    report = evaluate(smoke=installer_smoke(computer_use_reason_code="MACOS_COMPUTER_USE_PILOT"))

    assert report["status"] == "fail"
    assert_blocked(report, "smoke_computer_use_reason_code_mismatch")


def test_operator_capabilities_missing_blocks_public_release():
    report = gate.evaluate_gate(
        release_status=loaded_json(release_status()),
        installer_smoke=loaded_json(installer_smoke()),
        operator_capabilities=gate.LoadedEvidence(path=Path("missing.json"), status="missing"),
        doctor=loaded_json(doctor()),
        runtime_manifest=loaded_text(runtime_manifest()),
        bundle_hashes=loaded_json(bundle_hashes()),
        generated_at_utc="2026-05-04T00:00:00Z",
    )

    assert_blocked(report, "operator_capabilities_missing")


def test_installer_hash_mismatch_blocks_public_release():
    report = evaluate(smoke=installer_smoke(installer_sha256=SHA_B))

    assert report["status"] == "fail"
    assert_blocked(report, "installer_hash_mismatch")


def test_runtime_manifest_missing_blocks_public_release():
    report = gate.evaluate_gate(
        release_status=loaded_json(release_status()),
        installer_smoke=loaded_json(installer_smoke()),
        operator_capabilities=loaded_json(operator_capabilities()),
        doctor=loaded_json(doctor()),
        runtime_manifest=gate.LoadedEvidence(path=Path("missing.txt"), status="missing"),
        bundle_hashes=loaded_json(bundle_hashes()),
        generated_at_utc="2026-05-04T00:00:00Z",
    )

    assert_blocked(report, "runtime_manifest_missing")


def test_runtime_manifest_platform_mismatch_blocks_public_release():
    report = evaluate(manifest=runtime_manifest(platform="linux"))

    assert_blocked(report, "runtime_manifest_platform_mismatch")


def test_runtime_manifest_python_path_mismatch_blocks_public_release():
    report = evaluate(manifest=runtime_manifest(python="python/bin/python"))

    assert_blocked(report, "runtime_manifest_python_path_mismatch")


def test_runtime_manifest_rejects_extra_former_version_key():
    former_version_key = "bin" + "liquid_version"
    report = evaluate(
        manifest=runtime_manifest(**{former_version_key: "0.4.1"}),
    )

    assert_blocked(report, "runtime_manifest_invalid")


def test_runtime_manifest_rejects_duplicate_canonical_key():
    manifest = runtime_manifest() + "imperaos_version=0.4.1\n"

    report = evaluate(manifest=manifest)

    assert_blocked(report, "runtime_manifest_invalid")


def test_bundle_hashes_missing_blocks_public_release():
    report = gate.evaluate_gate(
        release_status=loaded_json(release_status()),
        installer_smoke=loaded_json(installer_smoke()),
        operator_capabilities=loaded_json(operator_capabilities()),
        doctor=loaded_json(doctor()),
        runtime_manifest=loaded_text(runtime_manifest()),
        bundle_hashes=gate.LoadedEvidence(path=Path("missing.json"), status="missing"),
        generated_at_utc="2026-05-04T00:00:00Z",
    )

    assert_blocked(report, "bundle_hashes_missing")


def test_bundle_hashes_installer_hash_mismatch_blocks_public_release():
    report = evaluate(hashes=bundle_hashes(sha=SHA_B))

    assert_blocked(report, "bundle_hashes_installer_hash_mismatch")


def test_single_object_bundle_hashes_from_powershell_are_accepted():
    report = evaluate(hashes=bundle_hashes()[0])

    assert report["status"] == "pass"
    assert report["public_release_allowed"] is True


def test_installer_smoke_timestamp_missing_blocks_public_release():
    report = evaluate(smoke=installer_smoke(timestamped=False))

    assert_blocked(report, "installer_smoke_timestamp_missing")


def test_installer_smoke_signature_not_valid_blocks_public_release():
    report = evaluate(smoke=installer_smoke(signature_status="UnknownError"))

    assert_blocked(report, "installer_smoke_signature_not_valid")


def test_installer_smoke_signtool_verify_fail_blocks_public_release():
    report = evaluate(smoke=installer_smoke(signtool_verify_status="fail"))

    assert_blocked(report, "installer_smoke_signtool_verify_not_pass")


def test_app_launch_fail_blocks_public_release():
    report = evaluate(smoke=installer_smoke(app_launch_status="fail"))

    assert_blocked(report, "app_launch_not_pass")


def test_installer_smoke_alias_fields_are_accepted():
    smoke = installer_smoke()
    smoke.pop("signature_status")
    smoke.pop("timestamped")
    smoke["installer_signature_status"] = "Valid"
    smoke["installer_timestamped"] = True

    report = evaluate(smoke=smoke)

    assert report["status"] == "pass"


def test_webview2_missing_warns_without_opening_public_claim():
    report = evaluate(smoke=installer_smoke(webview2_status="unknown"))

    assert report["public_release_allowed"] is True
    assert "webview2_not_detected_for_smoke" in report["warnings"]


def test_gate_report_includes_schema_version_generated_at_and_input_hashes():
    report = evaluate()

    assert report["schemaVersion"] == "windows-public-release-gate/v1"
    assert report["generated_at_utc"] == "2026-05-04T00:00:00Z"
    assert report["decision_source"] == "scripts/evaluate_windows_release_gate.py"
    assert report["inputs"]["release_status"]["sha256"] == SHA_A
    assert report["inputs"]["runtime_manifest"]["status"] == "present"


def test_malformed_json_is_reported_as_blocked(tmp_path):
    release_path = tmp_path / "windows-release-status.json"
    smoke_path = tmp_path / "windows-installer-smoke.json"
    capabilities_path = tmp_path / "operator_capabilities.json"
    doctor_path = tmp_path / "doctor_balanced.json"
    manifest_path = tmp_path / "runtime_manifest.txt"
    hashes_path = tmp_path / "bundle_hashes.json"
    output_path = tmp_path / "windows-public-release-gate.json"

    release_path.write_text(json.dumps(release_status()), encoding="utf-8")
    smoke_path.write_text(json.dumps(installer_smoke()), encoding="utf-8")
    capabilities_path.write_text("{not-json", encoding="utf-8")
    doctor_path.write_text(json.dumps(doctor()), encoding="utf-8")
    manifest_path.write_text(runtime_manifest(), encoding="utf-8")
    hashes_path.write_text(json.dumps(bundle_hashes()), encoding="utf-8")

    report = gate.evaluate_from_files(
        SimpleNamespace(
            bundle_hashes=hashes_path,
            doctor=doctor_path,
            installer_smoke=smoke_path,
            operator_capabilities=capabilities_path,
            output=output_path,
            release_status=release_path,
            runtime_manifest=manifest_path,
        )
    )

    assert report["status"] == "fail"
    assert_blocked(report, "operator_capabilities_invalid_json")


def test_windows_powershell_utf8_bom_json_is_accepted(tmp_path):
    release_path = tmp_path / "windows-release-status.json"
    smoke_path = tmp_path / "windows-installer-smoke.json"
    capabilities_path = tmp_path / "operator_capabilities.json"
    doctor_path = tmp_path / "doctor_balanced.json"
    manifest_path = tmp_path / "runtime_manifest.txt"
    hashes_path = tmp_path / "bundle_hashes.json"

    release_path.write_text(json.dumps(release_status()), encoding="utf-8-sig")
    smoke_path.write_text(json.dumps(installer_smoke()), encoding="utf-8-sig")
    capabilities_path.write_text(json.dumps(operator_capabilities()), encoding="utf-8-sig")
    doctor_path.write_text(json.dumps(doctor()), encoding="utf-8-sig")
    manifest_path.write_text(runtime_manifest(), encoding="utf-8-sig")
    hashes_path.write_text(json.dumps(bundle_hashes()), encoding="utf-8-sig")

    report = gate.evaluate_from_files(
        SimpleNamespace(
            bundle_hashes=hashes_path,
            doctor=doctor_path,
            installer_smoke=smoke_path,
            operator_capabilities=capabilities_path,
            output=tmp_path / "windows-public-release-gate.json",
            release_status=release_path,
            runtime_manifest=manifest_path,
        )
    )

    assert report["public_release_allowed"] is True


def test_fail_on_blocked_exit_code_is_two(tmp_path):
    release_path = tmp_path / "windows-release-status.json"
    smoke_path = tmp_path / "windows-installer-smoke.json"
    capabilities_path = tmp_path / "operator_capabilities.json"
    doctor_path = tmp_path / "doctor_balanced.json"
    manifest_path = tmp_path / "runtime_manifest.txt"
    hashes_path = tmp_path / "bundle_hashes.json"
    output_path = tmp_path / "windows-public-release-gate.json"

    release_path.write_text(json.dumps(release_status()), encoding="utf-8")
    capabilities_path.write_text(json.dumps(operator_capabilities()), encoding="utf-8")
    doctor_path.write_text(json.dumps(doctor()), encoding="utf-8")
    manifest_path.write_text(runtime_manifest(), encoding="utf-8")
    hashes_path.write_text(json.dumps(bundle_hashes()), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--release-status",
            str(release_path),
            "--installer-smoke",
            str(smoke_path),
            "--operator-capabilities",
            str(capabilities_path),
            "--doctor",
            str(doctor_path),
            "--runtime-manifest",
            str(manifest_path),
            "--bundle-hashes",
            str(hashes_path),
            "--output",
            str(output_path),
            "--fail-on-blocked",
        ],
        check=False,
        cwd=ROOT,
    )

    assert result.returncode == 2
