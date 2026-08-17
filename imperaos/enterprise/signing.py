from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from pydantic import BaseModel, ConfigDict

from imperaos.runtime.config import RuntimeConfig
from imperaos.runtime.paths import enterprise_state_path


class TrustedKey(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=False)

    schema_version: str = "1"
    key_id: str
    algorithm: str = "ed25519"
    purpose: str = "artifact-signing"
    public_key: str
    state: str = "active"
    created_at: datetime | None = None
    not_before: datetime | None = None
    not_after: datetime | None = None
    issuer: str | None = None


class PrivateKeyMaterial(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=False)

    schema_version: str = "1"
    key_id: str
    algorithm: str = "ed25519"
    purpose: str = "artifact-signing"
    private_key: str
    public_key: str
    created_at: datetime | None = None
    not_before: datetime | None = None
    not_after: datetime | None = None


class IntegrityRecord(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    prev_hash: str | None = None
    hash: str
    hash_algorithm: str = "sha256"
    signature: str | None = None
    signature_mode: str = "unsigned"
    key_id: str | None = None
    public_key_fingerprint: str | None = None


def canonical_payload_hash(payload: dict[str, Any], *, prev_hash: str | None = None) -> str:
    body = {"prev_hash": prev_hash, "payload": payload}
    raw = json.dumps(
        body,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=_json_default,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_integrity(
    *,
    payload: dict[str, Any],
    config: RuntimeConfig | None,
    purpose: str,
    prev_hash: str | None = None,
) -> dict[str, Any]:
    current_hash = canonical_payload_hash(payload, prev_hash=prev_hash)
    integrity = IntegrityRecord(prev_hash=prev_hash, hash=current_hash)

    if config is None:
        return integrity.model_dump(mode="json")

    signature_payload = _sign_hash(hash_value=current_hash, config=config, purpose=purpose)
    if signature_payload is None:
        return integrity.model_dump(mode="json")

    integrity = integrity.model_copy(
        update={
            "signature": signature_payload["signature"],
            "signature_mode": signature_payload["signature_mode"],
            "key_id": signature_payload.get("key_id"),
            "public_key_fingerprint": signature_payload.get("public_key_fingerprint"),
        }
    )
    return integrity.model_dump(mode="json")


def write_signed_json(
    *,
    path: str | Path,
    artifact: str,
    data: dict[str, Any],
    config: RuntimeConfig | None,
    purpose: str,
    status: str = "ok",
) -> str:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "artifact": artifact,
        "generated_at": _now_iso(),
        "status": status,
        "data": data,
    }
    body["integrity"] = build_integrity(payload=body, config=config, purpose=purpose)
    destination.write_text(json.dumps(body, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(destination)


def verify_signed_artifact(
    *,
    path: str | Path,
    config: RuntimeConfig | None = None,
    trusted_keys_dir: str | Path | None = None,
    key_manifest_path: str | Path | None = None,
) -> dict[str, Any]:
    source = Path(path)
    payload = json.loads(source.read_text(encoding="utf-8"))
    integrity_raw = payload.pop("integrity", None)
    if not isinstance(integrity_raw, dict):
        return {
            "path": str(source),
            "verified": False,
            "error_code": "INTEGRITY_MISSING",
        }
    integrity = IntegrityRecord.model_validate(integrity_raw)
    expected_hash = canonical_payload_hash(payload, prev_hash=integrity.prev_hash)
    if expected_hash != integrity.hash:
        return {
            "path": str(source),
            "verified": False,
            "error_code": "HASH_MISMATCH",
            "expected_hash": expected_hash,
            "actual_hash": integrity.hash,
        }
    if not integrity.signature:
        return {
            "path": str(source),
            "verified": True,
            "signature_verified": False,
            "signature_mode": integrity.signature_mode,
            "key_id": integrity.key_id,
        }
    if integrity.signature_mode == "env_hmac_compat":
        key = os.getenv("IMPERAOS_AUDIT_SIGNING_KEY", "").strip()
        if not key:
            return {
                "path": str(source),
                "verified": False,
                "error_code": "ENV_HMAC_KEY_MISSING",
                "key_id": integrity.key_id,
            }
        expected = hashlib.sha256((key + integrity.hash).encode("utf-8")).hexdigest()
        ok = expected == integrity.signature
        return {
            "path": str(source),
            "verified": ok,
            "signature_verified": ok,
            "signature_mode": integrity.signature_mode,
            "key_id": integrity.key_id,
            "public_key_fingerprint": hashlib.sha256(key.encode("utf-8")).hexdigest(),
            "error_code": None if ok else "SIGNATURE_INVALID",
        }

    trusted = _load_trusted_keys(
        config=config,
        trusted_keys_dir=trusted_keys_dir,
        key_manifest_path=key_manifest_path,
    )
    key = trusted.get(str(integrity.key_id or ""))
    if key is None:
        return {
            "path": str(source),
            "verified": False,
            "error_code": "TRUSTED_KEY_NOT_FOUND",
            "key_id": integrity.key_id,
        }
    ok = _verify_signature(integrity.hash, integrity.signature, key)
    return {
        "path": str(source),
        "verified": ok,
        "signature_verified": ok,
        "signature_mode": integrity.signature_mode,
        "key_id": integrity.key_id,
        "public_key_fingerprint": fingerprint_public_key(key.public_key),
        "error_code": None if ok else "SIGNATURE_INVALID",
    }


def load_signed_artifact(
    *,
    path: str | Path,
    config: RuntimeConfig | None = None,
    trusted_keys_dir: str | Path | None = None,
    key_manifest_path: str | Path | None = None,
) -> dict[str, Any]:
    source = Path(path)
    if not source.exists():
        return {
            "path": str(source),
            "present": False,
            "verified": False,
            "error_code": "ARTIFACT_NOT_FOUND",
        }
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {
            "path": str(source),
            "present": True,
            "verified": False,
            "error_code": "INVALID_JSON",
            "error": str(exc),
        }

    verification = verify_signed_artifact(
        path=source,
        config=config,
        trusted_keys_dir=trusted_keys_dir,
        key_manifest_path=key_manifest_path,
    )
    if not isinstance(payload, dict):
        payload = {}
    return {
        **verification,
        "present": True,
        "artifact": payload.get("artifact"),
        "status": payload.get("status"),
        "generated_at": payload.get("generated_at"),
        "data": payload.get("data"),
    }


def key_status(config: RuntimeConfig) -> dict[str, Any]:
    trusted = _load_trusted_keys(config=config)
    current_key_id = str(config.keys.current_key_id or "").strip() or None
    manifest_path = Path(config.keys.key_manifest_path)
    private_path = Path(config.keys.private_key_path)
    return {
        "provider": config.keys.provider,
        "current_key_id": current_key_id,
        "private_key_path": str(private_path),
        "private_key_present": private_path.exists(),
        "trusted_keys_dir": config.keys.trusted_public_keys_dir,
        "trusted_key_count": len(trusted),
        "trusted_keys": sorted(trusted),
        "key_manifest_path": str(manifest_path),
        "key_manifest_present": manifest_path.exists(),
        "compat_env_hmac_enabled": bool(config.keys.allow_env_hmac_compat),
        "enterprise_compatible": config.keys.provider in {"local_file", "managed_kms"},
        "pkcs11_status": "planned" if config.keys.provider == "pkcs11_hsm" else "n/a",
    }


def rotate_plan(
    config: RuntimeConfig,
    *,
    next_key_id: str | None = None,
    activate_at: str | None = None,
    retire_after: str | None = None,
) -> dict[str, Any]:
    status = key_status(config)
    next_id = next_key_id or f"{status.get('current_key_id') or 'new-key'}-next"
    return {
        "provider": config.keys.provider,
        "current_key_id": status.get("current_key_id"),
        "next_key_id": next_id,
        "steps": [
            "prepare",
            "dual-verify",
            "activate",
            "retire-old",
        ],
        "activate_at": activate_at,
        "retire_after": retire_after,
        "enterprise_ready": config.keys.provider in {"local_file", "managed_kms"},
    }


def fingerprint_public_key(public_key_b64: str) -> str:
    try:
        raw = base64.b64decode(public_key_b64)
    except Exception:  # noqa: BLE001
        raw = public_key_b64.encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _sign_hash(*, hash_value: str, config: RuntimeConfig, purpose: str) -> dict[str, str] | None:
    provider = config.keys.provider
    if provider == "local_file":
        key = _load_private_key(Path(config.keys.private_key_path))
        signature = _sign_with_private_key(hash_value, key)
        return {
            "signature": signature,
            "signature_mode": "ed25519_local_file",
            "key_id": key.key_id,
            "public_key_fingerprint": fingerprint_public_key(key.public_key),
            "purpose": purpose,
        }
    if provider == "managed_kms":
        command = list(config.keys.managed_signer_command)
        if not command:
            raise RuntimeError("managed_kms provider configured without managed_signer_command")
        proc = subprocess.run(
            command,
            input=json.dumps(
                {
                    "hash": hash_value,
                    "purpose": purpose,
                    "key_id": config.keys.current_key_id,
                }
            ),
            text=True,
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"managed_kms signer failed: {proc.stderr.strip()}")
        payload = json.loads(proc.stdout)
        signature = str(payload.get("signature") or "")
        if not signature:
            raise RuntimeError("managed_kms signer returned no signature")
        key_id = str(payload.get("key_id") or config.keys.current_key_id or "")
        public_key = str(payload.get("public_key") or "")
        return {
            "signature": signature,
            "signature_mode": "managed_kms",
            "key_id": key_id,
            "public_key_fingerprint": fingerprint_public_key(public_key) if public_key else "",
            "purpose": purpose,
        }
    if provider == "env_hmac" or (
        provider == "disabled"
        and config.keys.allow_env_hmac_compat
        and os.getenv("IMPERAOS_AUDIT_SIGNING_KEY", "").strip()
    ):
        key = os.getenv("IMPERAOS_AUDIT_SIGNING_KEY", "").strip()
        if not key:
            return None
        digest = hashlib.sha256((key + hash_value).encode("utf-8")).hexdigest()
        return {
            "signature": digest,
            "signature_mode": "env_hmac_compat",
            "key_id": "env-hmac",
            "public_key_fingerprint": hashlib.sha256(key.encode("utf-8")).hexdigest(),
            "purpose": purpose,
        }
    return None


def _load_private_key(path: Path) -> PrivateKeyMaterial:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return PrivateKeyMaterial.model_validate(payload)


def _load_trusted_keys(
    *,
    config: RuntimeConfig | None = None,
    trusted_keys_dir: str | Path | None = None,
    key_manifest_path: str | Path | None = None,
) -> dict[str, TrustedKey]:
    resolved_dir = Path(
        trusted_keys_dir
        or (
            config.keys.trusted_public_keys_dir
            if config is not None
            else enterprise_state_path("keys", "trusted")
        )
    )
    resolved_manifest = Path(
        key_manifest_path
        or (
            config.keys.key_manifest_path
            if config is not None
            else enterprise_state_path("keys", "manifest.json")
        )
    )
    revoked: set[str] = set()
    if resolved_manifest.exists():
        manifest = json.loads(resolved_manifest.read_text(encoding="utf-8"))
        revoked = {str(item) for item in manifest.get("revoked_keys", [])}
    keys: dict[str, TrustedKey] = {}
    if not resolved_dir.exists():
        return keys
    for item in sorted(resolved_dir.glob("*.json")):
        payload = json.loads(item.read_text(encoding="utf-8"))
        trusted = TrustedKey.model_validate(payload)
        if trusted.key_id in revoked or trusted.state == "revoked":
            continue
        keys[trusted.key_id] = trusted
    return keys


def _sign_with_private_key(hash_value: str, key: PrivateKeyMaterial) -> str:
    raw_private = base64.b64decode(key.private_key)
    signer = Ed25519PrivateKey.from_private_bytes(raw_private)
    signature = signer.sign(hash_value.encode("utf-8"))
    return base64.b64encode(signature).decode("ascii")


def _verify_signature(hash_value: str, signature_b64: str, key: TrustedKey) -> bool:
    try:
        verifier = Ed25519PublicKey.from_public_bytes(base64.b64decode(key.public_key))
        verifier.verify(base64.b64decode(signature_b64), hash_value.encode("utf-8"))
        return True
    except Exception:  # noqa: BLE001
        return False


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        encoded = value.isoformat()
        if encoded.endswith("+00:00"):
            return encoded.replace("+00:00", "Z")
        return encoded
    return str(value)
