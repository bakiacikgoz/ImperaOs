from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from imperaos.governance.models import GovernanceAction
from imperaos.governance.runtime import GovernanceRuntime


@dataclass(slots=True)
class HandoffDecisionResult:
    allowed: bool
    requires_approval: bool
    reason_code: str
    approval_id: str | None
    payload: dict[str, Any]
    payload_hash: str
    redaction_applied: bool


def evaluate_handoff_transfer(
    *,
    governance_runtime: GovernanceRuntime | None,
    run_id: str,
    from_role: str,
    to_role: str,
    payload: dict[str, Any],
    override_approval_id: str | None = None,
    execution_contract_hash: str | None = None,
    resume_token_ref: str | None = None,
) -> HandoffDecisionResult:
    payload_hash = _hash_payload(payload)
    if governance_runtime is None:
        return HandoffDecisionResult(
            allowed=True,
            requires_approval=False,
            reason_code="RULE_ROUTE",
            approval_id=None,
            payload=payload,
            payload_hash=payload_hash,
            redaction_applied=False,
        )

    redacted_payload = governance_runtime.trace_redact(payload)
    redaction_applied = redacted_payload != payload
    decision, ticket = governance_runtime.evaluate_handoff(
        run_id=run_id,
        from_role=from_role,
        to_role=to_role,
        payload=redacted_payload,
        override_approval_id=override_approval_id,
        execution_contract_hash=execution_contract_hash,
        resume_token_ref=resume_token_ref,
    )

    if decision.action == GovernanceAction.DENY:
        return HandoffDecisionResult(
            allowed=False,
            requires_approval=False,
            reason_code=decision.reason_code,
            approval_id=None,
            payload=redacted_payload,
            payload_hash=_hash_payload(redacted_payload),
            redaction_applied=redaction_applied,
        )
    if decision.action == GovernanceAction.REQUIRE_APPROVAL:
        return HandoffDecisionResult(
            allowed=False,
            requires_approval=True,
            reason_code=decision.reason_code,
            approval_id=ticket.approval_id if ticket else None,
            payload=redacted_payload,
            payload_hash=_hash_payload(redacted_payload),
            redaction_applied=redaction_applied,
        )

    return HandoffDecisionResult(
        allowed=True,
        requires_approval=False,
        reason_code=decision.reason_code,
        approval_id=decision.approval_id,
        payload=redacted_payload,
        payload_hash=_hash_payload(redacted_payload),
        redaction_applied=redaction_applied,
    )


def _hash_payload(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
