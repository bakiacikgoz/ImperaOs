from __future__ import annotations

import hashlib
import json
from typing import Any

from imperaos.computer_use.models import PerceptionSnapshot, ProposedAction


def device_action_hash(*, action: ProposedAction, policy_hash: str) -> str:
    payload = {
        "action_id": action.action_id,
        "category": action.category.value,
        "risk_class": action.risk_class.value,
        "target_ref": action.target_descriptor.target_ref,
        "window_identity": action.window_identity,
        "app_identity": action.app_identity,
        "selector_source": action.selector_source,
        "expected_effect": action.expected_effect,
        "policy_hash": policy_hash,
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def approval_snapshot_payload(
    *,
    action: ProposedAction,
    perception: PerceptionSnapshot,
    policy_hash: str,
) -> dict[str, Any]:
    action_hash = device_action_hash(action=action, policy_hash=policy_hash)
    return {
        "action_id": action.action_id,
        "category": action.category.value,
        "risk_class": action.risk_class.value,
        "target_ref": action.target_descriptor.target_ref,
        "window_or_tab_identity": perception.window_or_tab_identity,
        "window_identity": action.window_identity,
        "app_identity": action.app_identity,
        "selector_source": action.selector_source,
        "selector_context": perception.selector_context.model_dump(mode="json"),
        "perception_fingerprint": perception.perception_fingerprint,
        "action_plan": {
            "expected_effect": action.expected_effect,
            "dry_run_preview": action.dry_run_preview,
        },
        "execution_contract": {
            "action_hash": action_hash,
            "window_identity": action.window_identity,
            "app_identity": action.app_identity,
            "selector_context": perception.selector_context.model_dump(mode="json"),
            "perception_fingerprint": perception.perception_fingerprint,
            "policy_hash": policy_hash,
        },
    }
