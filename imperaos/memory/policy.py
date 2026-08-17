from __future__ import annotations

from dataclasses import dataclass

from imperaos.governance.models import GovernanceAction
from imperaos.governance.policy import evaluate_memory_scope_write, load_policy
from imperaos.memory.models import (
    MemoryPolicyAction,
    MemoryPolicyDecision,
    MemoryRetrievalRequest,
    MemoryScope,
    MemoryVisibility,
    MemoryWriteProposal,
)
from imperaos.memory.redaction import MemoryRedactionResult
from imperaos.runtime.config import RuntimeConfig


@dataclass(slots=True)
class MemoryWritePolicyContext:
    proposal: MemoryWriteProposal
    redaction: MemoryRedactionResult
    config: RuntimeConfig


@dataclass(slots=True)
class MemoryRetrievalPolicyContext:
    request: MemoryRetrievalRequest
    config: RuntimeConfig


class MemoryPolicyEvaluator:
    def __init__(self, *, config: RuntimeConfig):
        self.config = config

    def evaluate_write(self, context: MemoryWritePolicyContext) -> MemoryPolicyDecision:
        proposal = context.proposal
        scope = str(proposal.scope)
        visibility = str(proposal.visibility)
        if context.redaction.secret_detected:
            return _decision(
                MemoryPolicyAction.DENY,
                "MEMORY_SECRET_DETECTED",
                blocking=["MEMORY_SECRET_DETECTED"],
            )
        if scope == MemoryScope.GLOBAL_READONLY.value:
            if proposal.producer_role.strip().lower() in {"system", "migration"}:
                return _decision(MemoryPolicyAction.ALLOW, "MEMORY_GLOBAL_READONLY_SYSTEM_WRITE")
            return _decision(
                MemoryPolicyAction.DENY,
                "MEMORY_SCOPE_DENIED",
                blocking=["MEMORY_SCOPE_DENIED"],
            )
        if scope == MemoryScope.ORGANIZATION.value:
            return _decision(MemoryPolicyAction.REQUIRE_APPROVAL, "MEMORY_APPROVAL_REQUIRED")
        if scope == MemoryScope.PERSONAL.value and visibility == MemoryVisibility.PRIVATE.value:
            return _decision(MemoryPolicyAction.ALLOW, "MEMORY_PERSONAL_PRIVATE_ALLOWED")
        if scope == MemoryScope.AGENT.value and visibility in {
            MemoryVisibility.PRIVATE.value,
            MemoryVisibility.AGENT.value,
        }:
            return _decision(MemoryPolicyAction.ALLOW, "MEMORY_AGENT_SCOPE_ALLOWED")

        try:
            policy = load_policy(context.config.governance.policy_path).policy
            match = evaluate_memory_scope_write(
                policy,
                scope=scope,
                producer_role=proposal.producer_role,
                visibility=visibility,
            )
        except Exception:
            return _decision(
                MemoryPolicyAction.DENY,
                "MEMORY_POLICY_UNAVAILABLE",
                blocking=["MEMORY_POLICY_UNAVAILABLE"],
            )

        if match.action == GovernanceAction.ALLOW:
            return _decision(
                MemoryPolicyAction.ALLOW,
                match.reason_code,
                matched=match.matched_rule_path,
            )
        if match.action == GovernanceAction.REQUIRE_APPROVAL:
            return _decision(
                MemoryPolicyAction.REQUIRE_APPROVAL,
                "MEMORY_APPROVAL_REQUIRED",
                matched=match.matched_rule_path,
            )
        return _decision(
            MemoryPolicyAction.DENY,
            "MEMORY_POLICY_DENY",
            matched=match.matched_rule_path,
            blocking=["MEMORY_POLICY_DENY"],
        )

    def evaluate_retrieval(self, context: MemoryRetrievalPolicyContext) -> MemoryPolicyDecision:
        request = context.request
        allowed = {str(item) for item in request.allowed_scopes}
        requested = {str(item.scope) for item in request.scope_filters}
        if not requested:
            requested = allowed
        denied = sorted(requested - allowed)
        if denied:
            return _decision(
                MemoryPolicyAction.DENY,
                "MEMORY_SCOPE_DENIED",
                blocking=["MEMORY_SCOPE_DENIED", *denied],
            )
        visibility_filters = {str(item) for item in request.visibility_filters}
        if (
            MemoryVisibility.ORGANIZATION.value in visibility_filters
            and "admin" not in request.requester_role.lower()
        ):
            return _decision(
                MemoryPolicyAction.DENY,
                "MEMORY_SCOPE_VISIBILITY_DENIED",
                blocking=["MEMORY_SCOPE_VISIBILITY_DENIED"],
            )
        return _decision(MemoryPolicyAction.ALLOW, "MEMORY_RETRIEVAL_ALLOWED")


def _decision(
    action: MemoryPolicyAction,
    reason: str,
    *,
    matched: str | None = None,
    blocking: list[str] | None = None,
) -> MemoryPolicyDecision:
    return MemoryPolicyDecision(
        decision=action,
        reasonCode=reason,
        matchedRulePath=matched,
        blockingReasons=blocking or [],
    )
