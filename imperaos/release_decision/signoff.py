from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from imperaos.release_decision.models import (
    HumanSignoffRecord,
    HumanSignoffVerificationReport,
    SignoffRole,
)

DEFAULT_REQUIRED_ROLES: list[SignoffRole] = ["release_owner", "security_operator"]
REQUIRED_BOUNDARIES = ["NO_PUBLIC_DESKTOP_RELEASE", "NO_LIVE_COMPUTER_USE"]


def build_signoff_template(*, dossier_hash: str, role: SignoffRole) -> HumanSignoffRecord:
    return HumanSignoffRecord(
        signoffId=f"{role}-template",
        role=role,
        operatorDisplayNameHash="0" * 64,
        dossierSha256=dossier_hash,
        acceptedBoundaries=REQUIRED_BOUNDARIES,
        signedAtUtc=datetime.now(UTC),
    )


def write_signoff_template(
    *,
    dossier_hash: str,
    role: SignoffRole,
    output: Path,
) -> HumanSignoffRecord:
    record = build_signoff_template(dossier_hash=dossier_hash, role=role)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(record.model_dump(mode="json", by_alias=True), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return record


def verify_human_signoffs(
    *,
    dossier_hash: str,
    signoff_root: Path,
    required_roles: list[SignoffRole] | None = None,
) -> HumanSignoffVerificationReport:
    roles = required_roles or DEFAULT_REQUIRED_ROLES
    if not signoff_root.exists():
        return HumanSignoffVerificationReport(
            status="missing",
            requiredRoles=list(roles),
            missingRoles=list(roles),
        )
    verified: list[str] = []
    blocking: list[str] = []
    seen: set[str] = set()
    now = datetime.now(UTC)
    for path in sorted(signoff_root.glob("*.json")):
        if path.name.endswith(".template.json"):
            continue
        try:
            record = HumanSignoffRecord.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception:
            blocking.append(f"INVALID_SIGNOFF:{path.name}")
            continue
        if record.role in seen:
            blocking.append(f"DUPLICATE_ROLE:{record.role}")
        seen.add(record.role)
        if record.role not in roles:
            blocking.append(f"UNEXPECTED_ROLE:{record.role}")
        if record.dossier_sha256 != dossier_hash:
            blocking.append("STALE_DOSSIER_HASH")
        if record.operator_display_name_hash == "0" * 64:
            blocking.append(f"PLACEHOLDER_OPERATOR_HASH:{record.role}")
        if record.signed_at_utc > now:
            blocking.append(f"FUTURE_SIGNOFF_TIMESTAMP:{record.role}")
        missing_boundaries = sorted(set(REQUIRED_BOUNDARIES) - set(record.accepted_boundaries))
        if missing_boundaries:
            blocking.append(f"MISSING_ACCEPTED_BOUNDARIES:{record.role}")
        if not blocking:
            verified.append(record.role)
    missing = sorted(set(roles) - seen)
    status = "verified" if not missing and not blocking else "blocked" if blocking else "partial"
    if missing and not seen:
        status = "missing"
    return HumanSignoffVerificationReport(
        status=status,
        requiredRoles=list(roles),
        verifiedRoles=sorted(set(verified)),
        missingRoles=missing,
        blockingReasons=sorted(set(blocking)),
    )
