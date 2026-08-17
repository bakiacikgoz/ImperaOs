from __future__ import annotations

from dataclasses import dataclass

from imperaos.model_providers.errors import REASON_CODES
from imperaos.model_providers.models import (
    DataBoundary,
    DataClass,
    ModelProviderRecord,
    ProviderCallRequest,
    ProviderDecisionStatus,
    ProviderPolicy,
    ProviderPolicyDecision,
)


@dataclass(frozen=True, slots=True)
class GovernanceContext:
    remote_providers_enabled: bool = False
    fallback_provider_id: str | None = None


BLOCKED_DATA_CLASSES = {
    DataClass.SECRET,
    DataClass.CREDENTIAL,
    DataClass.PAYMENT,
    DataClass.RAW_PII,
}


def evaluate_provider_policy(
    *,
    request: ProviderCallRequest,
    provider: ModelProviderRecord,
    policy: ProviderPolicy,
    governance_context: GovernanceContext | None = None,
) -> ProviderPolicyDecision:
    context = governance_context or GovernanceContext()
    data_classes = list(dict.fromkeys(request.data_classes or [DataClass.PUBLIC]))

    hard_blocked = BLOCKED_DATA_CLASSES
    if any(item in hard_blocked for item in data_classes):
        return _decision(
            status=ProviderDecisionStatus.DENY,
            reason_code="PROVIDER_BLOCKED_DATA_CLASS",
            provider_id=provider.provider_id,
            data_classes=data_classes,
            redaction_required=True,
            evidence_required=policy.evidence_required,
            user_message="Request contains data that cannot be sent to model providers.",
        )

    allowed = set(policy.allowed_data_classes)
    if not allowed:
        allowed = {DataClass.PUBLIC} if provider.data_boundary != DataBoundary.LOCAL else {
            DataClass.PUBLIC,
            DataClass.INTERNAL,
            DataClass.CONFIDENTIAL,
            DataClass.REGULATED,
            DataClass.PII_REDACTED,
        }
    denied_classes = [item for item in data_classes if item not in allowed]
    denied_classes.extend(
        item for item in data_classes if item in set(policy.blocked_data_classes) - hard_blocked
    )
    if denied_classes:
        return _decision(
            status=ProviderDecisionStatus.DENY,
            reason_code="PROVIDER_DATA_BOUNDARY_DENIED",
            provider_id=provider.provider_id,
            data_classes=data_classes,
            redaction_required=policy.requires_redaction,
            evidence_required=policy.evidence_required,
            user_message="Provider cannot receive the requested data classes under current policy.",
            internal_detail=(
                f"denied_data_classes={','.join(sorted(str(item) for item in denied_classes))}"
            ),
        )

    if not provider.enabled:
        return _decision(
            status=ProviderDecisionStatus.BLOCKED_NOT_CONFIGURED,
            reason_code="PROVIDER_DISABLED",
            provider_id=provider.provider_id,
            data_classes=data_classes,
            redaction_required=policy.requires_redaction,
            evidence_required=policy.evidence_required,
            user_message="Provider is disabled in the current registry.",
        )

    if provider.data_boundary != DataBoundary.LOCAL and not context.remote_providers_enabled:
        return _decision(
            status=ProviderDecisionStatus.DENY,
            reason_code="PROVIDER_REMOTE_DISABLED",
            provider_id=provider.provider_id,
            data_classes=data_classes,
            redaction_required=policy.requires_redaction,
            evidence_required=policy.evidence_required,
            user_message="Remote model providers are disabled by default.",
        )

    if request.stream and (not provider.supports_streaming or not policy.allow_streaming):
        return _decision(
            status=ProviderDecisionStatus.DENY,
            reason_code="PROVIDER_UNSUPPORTED_CAPABILITY",
            provider_id=provider.provider_id,
            data_classes=data_classes,
            redaction_required=policy.requires_redaction,
            evidence_required=policy.evidence_required,
            user_message="Provider streaming is not allowed by capability or policy.",
        )

    if request.json_schema and not provider.supports_json_schema:
        return _decision(
            status=ProviderDecisionStatus.DENY,
            reason_code="PROVIDER_UNSUPPORTED_CAPABILITY",
            provider_id=provider.provider_id,
            data_classes=data_classes,
            redaction_required=policy.requires_redaction,
            evidence_required=policy.evidence_required,
            user_message="Provider does not support JSON schema output.",
        )

    if request.json_mode and not provider.supports_json_mode:
        return _decision(
            status=ProviderDecisionStatus.DENY,
            reason_code="PROVIDER_UNSUPPORTED_CAPABILITY",
            provider_id=provider.provider_id,
            data_classes=data_classes,
            redaction_required=policy.requires_redaction,
            evidence_required=policy.evidence_required,
            user_message="Provider does not support JSON mode.",
        )

    approval_required = bool(request.tools and policy.requires_approval_for_tool_calls)
    if request.tools and not policy.allow_tool_calls:
        return _decision(
            status=ProviderDecisionStatus.REQUIRE_APPROVAL,
            reason_code="PROVIDER_TOOL_CALL_APPROVAL_REQUIRED",
            provider_id=provider.provider_id,
            data_classes=data_classes,
            redaction_required=policy.requires_redaction,
            approval_required=True,
            evidence_required=policy.evidence_required,
            safe_to_call_provider=False,
            user_message="Tool calls are proposal-only and require governance approval.",
        )

    if (
        context.fallback_provider_id
        and context.fallback_provider_id not in policy.fallback_allowed_to
    ):
        return _decision(
            status=ProviderDecisionStatus.DENY,
            reason_code="PROVIDER_FALLBACK_DOWNGRADE_DENIED",
            provider_id=provider.provider_id,
            data_classes=data_classes,
            redaction_required=policy.requires_redaction,
            evidence_required=policy.evidence_required,
            user_message="Fallback is not allowed by provider policy.",
        )

    status = (
        ProviderDecisionStatus.ALLOW_WITH_REDACTION
        if policy.requires_redaction
        else ProviderDecisionStatus.ALLOW
    )
    return _decision(
        status=status,
        reason_code=(
            "PROVIDER_REDACTION_REQUIRED" if policy.requires_redaction else "PROVIDER_READY"
        ),
        provider_id=provider.provider_id,
        data_classes=data_classes,
        redaction_required=policy.requires_redaction,
        approval_required=approval_required,
        evidence_required=policy.evidence_required,
        fallback_allowed=bool(policy.fallback_allowed_to),
        safe_to_call_provider=not approval_required,
        user_message=REASON_CODES.get("PROVIDER_READY", "Provider call is allowed."),
    )


def _decision(
    *,
    status: ProviderDecisionStatus,
    reason_code: str,
    provider_id: str,
    data_classes: list[DataClass],
    redaction_required: bool,
    evidence_required: bool,
    user_message: str,
    approval_required: bool = False,
    fallback_allowed: bool = False,
    safe_to_call_provider: bool = False,
    internal_detail: str | None = None,
) -> ProviderPolicyDecision:
    return ProviderPolicyDecision(
        status=status,
        reason_code=reason_code,
        provider_id=provider_id,
        effective_data_classes=data_classes,
        redaction_required=redaction_required,
        approval_required=approval_required,
        evidence_required=evidence_required,
        fallback_allowed=fallback_allowed,
        safe_to_call_provider=safe_to_call_provider,
        user_message=user_message,
        internal_detail=internal_detail,
    )
