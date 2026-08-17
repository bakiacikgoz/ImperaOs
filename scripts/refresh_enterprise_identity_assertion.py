from __future__ import annotations

import argparse
import base64
import json
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from imperaos.enterprise.signing import canonical_payload_hash
from imperaos.runtime.paths import enterprise_state_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Refresh the local enterprise identity assertion without rotating "
            "the existing signing key."
        )
    )
    parser.add_argument("--root", default=".", help="Workspace root for .imperaos assets")
    parser.add_argument(
        "--assertion-name",
        default="current_assertion.json",
        help="Assertion filename under .imperaos/enterprise/identity",
    )
    parser.add_argument(
        "--valid-hours",
        type=float,
        default=30.0,
        help="Validity duration for the refreshed assertion",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the refreshed assertion summary without writing files",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Do not create a timestamped backup before writing",
    )
    args = parser.parse_args()

    if args.valid_hours <= 0:
        raise SystemExit("--valid-hours must be greater than zero")

    root = Path(args.root).resolve()
    private_key_path = root / enterprise_state_path("keys", "private", "current_key.json")
    assertion_path = root / enterprise_state_path("identity", args.assertion_name)
    if not private_key_path.exists():
        raise SystemExit(f"private key fixture not found: {private_key_path}")
    if not assertion_path.exists():
        raise SystemExit(f"identity assertion not found: {assertion_path}")

    private_payload = _read_json(private_key_path)
    assertion_payload = _read_json(assertion_path)
    key_id = str(private_payload.get("key_id") or "").strip()
    private_key_b64 = str(private_payload.get("private_key") or "").strip()
    if not key_id or not private_key_b64:
        raise SystemExit("private key fixture is missing key_id or private_key")

    now = datetime.now(UTC)
    refreshed = {
        "schema_version": assertion_payload.get("schema_version", "1"),
        "assertion_type": assertion_payload.get("assertion_type", "external"),
        "actor_id": assertion_payload["actor_id"],
        "subject": assertion_payload["subject"],
        "issuer": assertion_payload["issuer"],
        "roles": sorted(set(_string_list(assertion_payload.get("roles")))),
        "permissions": sorted(set(_string_list(assertion_payload.get("permissions")))),
        "issued_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=args.valid_hours)).isoformat(),
        "key_id": key_id,
    }
    private_key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(private_key_b64))
    signature = private_key.sign(canonical_payload_hash(refreshed).encode("utf-8"))
    refreshed["signature"] = base64.b64encode(signature).decode("ascii")

    backup_path = None
    if not args.dry_run:
        assertion_path.parent.mkdir(parents=True, exist_ok=True)
        if not args.no_backup:
            backup_path = assertion_path.with_name(
                f"{assertion_path.name}.bak-{now.strftime('%Y%m%dT%H%M%SZ')}"
            )
            shutil.copy2(assertion_path, backup_path)
        assertion_path.write_text(
            json.dumps(refreshed, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    print(
        json.dumps(
            {
                "root": str(root),
                "assertion_path": str(assertion_path),
                "backup_path": str(backup_path) if backup_path else None,
                "dry_run": args.dry_run,
                "key_id": key_id,
                "actor_id": refreshed["actor_id"],
                "issued_at": refreshed["issued_at"],
                "expires_at": refreshed["expires_at"],
                "valid_hours": args.valid_hours,
                "permissions": refreshed["permissions"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"expected JSON object: {path}")
    return payload


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


if __name__ == "__main__":
    main()
