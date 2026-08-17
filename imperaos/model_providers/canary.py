from __future__ import annotations

import os
import time
from datetime import UTC, datetime
from pathlib import Path

from imperaos.model_providers.adapters.adapter_factory import ProviderAdapterFactory
from imperaos.model_providers.budget import evaluate_provider_budget
from imperaos.model_providers.canary_evidence import write_canary_evidence
from imperaos.model_providers.models import (
    ChatMessage,
    DataBoundary,
    ModelProviderRecord,
    ProviderCallRequest,
    ProviderCanaryRequest,
    ProviderCanaryResult,
    ProviderCanaryStatus,
    ResolvedProviderRegistry,
    RiskTier,
    stable_hash_text,
)
from imperaos.model_providers.network import evaluate_provider_network
from imperaos.model_providers.policy import GovernanceContext, evaluate_provider_policy
from imperaos.model_providers.redaction import redact_provider_input

LIVE_CANARY_ENV = "IMPERAOS_PROVIDER_LIVE_CANARY"
CANARY_PROMPTS = {
    "public_smoke": "Return the word ok as JSON: {\"status\":\"ok\"}.",
    "internal_smoke": "Return a short readiness acknowledgement.",
    "confidential_block": "Confidential canary fixture must be denied before provider call.",
}


def run_provider_canary(
    *,
    request: ProviderCanaryRequest,
    registry: ResolvedProviderRegistry,
    env: dict[str, str] | None = None,
    evidence_root: str | Path | None = None,
    budget_state_path: str | Path | None = None,
    persist_budget: bool = False,
) -> ProviderCanaryResult:
    runtime_env = env or dict(os.environ)
    provider = registry.get(request.provider_id)
    if provider is None:
        return _base_result(
            request=request,
            provider_id=request.provider_id,
            provider_kind="unknown",
            data_boundary=DataBoundary.UNKNOWN,
            risk_tier=RiskTier.BLOCKED,
            status=ProviderCanaryStatus.DENIED,
            reason_code="PROVIDER_NOT_FOUND",
        )

    prompt = CANARY_PROMPTS.get(request.prompt_fixture_id, CANARY_PROMPTS["public_smoke"])
    provider_policy = registry.policy_for(provider.provider_id)
    call_request = ProviderCallRequest(
        call_id=_canary_id(provider.provider_id),
        run_id="provider-canary",
        provider_id=provider.provider_id,
        model=provider.default_model,
        messages=[ChatMessage(role="user", content=prompt)],
        data_classes=request.data_classes,
        timeout_s=provider_policy.timeout_ms / 1000,
    )
    policy_decision = evaluate_provider_policy(
        request=call_request,
        provider=provider,
        policy=provider_policy,
        governance_context=GovernanceContext(
            remote_providers_enabled=registry.remote_providers_enabled or request.allow_live
        ),
    )
    redacted = redact_provider_input(request=call_request, decision=policy_decision)
    result = _base_result(
        request=request,
        provider_id=provider.provider_id,
        provider_kind=provider.kind,
        data_boundary=provider.data_boundary,
        risk_tier=provider.risk_tier or RiskTier.BLOCKED,
        status=ProviderCanaryStatus.SKIPPED,
        reason_code="PROVIDER_LIVE_CANARY_DISABLED",
        canary_id=call_request.call_id,
    )
    result.policy_decision = policy_decision
    result.redaction_summary = redacted.summary
    result.request_hash = stable_hash_text(prompt)

    if not request.allow_live or runtime_env.get(LIVE_CANARY_ENV) != "1":
        return _write_if_needed(result, evidence_root or request.evidence_root)

    if not policy_decision.safe_to_call_provider:
        result.status = ProviderCanaryStatus.DENIED
        result.reason_code = policy_decision.reason_code
        return _write_if_needed(result, evidence_root or request.evidence_root)

    budget_decision = evaluate_provider_budget(
        provider_id=provider.provider_id,
        policy=provider_policy,
        prompt_chars=len(prompt),
        state_path=budget_state_path,
        persist=persist_budget,
    )
    result.budget_decision = budget_decision
    if not budget_decision.allowed:
        result.status = ProviderCanaryStatus.DENIED
        result.reason_code = budget_decision.reason_code
        return _write_if_needed(result, evidence_root or request.evidence_root)

    network_decision = evaluate_provider_network(provider=provider, policy=provider_policy)
    result.network_decision = network_decision
    if not network_decision.allowed:
        result.status = ProviderCanaryStatus.DENIED
        result.reason_code = network_decision.reason_code
        return _write_if_needed(result, evidence_root or request.evidence_root)

    return _call_provider(
        provider=provider,
        registry=registry,
        request=request,
        call_request=call_request,
        result=result,
        evidence_root=evidence_root or request.evidence_root,
    )


def _call_provider(
    *,
    provider: ModelProviderRecord,
    registry: ResolvedProviderRegistry,
    request: ProviderCanaryRequest,
    call_request: ProviderCallRequest,
    result: ProviderCanaryResult,
    evidence_root: str | Path,
) -> ProviderCanaryResult:
    _ = request
    started = time.perf_counter()
    result.live_call_attempted = True
    try:
        response = ProviderAdapterFactory(registry=registry).create(provider.provider_id).generate(
            call_request
        )
    except Exception as exc:  # noqa: BLE001 - canary reports class without leaking raw details.
        result.status = ProviderCanaryStatus.FAIL
        result.reason_code = getattr(exc, "reason_code", "PROVIDER_CANARY_CALL_FAILED")
        result.error_class = type(exc).__name__
        result.latency_ms = int((time.perf_counter() - started) * 1000)
        return _write_if_needed(result, evidence_root)
    result.status = ProviderCanaryStatus.PASS
    result.reason_code = "PROVIDER_CANARY_PASS"
    result.response_hash = stable_hash_text(response.content)
    result.usage = response.usage
    result.status_code_class = "2xx"
    result.latency_ms = int((time.perf_counter() - started) * 1000)
    return _write_if_needed(result, evidence_root)


def _write_if_needed(
    result: ProviderCanaryResult,
    evidence_root: str | Path,
) -> ProviderCanaryResult:
    path = write_canary_evidence(result=result, evidence_root=evidence_root)
    result.evidence_path = str(path)
    path = write_canary_evidence(result=result, evidence_root=evidence_root)
    result.evidence_path = str(path)
    return result


def _base_result(
    *,
    request: ProviderCanaryRequest,
    provider_id: str,
    provider_kind: str,
    data_boundary: DataBoundary,
    risk_tier: RiskTier | str,
    status: ProviderCanaryStatus,
    reason_code: str,
    canary_id: str | None = None,
) -> ProviderCanaryResult:
    return ProviderCanaryResult(
        canary_id=canary_id or _canary_id(provider_id),
        provider_id=provider_id,
        provider_kind=provider_kind,
        data_boundary=data_boundary,
        risk_tier=risk_tier,
        data_classes=request.data_classes,
        status=status,
        reason_code=reason_code,
    )


def _canary_id(provider_id: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    safe_provider = provider_id.replace("/", "-")
    return f"provider-canary-{safe_provider}-{stamp}"
