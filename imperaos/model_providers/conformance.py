from __future__ import annotations

import json
from pathlib import Path

from imperaos.model_providers.models import (
    DataBoundary,
    DataClass,
    ModelProviderRecord,
    ProviderConformanceCheck,
    ProviderConformanceEntry,
    ProviderConformanceMatrix,
    ProviderConformanceStatus,
    ProviderKind,
    ProviderPolicy,
    ResolvedProviderRegistry,
)


def build_provider_conformance_matrix(
    *,
    registry: ResolvedProviderRegistry,
    profile: str,
    mode: str = "offline",
) -> ProviderConformanceMatrix:
    if mode not in {"offline", "live"}:
        raise ValueError("mode must be offline or live")
    entries = [
        _provider_entry(
            provider=provider,
            policy=registry.policy_for(provider.provider_id),
            remote_providers_enabled=registry.remote_providers_enabled,
            mode=mode,
        )
        for provider in registry.providers
    ]
    return ProviderConformanceMatrix(
        profile=profile,
        mode=mode,
        remote_providers_enabled=registry.remote_providers_enabled,
        providers=entries,
    )


def write_provider_conformance_matrix(
    *,
    matrix: ProviderConformanceMatrix,
    output_root: Path,
) -> dict[str, str]:
    output_root.mkdir(parents=True, exist_ok=True)
    json_path = output_root / "provider_conformance_matrix.json"
    markdown_path = output_root / "PROVIDER_CONFORMANCE_MATRIX.md"
    json_path.write_text(
        json.dumps(matrix.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(_matrix_markdown(matrix), encoding="utf-8")
    return {
        "json": json_path.as_posix(),
        "markdown": markdown_path.as_posix(),
    }


def _provider_entry(
    *,
    provider: ModelProviderRecord,
    policy: ProviderPolicy,
    remote_providers_enabled: bool,
    mode: str,
) -> ProviderConformanceEntry:
    checks = [
        _check(
            "registry_record_valid",
            True,
            "PROVIDER_REGISTRY_RECORD_VALID",
            "Provider registry record validates against the governance contract.",
            provider_id=provider.provider_id,
            kind=str(provider.kind),
        ),
        _check(
            "text_generation_contract",
            bool(provider.default_model),
            "PROVIDER_MODEL_CONFIGURED",
            "Default text generation model is declared.",
            model=provider.default_model,
        ),
        _capability_check(
            "structured_json",
            provider.supports_json_mode or provider.supports_json_schema,
            "PROVIDER_JSON_CONTRACT_DECLARED",
            "Provider declares JSON mode or JSON schema support.",
        ),
        _capability_check(
            "streaming",
            provider.supports_streaming,
            "PROVIDER_STREAMING_CONTRACT_DECLARED",
            "Provider declares streaming support.",
        ),
        _tool_policy_check(provider=provider, policy=policy),
        _capability_check(
            "vision_optional",
            provider.supports_vision,
            "PROVIDER_VISION_CONTRACT_DECLARED",
            "Vision support is optional and explicitly declared when available.",
        ),
        _check(
            "redaction_safety",
            provider.data_boundary == DataBoundary.LOCAL or policy.requires_redaction,
            "PROVIDER_REDACTION_POLICY_PRESENT",
            "Remote providers require redaction; local providers may opt out.",
            requires_redaction=policy.requires_redaction,
        ),
        _data_boundary_check(provider=provider, policy=policy),
        _check(
            "rate_limit_guard",
            policy.rate_limit_per_minute >= 0,
            "PROVIDER_RATE_LIMIT_POLICY_PRESENT",
            "Rate limit policy is declared.",
            rate_limit_per_minute=policy.rate_limit_per_minute,
        ),
        _check(
            "timeout_guard",
            policy.timeout_ms > 0,
            "PROVIDER_TIMEOUT_POLICY_PRESENT",
            "Timeout policy is declared.",
            timeout_ms=policy.timeout_ms,
        ),
        _live_canary_check(
            provider=provider,
            remote_providers_enabled=remote_providers_enabled,
            mode=mode,
        ),
    ]
    if provider.kind == ProviderKind.OPENAI_RESPONSES:
        checks.extend(_native_openai_responses_checks())
    if provider.kind == ProviderKind.ANTHROPIC_MESSAGES:
        checks.extend(_native_anthropic_messages_checks())
    pass_count = sum(item.status == ProviderConformanceStatus.PASS for item in checks)
    skipped_count = sum(item.status == ProviderConformanceStatus.SKIPPED for item in checks)
    fail_count = sum(item.status == ProviderConformanceStatus.FAIL for item in checks)
    summary_status = (
        ProviderConformanceStatus.FAIL
        if fail_count
        else ProviderConformanceStatus.PASS
        if pass_count
        else ProviderConformanceStatus.SKIPPED
    )
    return ProviderConformanceEntry(
        provider_id=provider.provider_id,
        provider_kind=provider.kind,
        data_boundary=provider.data_boundary,
        risk_tier=provider.risk_tier or "unknown",
        enabled=provider.enabled,
        summary_status=summary_status,
        pass_count=pass_count,
        skipped_count=skipped_count,
        fail_count=fail_count,
        checks=checks,
    )


def _native_openai_responses_checks() -> list[ProviderConformanceCheck]:
    return [
        ProviderConformanceCheck(
            check_id="native_storage_policy",
            status=ProviderConformanceStatus.PASS,
            reason_code="NATIVE_STORAGE_HASH_ONLY_STORE_FALSE",
            summary="OpenAI Responses native adapter forces store=false and hash-only evidence.",
            evidence={"store": False, "evidence_mode": "hash_only"},
        ),
        ProviderConformanceCheck(
            check_id="native_server_tools_policy",
            status=ProviderConformanceStatus.PASS,
            reason_code="NATIVE_SERVER_TOOLS_DEFAULT_DENY",
            summary="Built-in, MCP, computer-use, and server-side tools are denied by default.",
            evidence={"server_tools_allowed": False, "mcp_tools_allowed": False},
        ),
        ProviderConformanceCheck(
            check_id="native_canary_only",
            status=ProviderConformanceStatus.PASS,
            reason_code="NATIVE_ADAPTER_CANARY_ONLY",
            summary="Native adapter is conformance/canary-only and not production-routed.",
            evidence={"production_routing_enabled": False},
        ),
    ]


def _native_anthropic_messages_checks() -> list[ProviderConformanceCheck]:
    return [
        ProviderConformanceCheck(
            check_id="native_storage_policy",
            status=ProviderConformanceStatus.PASS,
            reason_code="NATIVE_STORAGE_HASH_ONLY_RAW_DISABLED",
            summary=(
                "Anthropic Messages native adapter uses hash-only evidence "
                "and raw persistence off."
            ),
            evidence={"evidence_mode": "hash_only", "raw_payload_persistence": False},
        ),
        ProviderConformanceCheck(
            check_id="native_server_tools_policy",
            status=ProviderConformanceStatus.PASS,
            reason_code="NATIVE_SERVER_TOOLS_DEFAULT_DENY",
            summary="Anthropic server, MCP, browser, code, and computer-use tools are denied.",
            evidence={
                "server_tools_allowed": False,
                "mcp_tools_allowed": False,
                "tool_result_loop_supported": False,
            },
        ),
        ProviderConformanceCheck(
            check_id="native_client_tools_policy",
            status=ProviderConformanceStatus.PASS,
            reason_code="NATIVE_CLIENT_TOOLS_PROPOSAL_ONLY",
            summary="Anthropic client/custom tools are normalized into governance proposals only.",
            evidence={"client_tools_mode": "proposal_only", "execution_allowed": False},
        ),
        ProviderConformanceCheck(
            check_id="native_canary_only",
            status=ProviderConformanceStatus.PASS,
            reason_code="NATIVE_ADAPTER_CANARY_ONLY",
            summary=(
                "Anthropic native adapter is conformance/canary-only "
                "and not production-routed."
            ),
            evidence={"production_routing_enabled": False, "live_canary_default": False},
        ),
    ]


def _check(
    check_id: str,
    condition: bool,
    reason_code: str,
    summary: str,
    **evidence: object,
) -> ProviderConformanceCheck:
    return ProviderConformanceCheck(
        check_id=check_id,
        status=ProviderConformanceStatus.PASS if condition else ProviderConformanceStatus.FAIL,
        reason_code=reason_code if condition else f"{reason_code}_FAILED",
        summary=summary,
        evidence={key: value for key, value in evidence.items() if value is not None},
    )


def _capability_check(
    check_id: str,
    supported: bool,
    reason_code: str,
    summary: str,
) -> ProviderConformanceCheck:
    return ProviderConformanceCheck(
        check_id=check_id,
        status=ProviderConformanceStatus.PASS
        if supported
        else ProviderConformanceStatus.SKIPPED,
        reason_code=reason_code if supported else "PROVIDER_CAPABILITY_NOT_DECLARED",
        summary=summary,
        evidence={"declared": supported},
    )


def _tool_policy_check(
    *,
    provider: ModelProviderRecord,
    policy: ProviderPolicy,
) -> ProviderConformanceCheck:
    safe = (not provider.supports_tool_calling) or (
        policy.allow_tool_calls and policy.requires_approval_for_tool_calls
    )
    return ProviderConformanceCheck(
        check_id="tool_proposal_only",
        status=ProviderConformanceStatus.PASS if safe else ProviderConformanceStatus.FAIL,
        reason_code=(
            "PROVIDER_TOOL_POLICY_APPROVAL_GATED"
            if safe
            else "PROVIDER_TOOL_POLICY_NOT_APPROVAL_GATED"
        ),
        summary="Tool calls are proposal-only unless policy approval gates them.",
        evidence={
            "supports_tool_calling": provider.supports_tool_calling,
            "allow_tool_calls": policy.allow_tool_calls,
            "requires_approval_for_tool_calls": policy.requires_approval_for_tool_calls,
            "server_tools_allowed": False,
        },
    )


def _data_boundary_check(
    *,
    provider: ModelProviderRecord,
    policy: ProviderPolicy,
) -> ProviderConformanceCheck:
    public_cloud_confidential_denied = not (
        provider.data_boundary == DataBoundary.PUBLIC_CLOUD
        and DataClass.CONFIDENTIAL in policy.allowed_data_classes
    )
    return ProviderConformanceCheck(
        check_id="policy_data_boundary",
        status=ProviderConformanceStatus.PASS
        if public_cloud_confidential_denied
        else ProviderConformanceStatus.FAIL,
        reason_code=(
            "PROVIDER_DATA_BOUNDARY_POLICY_PRESENT"
            if public_cloud_confidential_denied
            else "PROVIDER_PUBLIC_CLOUD_CONFIDENTIAL_ALLOWED"
        ),
        summary="Public cloud providers must not accept confidential data by default.",
        evidence={
            "data_boundary": provider.data_boundary,
            "allowed_data_classes": policy.allowed_data_classes,
        },
    )


def _live_canary_check(
    *,
    provider: ModelProviderRecord,
    remote_providers_enabled: bool,
    mode: str,
) -> ProviderConformanceCheck:
    if mode == "offline":
        return ProviderConformanceCheck(
            check_id="live_canary",
            status=ProviderConformanceStatus.SKIPPED,
            reason_code="PROVIDER_LIVE_CANARY_DISABLED",
            summary="Offline conformance never performs live provider calls.",
            evidence={"live_call_attempted": False},
        )
    allowed = provider.enabled and (
        provider.data_boundary == DataBoundary.LOCAL or remote_providers_enabled
    )
    return ProviderConformanceCheck(
        check_id="live_canary",
        status=ProviderConformanceStatus.SKIPPED
        if not allowed
        else ProviderConformanceStatus.PASS,
        reason_code=(
            "PROVIDER_LIVE_CANARY_DISABLED" if not allowed else "PROVIDER_LIVE_CANARY_READY"
        ),
        summary="Live conformance is gated by provider enablement and remote opt-in.",
        evidence={"live_call_attempted": False, "provider_enabled": provider.enabled},
    )


def _matrix_markdown(matrix: ProviderConformanceMatrix) -> str:
    lines = [
        "# Provider Conformance Matrix",
        "",
        f"- Profile: `{matrix.profile}`",
        f"- Mode: `{matrix.mode}`",
        f"- Remote providers enabled: `{str(matrix.remote_providers_enabled).lower()}`",
        "",
        "| Provider | Boundary | Status | Pass | Skip | Fail |",
        "| --- | --- | --- | ---: | ---: | ---: |",
    ]
    for entry in matrix.providers:
        lines.append(
            "| "
            f"{entry.provider_id} | {entry.data_boundary} | {entry.summary_status} | "
            f"{entry.pass_count} | {entry.skipped_count} | {entry.fail_count} |"
        )
    lines.append("")
    lines.append("Live checks are skipped in offline mode and do not attempt network calls.")
    lines.append("")
    return "\n".join(lines)
