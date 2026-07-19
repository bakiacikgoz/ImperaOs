from __future__ import annotations

import argparse
import base64
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from imperaos.enterprise.signing import canonical_payload_hash
from imperaos.runtime.paths import enterprise_state_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepare enterprise signing and identity fixtures."
    )
    parser.add_argument("--root", default=".", help="Workspace root for .imperaos assets")
    parser.add_argument("--actor-id", default="enterprise-admin", help="Actor id")
    parser.add_argument("--subject", default="enterprise-admin@example.local", help="Subject")
    parser.add_argument("--issuer", default="idp.local", help="Assertion issuer")
    parser.add_argument(
        "--assertion-name",
        default="current_assertion.json",
        help="Assertion filename",
    )
    parser.add_argument("--key-id", default="enterprise-signing-current", help="Signing key id")
    parser.add_argument(
        "--role",
        action="append",
        default=["platform_admin", "security_admin"],
        help="Role to include in the identity assertion",
    )
    parser.add_argument(
        "--permission",
        action="append",
        default=[
            "runtime.run",
            "runtime.resume",
            "approval.decide",
            "approval.execute",
            "backup.create",
            "restore.verify",
            "support.export",
            "maintenance.enter",
        ],
        help="Explicit permission to include in the identity assertion",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    keys_root = root / enterprise_state_path("keys")
    private_dir = keys_root / "private"
    trusted_dir = keys_root / "trusted"
    identity_dir = root / enterprise_state_path("identity")
    private_dir.mkdir(parents=True, exist_ok=True)
    trusted_dir.mkdir(parents=True, exist_ok=True)
    identity_dir.mkdir(parents=True, exist_ok=True)

    private_seed = hashlib.sha256(
        f"imperaos-enterprise-fixture:{args.key_id}".encode()
    ).digest()
    private_key = Ed25519PrivateKey.from_private_bytes(private_seed)
    private_raw = private_key.private_bytes_raw()
    public_raw = private_key.public_key().public_bytes_raw()
    now = datetime.now(UTC)

    private_payload = {
        "schema_version": "1",
        "key_id": args.key_id,
        "algorithm": "ed25519",
        "purpose": "artifact-signing",
        "private_key": base64.b64encode(private_raw).decode("ascii"),
        "public_key": base64.b64encode(public_raw).decode("ascii"),
        "created_at": now.isoformat(),
    }
    public_payload = {
        "schema_version": "1",
        "key_id": args.key_id,
        "algorithm": "ed25519",
        "purpose": "artifact-signing",
        "public_key": base64.b64encode(public_raw).decode("ascii"),
        "state": "active",
        "created_at": now.isoformat(),
    }
    manifest_payload = {
        "schema_version": "1",
        "current_key_id": args.key_id,
        "revoked_keys": [],
    }
    assertion_payload = {
        "schema_version": "1",
        "assertion_type": "external",
        "actor_id": args.actor_id,
        "subject": args.subject,
        "issuer": args.issuer,
        "roles": sorted(set(args.role)),
        "permissions": sorted(set(args.permission)),
        "issued_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=8)).isoformat(),
        "key_id": args.key_id,
    }
    signature = private_key.sign(canonical_payload_hash(assertion_payload).encode("utf-8"))
    assertion_payload["signature"] = base64.b64encode(signature).decode("ascii")

    (private_dir / "current_key.json").write_text(
        json.dumps(private_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (trusted_dir / f"{args.key_id}.json").write_text(
        json.dumps(public_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (keys_root / "manifest.json").write_text(
        json.dumps(manifest_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (identity_dir / args.assertion_name).write_text(
        json.dumps(assertion_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "root": str(root),
                "key_id": args.key_id,
                "assertion_path": str(identity_dir / args.assertion_name),
                "roles": sorted(set(args.role)),
                "permissions": sorted(set(args.permission)),
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
