from __future__ import annotations

from imperaos.model_providers.models import (
    DataBoundary,
    ModelProviderRecord,
    ProviderCallRequest,
    ProviderRouteCandidate,
    ProviderRouteShadowDecision,
    ProviderRouteShadowRequest,
    ResolvedProviderRegistry,
)
from imperaos.model_providers.policy import GovernanceContext, evaluate_provider_policy


def recommend_provider_shadow(
    *,
    registry: ResolvedProviderRegistry,
    request: ProviderRouteShadowRequest,
) -> ProviderRouteShadowDecision:
    candidates: list[ProviderRouteCandidate] = []
    for provider in registry.providers:
        capability_reason = _capability_reason(provider, request.required_capabilities)
        if capability_reason is not None:
            candidates.append(_candidate(provider, False, capability_reason, score=-100))
            continue
        policy_decision = evaluate_provider_policy(
            request=ProviderCallRequest(
                call_id="router-shadow",
                run_id="router-shadow",
                provider_id=provider.provider_id,
                model=provider.default_model,
                data_classes=request.data_classes,
                messages=[],
            ),
            provider=provider,
            policy=registry.policy_for(provider.provider_id),
            governance_context=GovernanceContext(
                remote_providers_enabled=registry.remote_providers_enabled
            ),
        )
        allowed = policy_decision.safe_to_call_provider
        score = _score_provider(provider) if allowed else -100
        candidates.append(_candidate(provider, allowed, policy_decision.reason_code, score=score))
    allowed_candidates = sorted(
        (item for item in candidates if item.allowed),
        key=lambda item: (-item.score, item.provider_id),
    )
    recommended = allowed_candidates[0].provider_id if allowed_candidates else None
    fallback = allowed_candidates[1].provider_id if len(allowed_candidates) > 1 else None
    return ProviderRouteShadowDecision(
        task_type=request.task_type,
        data_classes=request.data_classes,
        required_capabilities=request.required_capabilities,
        requested_provider_id=request.preferred_provider_id,
        recommended_provider_id=recommended,
        fallback_provider_id=fallback,
        allowed_providers=[item.provider_id for item in allowed_candidates],
        blocked_providers=[item for item in candidates if not item.allowed],
        candidates=candidates,
        reason_code=(
            "PROVIDER_ROUTER_SHADOW_RECOMMENDED"
            if recommended
            else "PROVIDER_ROUTER_SHADOW_NO_ELIGIBLE_PROVIDER"
        ),
    )


def _candidate(
    provider: ModelProviderRecord,
    allowed: bool,
    reason_code: str,
    *,
    score: int,
) -> ProviderRouteCandidate:
    return ProviderRouteCandidate(
        provider_id=provider.provider_id,
        provider_kind=provider.kind,
        data_boundary=provider.data_boundary,
        risk_tier=provider.risk_tier or "unknown",
        allowed=allowed,
        reason_code=reason_code,
        score=score,
    )


def _capability_reason(
    provider: ModelProviderRecord,
    required_capabilities: list[str],
) -> str | None:
    capability_map = {
        "streaming": provider.supports_streaming,
        "json_mode": provider.supports_json_mode,
        "json_schema": provider.supports_json_schema,
        "tool_calling": provider.supports_tool_calling,
        "vision": provider.supports_vision,
    }
    missing = [item for item in required_capabilities if not capability_map.get(item, False)]
    return "PROVIDER_UNSUPPORTED_CAPABILITY" if missing else None


def _score_provider(provider: ModelProviderRecord) -> int:
    boundary_weight = {
        DataBoundary.LOCAL: 500,
        DataBoundary.INTERNAL: 400,
        DataBoundary.PRIVATE_CLOUD: 300,
        DataBoundary.PUBLIC_CLOUD: 100,
        DataBoundary.AGGREGATOR: 50,
        DataBoundary.UNKNOWN: 0,
    }[provider.data_boundary]
    return boundary_weight + max(0, 999 - provider.fallback_priority)
