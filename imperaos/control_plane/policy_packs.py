from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from imperaos.control_plane.models import (
    PolicyPackDiffResult,
    PolicyPackManifest,
    PolicyPackPromotionDryRun,
    PolicyPackValidationResult,
    RiskClass,
)
from imperaos.control_plane.storage import ControlPlaneStore, canonical_json_hash
from imperaos.runtime.paths import CONTROL_PLANE_STATE_ROOT

UNSAFE_ALLOW_RISKS = {
    RiskClass.DESTRUCTIVE,
    RiskClass.CREDENTIAL_SENSITIVE,
    RiskClass.FINANCIAL_OR_LEGAL,
    RiskClass.SECURITY_SENSITIVE,
    RiskClass.COMPUTER_USE_VISUAL,
    RiskClass.UNKNOWN,
}


def load_policy_pack_manifest(path: str | Path) -> PolicyPackManifest:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return PolicyPackManifest.model_validate(payload)
    except (json.JSONDecodeError, OSError, ValidationError, ValueError) as exc:
        raise ValueError(f"invalid policy pack manifest: {exc}") from exc


def validate_policy_pack(manifest: PolicyPackManifest) -> PolicyPackValidationResult:
    blocking_reasons: list[str] = []
    warnings: list[str] = []
    rule_ids: set[str] = set()

    if manifest.default_decision != "deny":
        blocking_reasons.append("DEFAULT_DECISION_NOT_DENY")
    if not manifest.rules:
        warnings.append("POLICY_PACK_HAS_NO_RULES")
    if manifest.signed_manifest_ref is None:
        warnings.append("SIGNED_MANIFEST_MISSING")

    for rule in manifest.rules:
        if rule.rule_id in rule_ids:
            blocking_reasons.append(f"DUPLICATE_RULE:{rule.rule_id}")
        rule_ids.add(rule.rule_id)
        if rule.action == "allow" and rule.risk_class in UNSAFE_ALLOW_RISKS:
            blocking_reasons.append(f"UNSAFE_ALLOW:{rule.rule_id}")

    status = "blocked" if blocking_reasons else "conditional" if warnings else "pass"
    return PolicyPackValidationResult(
        policy_pack_id=manifest.policy_pack_id,
        policy_version=manifest.version,
        status=status,
        rule_count=len(manifest.rules),
        blocking_reasons=sorted(set(blocking_reasons)),
        warnings=sorted(set(warnings)),
    )


def diff_policy_packs(
    *,
    base: PolicyPackManifest,
    candidate: PolicyPackManifest,
) -> PolicyPackDiffResult:
    validation = validate_policy_pack(candidate)
    base_rules = {rule.rule_id: rule for rule in base.rules}
    candidate_rules = {rule.rule_id: rule for rule in candidate.rules}
    added = sorted(set(candidate_rules) - set(base_rules))
    removed = sorted(set(base_rules) - set(candidate_rules))
    changed: list[str] = []
    risk_changes: list[str] = []
    for rule_id in sorted(set(base_rules) & set(candidate_rules)):
        base_rule = base_rules[rule_id]
        candidate_rule = candidate_rules[rule_id]
        if base_rule.model_dump(mode="json") != candidate_rule.model_dump(mode="json"):
            changed.append(rule_id)
        if base_rule.risk_class != candidate_rule.risk_class:
            risk_changes.append(rule_id)

    warnings = list(validation.warnings)
    if candidate.policy_pack_id != base.policy_pack_id:
        warnings.append("POLICY_PACK_ID_CHANGED")
    status = "blocked" if validation.blocking_reasons else "conditional" if warnings else "pass"
    return PolicyPackDiffResult(
        base_policy_pack_id=base.policy_pack_id,
        candidate_policy_pack_id=candidate.policy_pack_id,
        added_rules=added,
        removed_rules=removed,
        changed_rules=changed,
        risk_changes=risk_changes,
        status=status,
        blocking_reasons=validation.blocking_reasons,
        warnings=sorted(set(warnings)),
    )


def promote_policy_pack_dry_run(
    *,
    manifest: PolicyPackManifest,
    root_dir: str | Path = CONTROL_PLANE_STATE_ROOT,
    dry_run: bool = True,
) -> PolicyPackPromotionDryRun:
    validation = validate_policy_pack(manifest)
    warnings = list(validation.warnings)
    blocking_reasons = list(validation.blocking_reasons)
    if not dry_run:
        blocking_reasons.append("EXECUTE_PROMOTION_NOT_SUPPORTED_IN_RC")
    would_promote = dry_run and validation.status == "pass"
    status = "blocked" if blocking_reasons else "conditional" if warnings else "pass"
    audit_ref = _write_promotion_audit(
        manifest=manifest,
        validation=validation,
        root_dir=root_dir,
        dry_run=dry_run,
        would_promote=would_promote,
        status=status,
        blocking_reasons=blocking_reasons,
        warnings=warnings,
    )
    return PolicyPackPromotionDryRun(
        policy_pack_id=manifest.policy_pack_id,
        policy_version=manifest.version,
        dry_run=dry_run,
        status=status,
        would_promote=would_promote,
        activation_audit_ref=audit_ref,
        validation=validation,
        blocking_reasons=sorted(set(blocking_reasons)),
        warnings=sorted(set(warnings)),
    )


def _write_promotion_audit(
    *,
    manifest: PolicyPackManifest,
    validation: PolicyPackValidationResult,
    root_dir: str | Path,
    dry_run: bool,
    would_promote: bool,
    status: str,
    blocking_reasons: list[str],
    warnings: list[str],
) -> str:
    store = ControlPlaneStore(root_dir)
    safe_version = manifest.version.replace("/", "-")
    relative_path = f"policy-packs/audit/{manifest.policy_pack_id}-{safe_version}.json"
    payload: dict[str, Any] = {
        "version": "control-plane.policy-pack-promotion-audit/v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "policy_pack_id": manifest.policy_pack_id,
        "policy_version": manifest.version,
        "dry_run": dry_run,
        "would_promote": would_promote,
        "status": status,
        "blocking_reasons": sorted(set(blocking_reasons)),
        "warnings": sorted(set(warnings)),
        "manifest_hash": canonical_json_hash(manifest.model_dump(mode="json", by_alias=True)),
        "validation": validation.model_dump(mode="json", by_alias=True),
    }
    store.write_json_atomic(relative_path, payload)
    return relative_path
