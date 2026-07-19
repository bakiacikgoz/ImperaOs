from __future__ import annotations

from pathlib import Path

from imperaos.control_plane.models import ReadinessReport
from imperaos.enterprise.identity import describe_actor
from imperaos.runtime.config import RuntimeConfig
from imperaos.runtime.paths import CONTROL_PLANE_STATE_ROOT


def build_readiness_report(config: RuntimeConfig) -> ReadinessReport:
    checks = {
        "policy_available": Path(config.governance.policy_path).exists(),
        "registry_available": Path(CONTROL_PLANE_STATE_ROOT).exists(),
        "evidence_export_available": True,
        "claim_guard_available": True,
        "signing_configured": config.keys.provider != "disabled",
        "privacy_default": config.privacy_mode,
        "computer_use_raw_screenshots_off": not config.computer_use.raw_screenshot_persistence,
    }
    actor = describe_actor(config)
    checks["identity_available"] = (
        not config.identity.enabled or bool(actor.get("verified", False))
    )
    reason_codes = {
        "policy_available": "POLICY_UNAVAILABLE",
        "registry_available": "REGISTRY_UNAVAILABLE",
        "evidence_export_available": "EVIDENCE_EXPORT_UNAVAILABLE",
        "claim_guard_available": "CLAIM_GUARD_UNAVAILABLE",
        "signing_configured": "SIGNING_UNAVAILABLE",
        "privacy_default": "PRIVACY_MODE_DISABLED",
        "computer_use_raw_screenshots_off": "RAW_SCREENSHOT_PERSISTED",
        "identity_available": "IDENTITY_UNAVAILABLE",
    }
    blocking = [reason_codes.get(key, key.upper()) for key, ok in checks.items() if not ok]
    status = "pass" if not blocking else "blocked"
    return ReadinessReport(
        profile=config.profile_name,
        status=status,
        checks=checks,
        blocking_reasons=blocking,
    )
