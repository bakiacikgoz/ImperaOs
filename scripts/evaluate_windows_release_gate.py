from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "windows-public-release-gate/v1"
DECISION_SOURCE = "scripts/evaluate_windows_release_gate.py"
EXPECTED_COMPUTER_USE_REASON = "WINDOWS_COMPUTER_USE_NOT_QUALIFIED"
EXPECTED_RUNTIME_PYTHON = "python/Scripts/python.exe"
WINDOWS_RUNTIME_MANIFEST_KEYS = frozenset(
    {
        "arch",
        "imperaos_version",
        "created_at_utc",
        "git_sha",
        "platform",
        "python",
        "python_exe_sha256",
        "source_wheel",
        "source_wheel_sha256",
        "uv_lock_sha256",
    }
)


@dataclass(frozen=True)
class LoadedEvidence:
    path: Path | None
    status: str
    sha256: str | None = None
    data: Any = None
    text: str | None = None

    def input_report(self) -> dict[str, str | None]:
        return {
            "path": str(self.path) if self.path else None,
            "sha256": self.sha256,
            "status": self.status,
        }


def _add_reason(reasons: list[str], reason: str) -> None:
    if reason not in reasons:
        reasons.append(reason)


def _add_warning(warnings: list[str], warning: str) -> None:
    if warning not in warnings:
        warnings.append(warning)


def _file_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_json_with_evidence(path: Path | None) -> LoadedEvidence:
    if path is None:
        return LoadedEvidence(path=None, status="missing")
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return LoadedEvidence(path=path, status="missing")
    try:
        return LoadedEvidence(
            path=path,
            status="present",
            sha256=_file_sha256(raw),
            data=json.loads(raw.decode("utf-8-sig")),
        )
    except (UnicodeDecodeError, json.JSONDecodeError):
        return LoadedEvidence(path=path, status="invalid_json", sha256=_file_sha256(raw))


def load_text_with_evidence(path: Path | None) -> LoadedEvidence:
    if path is None:
        return LoadedEvidence(path=None, status="missing")
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return LoadedEvidence(path=path, status="missing")
    try:
        return LoadedEvidence(
            path=path,
            status="present",
            sha256=_file_sha256(raw),
            text=raw.decode("utf-8-sig"),
        )
    except UnicodeDecodeError:
        return LoadedEvidence(path=path, status="invalid", sha256=_file_sha256(raw))


def parse_runtime_manifest(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or not key:
            raise ValueError(f"invalid manifest line: {raw_line}")
        if key in values:
            raise ValueError(f"duplicate manifest key: {key}")
        values[key] = value
    return values


def _bool_value(payload: Mapping[str, Any] | None, key: str) -> bool:
    return bool(payload and payload.get(key) is True)


def _status_value(payload: Mapping[str, Any] | None, key: str) -> str:
    if not payload:
        return "missing"
    value = payload.get(key)
    return str(value).strip().lower() if value is not None else "missing"


def _status_value_any(payload: Mapping[str, Any] | None, keys: tuple[str, ...]) -> str:
    value = _first_present(payload, keys)
    return str(value).strip().lower() if value is not None else "missing"


def _first_present(payload: Mapping[str, Any] | None, keys: tuple[str, ...]) -> Any:
    if not payload:
        return None
    for key in keys:
        if key in payload and payload[key] not in (None, ""):
            return payload[key]
    return None


def _computer_use_capability(payload: Mapping[str, Any] | None) -> Mapping[str, Any]:
    features = payload.get("features") if payload else None
    if isinstance(features, Mapping):
        capability = features.get("computerUsePilot")
        if isinstance(capability, Mapping):
            return capability
    return {}


def _doctor_reports_failure(payload: Mapping[str, Any] | None) -> bool:
    if not payload:
        return True
    status = _first_present(payload, ("status", "overall_status", "result"))
    if status is None:
        return False
    return str(status).strip().lower() in {"fail", "failed", "error", "red"}


def _sha256ish(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        char in "0123456789abcdefABCDEF" for char in value
    )


def validate_runtime_manifest(
    evidence: LoadedEvidence,
    blocking_reasons: list[str],
) -> dict[str, str] | None:
    if evidence.status == "missing":
        _add_reason(blocking_reasons, "runtime_manifest_missing")
        return None
    if evidence.status != "present" or evidence.text is None:
        _add_reason(blocking_reasons, "runtime_manifest_invalid")
        return None
    try:
        manifest = parse_runtime_manifest(evidence.text)
    except ValueError:
        _add_reason(blocking_reasons, "runtime_manifest_invalid")
        return None

    if set(manifest) != WINDOWS_RUNTIME_MANIFEST_KEYS or any(
        not value.strip() for value in manifest.values()
    ):
        _add_reason(blocking_reasons, "runtime_manifest_invalid")
    if manifest.get("platform") != "windows":
        _add_reason(blocking_reasons, "runtime_manifest_platform_mismatch")
    if manifest.get("arch") != "x86_64":
        _add_reason(blocking_reasons, "runtime_manifest_arch_mismatch")
    if manifest.get("python") != EXPECTED_RUNTIME_PYTHON:
        _add_reason(blocking_reasons, "runtime_manifest_python_path_mismatch")
    if not _sha256ish(manifest.get("python_exe_sha256")):
        _add_reason(blocking_reasons, "runtime_manifest_python_hash_missing")
    return manifest


def validate_bundle_hashes(
    evidence: LoadedEvidence,
    installer_sha256: str | None,
    blocking_reasons: list[str],
) -> None:
    if evidence.status == "missing":
        _add_reason(blocking_reasons, "bundle_hashes_missing")
        return
    if evidence.status != "present":
        _add_reason(blocking_reasons, "bundle_hashes_invalid_json")
        return
    payload = evidence.data
    if isinstance(payload, Mapping):
        items = [payload]
    elif isinstance(payload, list):
        items = payload
    else:
        _add_reason(blocking_reasons, "bundle_hashes_invalid_json")
        return
    hashes: list[str] = []
    for item in items:
        if not isinstance(item, Mapping):
            _add_reason(blocking_reasons, "bundle_hashes_invalid_json")
            return
        sha = item.get("sha256")
        if not _sha256ish(sha):
            _add_reason(blocking_reasons, "bundle_hashes_invalid_json")
            return
        hashes.append(str(sha).lower())

    if not installer_sha256:
        _add_reason(blocking_reasons, "bundle_hashes_installer_hash_missing")
        return
    if installer_sha256.lower() not in hashes:
        _add_reason(blocking_reasons, "bundle_hashes_installer_hash_mismatch")


def evaluate_gate(
    *,
    release_status: LoadedEvidence,
    installer_smoke: LoadedEvidence,
    operator_capabilities: LoadedEvidence,
    doctor: LoadedEvidence,
    runtime_manifest: LoadedEvidence | None = None,
    bundle_hashes: LoadedEvidence | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    blocking_reasons: list[str] = []
    warnings: list[str] = []

    release_payload = release_status.data if isinstance(release_status.data, Mapping) else None
    smoke_payload = installer_smoke.data if isinstance(installer_smoke.data, Mapping) else None
    capabilities_payload = (
        operator_capabilities.data if isinstance(operator_capabilities.data, Mapping) else None
    )
    doctor_payload = doctor.data if isinstance(doctor.data, Mapping) else None

    if release_status.status == "missing":
        _add_reason(blocking_reasons, "release_status_missing")
    elif release_status.status != "present":
        _add_reason(blocking_reasons, "release_status_invalid_json")

    if installer_smoke.status == "missing":
        _add_reason(blocking_reasons, "installer_smoke_missing")
        _add_reason(blocking_reasons, "clean_vm_smoke_missing")
    elif installer_smoke.status != "present":
        _add_reason(blocking_reasons, "installer_smoke_invalid_json")

    if operator_capabilities.status == "missing":
        _add_reason(blocking_reasons, "operator_capabilities_missing")
    elif operator_capabilities.status != "present":
        _add_reason(blocking_reasons, "operator_capabilities_invalid_json")

    if doctor.status == "missing":
        _add_reason(blocking_reasons, "doctor_missing")
    elif doctor.status != "present":
        _add_reason(blocking_reasons, "doctor_invalid_json")

    if release_payload and release_payload.get("platform") != "windows":
        _add_reason(blocking_reasons, "release_platform_mismatch")
    if smoke_payload and smoke_payload.get("platform") != "windows":
        _add_reason(blocking_reasons, "installer_smoke_platform_mismatch")

    if release_payload and release_payload.get("public_release_allowed") is True:
        _add_warning(warnings, "release_status_public_release_claim_ignored_warning")

    signed = _bool_value(release_payload, "signed")
    timestamped = _bool_value(release_payload, "timestamped")
    signtool_verify_status = _status_value(release_payload, "signtool_verify_status")

    if not signed:
        _add_reason(blocking_reasons, "artifact_not_signed")
    if not timestamped:
        _add_reason(blocking_reasons, "artifact_not_timestamped")
    if signtool_verify_status != "pass":
        _add_reason(blocking_reasons, "signtool_verify_not_pass")

    clean_vm_claimed = _bool_value(smoke_payload, "clean_vm_claimed")
    run_install_used = _bool_value(smoke_payload, "run_install_used")
    allow_unsigned_smoke_used = _bool_value(smoke_payload, "allow_unsigned_smoke_used")
    installer_signed = _bool_value(smoke_payload, "signed")
    smoke_timestamped = bool(
        _bool_value(smoke_payload, "timestamped")
        or _bool_value(smoke_payload, "installer_timestamped")
    )
    signature_status = _status_value_any(
        smoke_payload,
        ("signature_status", "installer_signature_status"),
    )
    smoke_signtool_verify_status = _status_value(smoke_payload, "signtool_verify_status")
    app_launch_status = _status_value(smoke_payload, "app_launch_status")

    if allow_unsigned_smoke_used:
        _add_reason(blocking_reasons, "unsigned_internal_smoke_not_public_release_eligible")
    if smoke_payload and not installer_signed:
        _add_reason(blocking_reasons, "artifact_not_signed")
    if smoke_payload and not smoke_timestamped:
        _add_reason(blocking_reasons, "installer_smoke_timestamp_missing")
    if smoke_payload and signature_status != "valid":
        _add_reason(blocking_reasons, "installer_smoke_signature_not_valid")
    if smoke_payload and smoke_signtool_verify_status != "pass":
        _add_reason(blocking_reasons, "installer_smoke_signtool_verify_not_pass")
    if smoke_payload and (not clean_vm_claimed or not run_install_used):
        _add_reason(blocking_reasons, "clean_vm_smoke_missing")

    installer_status = _status_value(smoke_payload, "install_status")
    bundled_runtime_status = _status_value(smoke_payload, "bundled_runtime_status")
    operator_capabilities_status = _status_value(smoke_payload, "operator_capabilities_status")
    doctor_status = _status_value(smoke_payload, "doctor_status")

    if smoke_payload and installer_status != "pass":
        _add_reason(blocking_reasons, "installer_install_not_pass")
    if smoke_payload and bundled_runtime_status != "pass":
        _add_reason(blocking_reasons, "bundled_runtime_not_pass")
    if smoke_payload and operator_capabilities_status != "pass":
        _add_reason(blocking_reasons, "operator_capabilities_not_pass")
    if smoke_payload and doctor_status != "pass":
        _add_reason(blocking_reasons, "doctor_not_pass")
    if smoke_payload and app_launch_status != "pass":
        _add_reason(blocking_reasons, "app_launch_not_pass")

    smoke_computer_use_enabled = bool(
        smoke_payload
        and (
            smoke_payload.get("computer_use_live_enabled") is True
            or smoke_payload.get("computer_use_enabled") is True
        )
    )
    if smoke_computer_use_enabled:
        _add_reason(blocking_reasons, "smoke_computer_use_enabled")
    if (
        smoke_payload
        and smoke_payload.get("computer_use_reason_code") != EXPECTED_COMPUTER_USE_REASON
    ):
        _add_reason(blocking_reasons, "smoke_computer_use_reason_code_mismatch")
    if smoke_payload and str(smoke_payload.get("webview2_status", "")).lower() not in {
        "present",
        "present_inferred",
    }:
        _add_warning(warnings, "webview2_not_detected_for_smoke")

    capability = _computer_use_capability(capabilities_payload)
    computer_use_enabled = bool(capability.get("enabled") is True)
    computer_use_reason_code = capability.get("reasonCode")
    computer_use_platform = capability.get("platform")
    computer_use_stage = capability.get("stage")

    if computer_use_enabled:
        _add_reason(blocking_reasons, "computer_use_enabled")
    if computer_use_reason_code != EXPECTED_COMPUTER_USE_REASON:
        _add_reason(blocking_reasons, "computer_use_reason_code_mismatch")
    if computer_use_platform not in (None, "windows"):
        _add_reason(blocking_reasons, "computer_use_platform_mismatch")
    if computer_use_stage not in (None, "not_qualified"):
        _add_reason(blocking_reasons, "computer_use_stage_mismatch")

    if _doctor_reports_failure(doctor_payload):
        _add_reason(blocking_reasons, "doctor_not_pass")

    release_hash = _first_present(
        release_payload,
        ("installer_sha256", "artifact_sha256", "nsis_sha256"),
    )
    smoke_hash = _first_present(smoke_payload, ("installer_sha256",))
    if release_hash and smoke_hash and str(release_hash).lower() != str(smoke_hash).lower():
        _add_reason(blocking_reasons, "installer_hash_mismatch")

    runtime_manifest = runtime_manifest or LoadedEvidence(path=None, status="missing")
    bundle_hashes = bundle_hashes or LoadedEvidence(path=None, status="missing")
    validate_runtime_manifest(runtime_manifest, blocking_reasons)
    validate_bundle_hashes(
        bundle_hashes,
        str(release_hash).lower() if release_hash else None,
        blocking_reasons,
    )

    signed_rc_allowed = (
        release_status.status == "present"
        and signed
        and timestamped
        and signtool_verify_status == "pass"
    )
    public_release_allowed = len(blocking_reasons) == 0

    fail_reasons = {
        "bundle_hashes_installer_hash_mismatch",
        "computer_use_enabled",
        "computer_use_platform_mismatch",
        "computer_use_reason_code_mismatch",
        "computer_use_stage_mismatch",
        "doctor_invalid_json",
        "installer_hash_mismatch",
        "installer_smoke_invalid_json",
        "operator_capabilities_invalid_json",
        "release_platform_mismatch",
        "release_status_invalid_json",
        "smoke_computer_use_enabled",
        "smoke_computer_use_reason_code_mismatch",
    }
    if public_release_allowed:
        status = "pass"
    elif any(reason in blocking_reasons for reason in fail_reasons):
        status = "fail"
    else:
        status = "blocked"

    inputs = {
        "bundle_hashes": bundle_hashes.input_report(),
        "doctor": doctor.input_report(),
        "installer_smoke": installer_smoke.input_report(),
        "operator_capabilities": operator_capabilities.input_report(),
        "release_status": release_status.input_report(),
        "runtime_manifest": runtime_manifest.input_report(),
    }

    return {
        "app_launch_status": app_launch_status,
        "artifact_type": str(release_payload.get("artifact_type", "nsis"))
        if release_payload
        else "nsis",
        "blocking_reasons": blocking_reasons,
        "bundled_runtime_status": bundled_runtime_status,
        "clean_vm_smoke_status": "pass"
        if clean_vm_claimed and run_install_used and installer_status == "pass"
        else "blocked",
        "computer_use_live_enabled": computer_use_enabled,
        "computer_use_reason_code": computer_use_reason_code,
        "decision_source": DECISION_SOURCE,
        "doctor_status": doctor_status,
        "generated_at_utc": generated_at_utc
        or datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "inputs": inputs,
        "installer_smoke_status": installer_status,
        "installer_smoke_signtool_verify_status": smoke_signtool_verify_status,
        "operator_capabilities_status": operator_capabilities_status,
        "platform": "windows",
        "public_release_allowed": public_release_allowed,
        "schemaVersion": SCHEMA_VERSION,
        "signed": signed,
        "signed_rc_allowed": signed_rc_allowed,
        "signtool_verify_status": signtool_verify_status,
        "status": status,
        "timestamped": timestamped,
        "warnings": warnings,
    }


def evaluate_from_files(args: argparse.Namespace) -> dict[str, Any]:
    return evaluate_gate(
        release_status=load_json_with_evidence(args.release_status),
        installer_smoke=load_json_with_evidence(args.installer_smoke),
        operator_capabilities=load_json_with_evidence(args.operator_capabilities),
        doctor=load_json_with_evidence(args.doctor),
        runtime_manifest=load_text_with_evidence(args.runtime_manifest),
        bundle_hashes=load_json_with_evidence(args.bundle_hashes),
    )


def write_gate_report(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate Windows public release gate evidence.")
    parser.add_argument("--release-status", required=True, type=Path)
    parser.add_argument("--installer-smoke", required=True, type=Path)
    parser.add_argument("--operator-capabilities", required=True, type=Path)
    parser.add_argument("--doctor", required=True, type=Path)
    parser.add_argument("--runtime-manifest", type=Path)
    parser.add_argument("--bundle-hashes", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--fail-on-blocked", action="store_true")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    report = evaluate_from_files(args)
    write_gate_report(args.output, report)
    if args.fail_on_blocked and not report["public_release_allowed"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
