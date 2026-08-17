from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from imperaos.enterprise.signing import key_status
from imperaos.runtime.config import RuntimeConfig


def security_posture(config: RuntimeConfig) -> dict[str, Any]:
    checks: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    warnings: list[str] = []

    def record(name: str, ok: bool, detail: str) -> None:
        checks[name] = {"status": "pass" if ok else "fail", "detail": detail}
        if not ok:
            errors.append(f"{name}: {detail}")

    record("profile_enterprise", config.profile_name == "enterprise", "enterprise profile required")
    record(
        "governance_fail_closed",
        config.governance.enabled and config.governance.policy_fail_mode == "fail_closed",
        "governance must be enabled and fail-closed",
    )
    record("web_disabled", not config.web_enabled, "web access must remain disabled")
    record("debug_disabled", not config.debug_mode, "debug mode must be disabled")
    record("privacy_enabled", bool(config.privacy_mode), "privacy mode must be enabled")
    record(
        "pii_redaction_enabled",
        bool(config.governance.pii_redaction_enabled),
        "PII redaction must be enabled",
    )
    record(
        "identity_enabled",
        config.identity.enabled and config.identity.required_for_mutations,
        "verified identity must gate mutating operations",
    )
    ks = key_status(config)
    record(
        "enterprise_signing_provider",
        config.keys.provider in {"local_file", "managed_kms"},
        "enterprise profile requires asymmetric signing provider",
    )
    record(
        "private_key_present",
        bool(ks.get("private_key_present")),
        "current signing private key must be present",
    )
    record(
        "trusted_keys_present",
        int(ks.get("trusted_key_count", 0)) > 0,
        "trusted verification keys must be present",
    )
    record(
        "identity_trust_store_present",
        Path(config.identity.trusted_keys_dir).exists(),
        "identity trust store must exist",
    )
    if os.getenv("IMPERAOS_AUDIT_SIGNING_KEY", "").strip():
        warnings.append("IMPERAOS_AUDIT_SIGNING_KEY compatibility secret is set")
        if config.keys.provider in {"disabled", "env_hmac"}:
            errors.append("env HMAC compatibility mode is not allowed in enterprise profile")
            checks["env_hmac_compat"] = {
                "status": "fail",
                "detail": "enterprise artifacts must not rely on IMPERAOS_AUDIT_SIGNING_KEY",
            }
        else:
            checks["env_hmac_compat"] = {
                "status": "pass",
                "detail": "compatibility secret present but asymmetric provider is active",
            }
    else:
        checks["env_hmac_compat"] = {
            "status": "pass",
            "detail": "compatibility HMAC secret not in use",
        }

    roots = {
        "memory_db": str(Path(config.memory.db_path).resolve()),
        "approval_store": str(Path(config.governance.approval_store_path).resolve()),
        "checkpoint_store": str(Path(config.team.checkpoint_db_path).resolve()),
        "audit_dir": str(Path(config.governance.audit_dir).resolve()),
        "team_artifacts": str(Path(config.team.artifact_dir).resolve()),
        "backup_dir": str(Path(config.maintenance.backup_dir).resolve()),
    }
    root_values = list(roots.values())
    storage_ok = len(set(root_values)) == len(root_values)
    record(
        "storage_separation",
        storage_ok,
        "memory, approval, checkpoint, audit, artifact, and backup roots must be distinct",
    )
    record(
        "metrics_network_default_off",
        not config.observability.http_exporter_enabled,
        "network metrics exporter must be opt-in",
    )
    record(
        "metrics_file_snapshot_on",
        bool(config.observability.file_snapshot_enabled),
        "file-based metrics snapshot must be enabled",
    )
    record(
        "immutable_audit_expectation",
        bool(config.security.require_immutable_audit_export),
        "immutable/WORM audit export expectation must be enabled",
    )
    record(
        "allow_debug_privacy_override_disabled",
        not config.security.allow_debug_privacy_override,
        "enterprise profile must forbid debug/privacy override by default",
    )

    return {
        "profile": config.profile_name,
        "overall_status": "pass" if not errors else "fail",
        "checks": checks,
        "errors": errors,
        "warnings": warnings,
        "roots": roots,
        "key_status": ks,
        "misconfiguration_risks": [
            "identity disabled under enterprise profile",
            "env HMAC signing used for enterprise artifacts",
            "shared storage roots across environments",
            "provider credentials stored unencrypted on runtime account",
            "debug/privacy override enabled in enterprise mode",
        ],
    }


def enterprise_startup_abort(config: RuntimeConfig) -> str | None:
    if config.profile_name != "enterprise":
        return None
    posture = security_posture(config)
    if posture["overall_status"] == "pass":
        return None
    return "; ".join(str(item) for item in posture.get("errors", []))
