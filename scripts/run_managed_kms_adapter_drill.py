from __future__ import annotations

import argparse
import base64
import json
import shutil
import stat
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from imperaos.enterprise.signing import (
    fingerprint_public_key,
    key_status,
    rotate_plan,
    verify_signed_artifact,
    write_signed_json,
)
from imperaos.runtime.config import RuntimeConfig

SCHEMA_VERSION = "imperaos-managed-kms-adapter-drill/v2"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _managed_signer_script() -> str:
    return r'''from __future__ import annotations

import base64
import json
import sys

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def main() -> None:
    key_path = sys.argv[1]
    key_payload = json.loads(open(key_path, encoding="utf-8").read())
    request = json.loads(sys.stdin.read())
    private_key = Ed25519PrivateKey.from_private_bytes(
        base64.b64decode(key_payload["private_key"])
    )
    signature = private_key.sign(str(request["hash"]).encode("utf-8"))
    print(
        json.dumps(
            {
                "key_id": key_payload["key_id"],
                "public_key": key_payload["public_key"],
                "signature": base64.b64encode(signature).decode("ascii"),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
'''


def _generate_key(key_id: str) -> dict[str, str]:
    private_key = Ed25519PrivateKey.generate()
    private_raw = private_key.private_bytes_raw()
    public_raw = private_key.public_key().public_bytes_raw()
    return {
        "schema_version": "1",
        "key_id": key_id,
        "algorithm": "ed25519",
        "purpose": "artifact-signing",
        "private_key": base64.b64encode(private_raw).decode("ascii"),
        "public_key": base64.b64encode(public_raw).decode("ascii"),
        "created_at": _now_iso(),
    }


def _public_record(key: dict[str, str], *, state: str = "active") -> dict[str, str]:
    return {
        "schema_version": "1",
        "key_id": key["key_id"],
        "algorithm": key["algorithm"],
        "purpose": key["purpose"],
        "public_key": key["public_key"],
        "state": state,
        "created_at": key["created_at"],
    }


def _build_config(
    *,
    output_root: Path,
    key_id: str,
    signer_script: Path,
    private_key_path: Path,
) -> RuntimeConfig:
    base = RuntimeConfig.from_profile("enterprise")
    return base.model_copy(
        update={
            "keys": base.keys.model_copy(
                update={
                    "provider": "managed_kms",
                    "current_key_id": key_id,
                    "private_key_path": str(output_root / "private_key_not_persisted.json"),
                    "trusted_public_keys_dir": str(output_root / "trusted_public_keys"),
                    "key_manifest_path": str(output_root / "key_manifest.json"),
                    "managed_signer_command": [
                        sys.executable,
                        str(signer_script),
                        str(private_key_path),
                    ],
                    "allow_env_hmac_compat": False,
                }
            )
        }
    )


def _scan_for_secret(output_root: Path, secret: str) -> list[str]:
    matches: list[str] = []
    for path in sorted(item for item in output_root.rglob("*") if item.is_file()):
        try:
            if secret in path.read_text(encoding="utf-8"):
                matches.append(path.relative_to(output_root).as_posix())
        except UnicodeDecodeError:
            if secret.encode("utf-8") in path.read_bytes():
                matches.append(path.relative_to(output_root).as_posix())
    return matches


def _write_readme(path: Path, *, status: str) -> None:
    path.write_text(
        "\n".join(
            [
                "# Managed KMS Adapter Drill Evidence",
                "",
                f"Status: `{status}`",
                "",
                "This evidence exercises the `managed_kms` subprocess signer adapter.",
                "It is not a vendor cloud KMS or hardware HSM attestation.",
                "PKCS#11/HSM breadth remains deferred.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def run_drill(
    *,
    output_root: Path,
    key_id: str = "managed-kms-drill-current",
    next_key_id: str = "managed-kms-drill-next",
) -> dict[str, Any]:
    output_root = output_root.resolve()
    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True)

    trusted_dir = output_root / "trusted_public_keys"
    trusted_dir.mkdir(parents=True)

    with tempfile.TemporaryDirectory(prefix="imperaos-managed-kms-") as tmp:
        tmp_dir = Path(tmp)
        current_key = _generate_key(key_id)
        next_key = _generate_key(next_key_id)

        private_key_path = tmp_dir / "managed_kms_private_key.json"
        _write_json(private_key_path, current_key)
        private_key_path.chmod(stat.S_IRUSR | stat.S_IWUSR)

        signer_script = tmp_dir / "managed_signer.py"
        signer_script.write_text(_managed_signer_script(), encoding="utf-8")
        signer_script.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)

        _write_json(trusted_dir / f"{key_id}.json", _public_record(current_key))
        _write_json(
            output_root / "key_manifest.json",
            {
                "schema_version": "1",
                "current_key_id": key_id,
                "revoked_keys": [],
            },
        )

        config = _build_config(
            output_root=output_root,
            key_id=key_id,
            signer_script=signer_script,
            private_key_path=private_key_path,
        )
        status_payload = key_status(config)
        _write_json(output_root / "keys_status.json", status_payload)

        sample_path = output_root / "managed_kms_sample_artifact.json"
        write_signed_json(
            path=sample_path,
            artifact="managed_kms_sample_artifact",
            data={
                "schema_version": SCHEMA_VERSION,
                "generated_by": "scripts/run_managed_kms_adapter_drill.py",
                "provider": "managed_kms",
                "purpose": "sign_verify_drill",
            },
            config=config,
            purpose="managed-kms-drill",
            status="pass",
        )
        sample_verify = verify_signed_artifact(path=sample_path, config=config)
        _write_json(output_root / "managed_kms_sample_artifact_verify.json", sample_verify)

        restore_dir = output_root / "restore_time"
        restore_dir.mkdir()
        restore_sample = restore_dir / sample_path.name
        shutil.copy2(sample_path, restore_sample)
        restore_verify = verify_signed_artifact(path=restore_sample, config=config)
        _write_json(output_root / "restore_time_verify.json", restore_verify)

        rotation_plan = rotate_plan(config, next_key_id=next_key_id)
        rotation_plan["next_public_key_fingerprint"] = fingerprint_public_key(
            next_key["public_key"]
        )
        _write_json(output_root / "rotation_plan.json", rotation_plan)

        revoked_manifest = output_root / "key_manifest_revoked_probe.json"
        _write_json(
            revoked_manifest,
            {
                "schema_version": "1",
                "current_key_id": key_id,
                "revoked_keys": [key_id],
            },
        )
        revoked_verify = verify_signed_artifact(
            path=sample_path,
            trusted_keys_dir=trusted_dir,
            key_manifest_path=revoked_manifest,
        )
        _write_json(output_root / "revoked_key_reject.json", revoked_verify)

        report_data = {
            "schema_version": SCHEMA_VERSION,
            "provider": "managed_kms",
            "adapter_contract": "subprocess_json_hash_signer",
            "external_hsm_attestation": "not_run",
            "pkcs11_hsm_status": "deferred",
            "key_id": key_id,
            "public_key_fingerprint": fingerprint_public_key(current_key["public_key"]),
            "drills": {
                "sign_verify": {
                    "status": "pass" if sample_verify.get("verified") else "fail",
                    "signature_mode": sample_verify.get("signature_mode"),
                    "key_id": sample_verify.get("key_id"),
                },
                "rotation_dry_run": {
                    "status": "pass" if rotation_plan.get("enterprise_ready") else "fail",
                    "steps": rotation_plan.get("steps"),
                    "next_key_id": rotation_plan.get("next_key_id"),
                },
                "revoked_key_reject": {
                    "status": (
                        "pass"
                        if not revoked_verify.get("verified")
                        and revoked_verify.get("error_code") == "TRUSTED_KEY_NOT_FOUND"
                        else "fail"
                    ),
                    "error_code": revoked_verify.get("error_code"),
                },
                "restore_time_historical_verify": {
                    "status": "pass" if restore_verify.get("verified") else "fail",
                    "signature_mode": restore_verify.get("signature_mode"),
                },
            },
            "evidence_files": {
                "sample_artifact": sample_path.name,
                "sample_verify": "managed_kms_sample_artifact_verify.json",
                "keys_status": "keys_status.json",
                "rotation_plan": "rotation_plan.json",
                "revoked_key_reject": "revoked_key_reject.json",
                "restore_time_verify": "restore_time_verify.json",
            },
            "no_ship_boundaries": [
                "external cloud KMS attestation not claimed",
                "hardware HSM/PKCS#11 breadth not claimed",
            ],
        }

        preliminary_secret_matches = _scan_for_secret(output_root, current_key["private_key"])
        report_data["secret_material_persisted_in_evidence"] = bool(preliminary_secret_matches)
        report_data["secret_material_matches"] = preliminary_secret_matches
        overall_status = (
            "pass"
            if all(item["status"] == "pass" for item in report_data["drills"].values())
            and not preliminary_secret_matches
            else "fail"
        )

        report_path = output_root / "managed_kms_live_drill.json"
        write_signed_json(
            path=report_path,
            artifact="managed_kms_live_drill",
            data=report_data,
            config=config,
            purpose="managed-kms-live-drill-report",
            status=overall_status,
        )
        report_verify = verify_signed_artifact(path=report_path, config=config)
        _write_json(output_root / "managed_kms_live_drill_verify.json", report_verify)

        final_secret_matches = _scan_for_secret(output_root, current_key["private_key"])
        if final_secret_matches:
            report_data["secret_material_persisted_in_evidence"] = True
            report_data["secret_material_matches"] = final_secret_matches
            overall_status = "fail"
            write_signed_json(
                path=report_path,
                artifact="managed_kms_live_drill",
                data=report_data,
                config=config,
                purpose="managed-kms-live-drill-report",
                status=overall_status,
            )
            report_verify = verify_signed_artifact(path=report_path, config=config)
            _write_json(output_root / "managed_kms_live_drill_verify.json", report_verify)

    summary = {
        "schema_version": SCHEMA_VERSION,
        "output_root": str(output_root),
        "status": overall_status,
        "report": str(output_root / "managed_kms_live_drill.json"),
        "report_verified": bool(report_verify.get("verified")),
        "key_id": key_id,
        "pkcs11_hsm_status": "deferred",
        "generated_at_utc": _now_iso(),
    }
    _write_json(output_root / "summary.json", summary)
    _write_readme(output_root / "README.md", status=overall_status)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a managed_kms adapter sign/verify and rotation drill."
    )
    parser.add_argument(
        "--output-root",
        default="artifacts/readiness/managed_kms_adapter_drill",
        help="Directory where drill evidence is written.",
    )
    parser.add_argument("--key-id", default="managed-kms-drill-current")
    parser.add_argument("--next-key-id", default="managed-kms-drill-next")
    args = parser.parse_args()

    summary = run_drill(
        output_root=Path(args.output_root),
        key_id=args.key_id,
        next_key_id=args.next_key_id,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    if summary.get("status") != "pass" or not summary.get("report_verified"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
