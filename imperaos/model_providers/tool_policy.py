from __future__ import annotations

from imperaos.artifacts.tool_names import PUBLIC_ARTIFACT_TOOL_NAMES
from imperaos.model_providers.models import DataClass, ProviderPolicy
from imperaos.model_providers.native.types import (
    ProviderRequestedTool,
    ProviderRequestedToolType,
    ProviderToolPolicyDecision,
    ProviderToolPolicyStatus,
)

DENY_REASON_BY_TOOL_TYPE = {
    ProviderRequestedToolType.BUILTIN_WEB_SEARCH: "BUILTIN_WEB_SEARCH_DEFAULT_DENY",
    ProviderRequestedToolType.BUILTIN_FILE_SEARCH: "BUILTIN_FILE_SEARCH_DEFAULT_DENY",
    ProviderRequestedToolType.BUILTIN_COMPUTER_USE: "BUILTIN_COMPUTER_USE_DEFAULT_DENY",
    ProviderRequestedToolType.BUILTIN_CODE_EXECUTION: "BUILTIN_CODE_EXECUTION_DEFAULT_DENY",
    ProviderRequestedToolType.BUILTIN_WEB_FETCH: "BUILTIN_WEB_FETCH_DEFAULT_DENY",
    ProviderRequestedToolType.BUILTIN_BASH: "BUILTIN_BASH_DEFAULT_DENY",
    ProviderRequestedToolType.BUILTIN_TEXT_EDITOR: "BUILTIN_TEXT_EDITOR_DEFAULT_DENY",
    ProviderRequestedToolType.MCP: "MCP_TOOL_DEFAULT_DENY",
    ProviderRequestedToolType.SERVER_TOOL: "SERVER_TOOL_DEFAULT_DENY",
    ProviderRequestedToolType.UNKNOWN: "UNKNOWN_TOOL_DEFAULT_DENY",
}

ANTHROPIC_SERVER_TOOL_NAMES = {
    "web_search",
    "web_search_20260209",
    "web_fetch",
    "web_fetch_20260209",
    "code_execution",
    "code_execution_20260609",
    "tool_search",
}

ANTHROPIC_CLIENT_HIGH_RISK_TOOL_NAMES = {
    "bash",
    "bash_20250124",
    "text_editor",
    "text_editor_20250429",
    "computer",
    "computer_20250124",
}


def evaluate_provider_tool_policy(
    *,
    requested_tool: ProviderRequestedTool,
    provider_policy: ProviderPolicy,
    data_class: DataClass,
    execution_surface: str = "provider_native_adapter",
) -> ProviderToolPolicyDecision:
    _ = data_class
    if execution_surface == "anthropic_messages_native":
        anthropic_reason = _anthropic_tool_deny_reason(requested_tool)
        if anthropic_reason is not None:
            return ProviderToolPolicyDecision(
                status=ProviderToolPolicyStatus.DENY,
                requested_tool_type=requested_tool.tool_type,
                reason_code=anthropic_reason,
                execution_allowed=False,
                proposal_allowed=False,
                approval_required=False,
                tool_name=requested_tool.name,
            )

    if requested_tool.tool_type != ProviderRequestedToolType.CUSTOM_FUNCTION:
        return ProviderToolPolicyDecision(
            status=ProviderToolPolicyStatus.DENY,
            requested_tool_type=requested_tool.tool_type,
            reason_code=DENY_REASON_BY_TOOL_TYPE.get(
                requested_tool.tool_type,
                "UNKNOWN_TOOL_DEFAULT_DENY",
            ),
            execution_allowed=False,
            proposal_allowed=False,
            approval_required=False,
            tool_name=requested_tool.name,
        )

    if (
        requested_tool.name.startswith("artifact.")
        and requested_tool.name not in PUBLIC_ARTIFACT_TOOL_NAMES
    ):
        return ProviderToolPolicyDecision(
            status=ProviderToolPolicyStatus.DENY,
            requested_tool_type=requested_tool.tool_type,
            reason_code="ARTIFACT_TOOL_NOT_PUBLIC",
            execution_allowed=False,
            proposal_allowed=False,
            approval_required=False,
            tool_name=requested_tool.name,
        )

    if not provider_policy.allow_tool_calls:
        return ProviderToolPolicyDecision(
            status=ProviderToolPolicyStatus.DENY,
            requested_tool_type=requested_tool.tool_type,
            reason_code="CUSTOM_TOOL_POLICY_DENY",
            execution_allowed=False,
            proposal_allowed=False,
            approval_required=False,
            tool_name=requested_tool.name,
        )

    approval_required = provider_policy.requires_approval_for_tool_calls or requested_tool.mutating
    return ProviderToolPolicyDecision(
        status=ProviderToolPolicyStatus.REQUIRES_APPROVAL
        if approval_required
        else ProviderToolPolicyStatus.ALLOW_PROPOSAL,
        requested_tool_type=requested_tool.tool_type,
        reason_code="CUSTOM_TOOL_PROPOSAL_REQUIRES_APPROVAL"
        if approval_required
        else "CUSTOM_TOOL_PROPOSAL_ONLY",
        execution_allowed=False,
        proposal_allowed=True,
        approval_required=approval_required,
        tool_name=requested_tool.name,
    )


def _anthropic_tool_deny_reason(requested_tool: ProviderRequestedTool) -> str | None:
    name = requested_tool.name.strip().lower()
    if requested_tool.tool_type == ProviderRequestedToolType.CUSTOM_FUNCTION:
        return None
    if requested_tool.tool_type == ProviderRequestedToolType.BUILTIN_WEB_SEARCH:
        return "ANTHROPIC_SERVER_WEB_SEARCH_DEFAULT_DENY"
    if requested_tool.tool_type == ProviderRequestedToolType.BUILTIN_WEB_FETCH:
        return "ANTHROPIC_SERVER_WEB_FETCH_DEFAULT_DENY"
    if requested_tool.tool_type == ProviderRequestedToolType.BUILTIN_CODE_EXECUTION:
        return "ANTHROPIC_SERVER_CODE_EXECUTION_DEFAULT_DENY"
    if requested_tool.tool_type == ProviderRequestedToolType.BUILTIN_COMPUTER_USE:
        return "ANTHROPIC_COMPUTER_USE_DEFAULT_DENY"
    if requested_tool.tool_type == ProviderRequestedToolType.BUILTIN_BASH:
        return "ANTHROPIC_BASH_DEFAULT_DENY"
    if requested_tool.tool_type == ProviderRequestedToolType.BUILTIN_TEXT_EDITOR:
        return "ANTHROPIC_TEXT_EDITOR_DEFAULT_DENY"
    if requested_tool.tool_type == ProviderRequestedToolType.MCP:
        return "ANTHROPIC_MCP_DEFAULT_DENY"
    if requested_tool.tool_type == ProviderRequestedToolType.SERVER_TOOL:
        if name in ANTHROPIC_SERVER_TOOL_NAMES:
            return "ANTHROPIC_SERVER_TOOL_DEFAULT_DENY"
        return "SERVER_TOOL_DEFAULT_DENY"
    if name in ANTHROPIC_SERVER_TOOL_NAMES:
        return "ANTHROPIC_SERVER_TOOL_DEFAULT_DENY"
    if name in ANTHROPIC_CLIENT_HIGH_RISK_TOOL_NAMES:
        return "ANTHROPIC_CLIENT_HIGH_RISK_TOOL_DEFAULT_DENY"
    return None
