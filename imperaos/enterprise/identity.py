from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from imperaos.enterprise.signing import TrustedKey, canonical_payload_hash
from imperaos.runtime.config import RuntimeConfig

_ARTIFACT_ALL_PERMISSIONS = {
    "artifact.read",
    "artifact.create",
    "artifact.update",
    "artifact.restore",
    "artifact.archive",
    "artifact.duplicate",
    "artifact.export",
    "artifact.asset.import",
    "artifact.import_evidence",
    "artifact.form.submit",
    "artifact.ai.propose",
    "artifact.ai.apply",
}

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "platform_admin": {
        "agent.registry.write",
        "evidence.verify",
        "runtime.run",
        "runtime.resume",
        "runtime.disable",
        "config.read",
        "config.write",
        "maintenance.enter",
        "backup.create",
        "restore.verify",
        "support.export",
        "artifact.read",
        "artifact.create",
        "artifact.update",
        "artifact.restore",
        "artifact.archive",
        "artifact.duplicate",
        "artifact.export",
        "artifact.asset.import",
        "artifact.import_evidence",
        "artifact.form.submit",
        "artifact.ai.propose",
        "artifact.ai.apply",
    },
    "security_admin": {
        "approval.reconcile",
        "evidence.verify",
        "approval.decide",
        "approval.execute",
        "audit.read",
        "audit.export",
        "replay.verify",
        "keys.read",
        "keys.rotate",
        "support.export",
        "config.read",
    },
    "policy_admin": {
        "policy.read",
        "policy.write",
        "policy.publish",
        "config.read",
    },
    "operator": {
        "runtime.run",
        "runtime.resume",
        "audit.read",
        "replay.verify",
        "config.read",
        "artifact.read",
        "artifact.create",
        "artifact.update",
        "artifact.restore",
        "artifact.archive",
        "artifact.duplicate",
        "artifact.export",
        "artifact.asset.import",
        "artifact.import_evidence",
        "artifact.form.submit",
        "artifact.ai.propose",
    },
    "auditor": {
        "audit.read",
        "audit.export",
        "replay.verify",
        "config.read",
        "artifact.read",
    },
    "observer": {"config.read", "audit.read", "artifact.read"},
    "artifact_admin": set(_ARTIFACT_ALL_PERMISSIONS),
    "artifact_editor": {
        "artifact.read",
        "artifact.create",
        "artifact.update",
        "artifact.restore",
        "artifact.duplicate",
        "artifact.export",
        "artifact.asset.import",
        "artifact.import_evidence",
        "artifact.form.submit",
        "artifact.ai.propose",
    },
    "artifact_viewer": {"artifact.read"},
}


class IdentityAssertion(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=False)

    schema_version: str = "1"
    assertion_type: str = "external"
    actor_id: str
    subject: str
    issuer: str
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    issued_at: datetime
    expires_at: datetime
    key_id: str
    signature: str


class ActorContext(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    actor_id: str
    subject: str
    issuer: str
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    auth_mode: str
    assertion_path: str
    key_id: str
    expires_at: datetime
    is_break_glass: bool = False


class IdentityResolutionError(RuntimeError):
    def __init__(self, error_code: str, message: str):
        super().__init__(message)
        self.error_code = error_code


def resolve_actor_context(
    config: RuntimeConfig,
    *,
    env: dict[str, str] | None = None,
) -> ActorContext | None:
    env_map = env or dict(os.environ)
    if not config.identity.enabled:
        return None

    paths = []
    assertion_path = env_map.get("IMPERAOS_IDENTITY_ASSERTION_PATH")
    if assertion_path:
        paths.append((Path(assertion_path), False))
    configured = str(config.identity.assertion_path).strip()
    if configured:
        candidate = Path(configured)
        if candidate.exists():
            paths.append((candidate, False))
    if config.identity.allow_break_glass:
        break_glass_env = env_map.get("IMPERAOS_BREAK_GLASS_ASSERTION_PATH")
        if break_glass_env:
            paths.append((Path(break_glass_env), True))
        break_glass_path = Path(config.identity.break_glass_assertion_path)
        if break_glass_path.exists():
            paths.append((break_glass_path, True))

    errors: list[str] = []
    for path, is_break_glass in paths:
        try:
            return _load_assertion(path, config=config, is_break_glass=is_break_glass)
        except IdentityResolutionError as exc:
            errors.append(f"{path.name}:{exc.error_code}")
            continue
    if errors:
        raise IdentityResolutionError("IDENTITY_INVALID", "; ".join(errors))
    raise IdentityResolutionError(
        "IDENTITY_REQUIRED",
        "no verified identity assertion available",
    )


def require_permission(
    config: RuntimeConfig,
    *,
    permission: str,
    env: dict[str, str] | None = None,
) -> ActorContext | None:
    if not _permission_enforced(config):
        return None
    actor = resolve_actor_context(config, env=env)
    permissions = set(actor.permissions)
    if permission not in permissions:
        raise IdentityResolutionError(
            "RBAC_DENY",
            f"actor '{actor.actor_id}' lacks permission '{permission}'",
        )
    return actor


def describe_actor(config: RuntimeConfig, *, env: dict[str, str] | None = None) -> dict[str, Any]:
    try:
        actor = resolve_actor_context(config, env=env)
    except IdentityResolutionError as exc:
        return {
            "identity_enabled": config.identity.enabled,
            "verified": False,
            "error_code": exc.error_code,
            "error": str(exc),
        }
    return {
        "identity_enabled": config.identity.enabled,
        "verified": True,
        "actor": actor.model_dump(mode="json"),
    }


def check_permission(
    config: RuntimeConfig,
    *,
    permission: str,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    try:
        actor = require_permission(config, permission=permission, env=env)
    except IdentityResolutionError as exc:
        return {
            "permission": permission,
            "allowed": False,
            "error_code": exc.error_code,
            "error": str(exc),
        }
    return {
        "permission": permission,
        "allowed": True,
        "actor": actor.model_dump(mode="json") if actor else None,
    }


def _load_assertion(path: Path, *, config: RuntimeConfig, is_break_glass: bool) -> ActorContext:
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_payload = dict(payload)
    signature = str(raw_payload.pop("signature", ""))
    assertion = IdentityAssertion.model_validate(payload)
    key = _trusted_key(config, assertion.key_id)
    expected_hash = canonical_payload_hash(raw_payload)
    from imperaos.enterprise.signing import _verify_signature  # noqa: PLC0415

    if not _verify_signature(expected_hash, signature or assertion.signature, key):
        raise IdentityResolutionError("IDENTITY_SIGNATURE_INVALID", "assertion signature invalid")
    now = datetime.now(UTC)
    skew = timedelta(seconds=config.identity.max_clock_skew_seconds)
    if assertion.issued_at - skew > now:
        raise IdentityResolutionError("IDENTITY_NOT_YET_VALID", "assertion not yet valid")
    if assertion.expires_at + skew < now:
        raise IdentityResolutionError("IDENTITY_EXPIRED", "assertion expired")

    permissions = sorted(_permissions_for_roles(assertion.roles) | set(assertion.permissions))
    return ActorContext(
        actor_id=assertion.actor_id,
        subject=assertion.subject,
        issuer=assertion.issuer,
        roles=sorted(set(assertion.roles)),
        permissions=permissions,
        auth_mode="break_glass" if is_break_glass else "external_assertion",
        assertion_path=str(path),
        key_id=assertion.key_id,
        expires_at=assertion.expires_at,
        is_break_glass=is_break_glass,
    )


def _trusted_key(config: RuntimeConfig, key_id: str) -> TrustedKey:
    from imperaos.enterprise.signing import _load_trusted_keys  # noqa: PLC0415

    trusted = _load_trusted_keys(config=config)
    key = trusted.get(key_id)
    if key is None:
        raise IdentityResolutionError("TRUSTED_KEY_NOT_FOUND", f"unknown key_id '{key_id}'")
    return key


def _permissions_for_roles(roles: list[str]) -> set[str]:
    resolved: set[str] = set()
    for role in roles:
        resolved.update(ROLE_PERMISSIONS.get(role, set()))
    return resolved


def _permission_enforced(config: RuntimeConfig) -> bool:
    return config.identity.enabled and (
        config.profile_name == "enterprise" or config.identity.required_for_mutations
    )
