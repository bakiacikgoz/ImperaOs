from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from imperaos.control_plane.models import ActionProposal
from imperaos.control_plane.policy_simulator import PolicySimulator


def evaluate_action_proposal_file(
    *,
    path: str | Path,
    simulator: PolicySimulator,
) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(payload, dict) and payload.get("type") == "action_proposal":
            payload = payload.get("payload")
        proposal = ActionProposal.model_validate(payload)
    except (json.JSONDecodeError, OSError, ValidationError) as exc:
        return {
            "type": "policy_decision",
            "payload": {
                "decision_action": "deny",
                "reason_code": "ADAPTER_CONTRACT_INVALID",
                "policy_hash": "unavailable",
                "error": str(exc),
            },
        }
    decision = simulator.simulate_action(proposal)
    return {
        "type": "policy_decision",
        "payload": decision.model_dump(mode="json"),
    }
