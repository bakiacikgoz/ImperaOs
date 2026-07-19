from __future__ import annotations

from imperaos.model_providers.models import DataClass, ProviderPolicy
from imperaos.model_providers.native.types import (
    ProviderRequestedTool,
    ProviderRequestedToolType,
)
from imperaos.model_providers.tool_policy import evaluate_provider_tool_policy


def _policy() -> ProviderPolicy:
    return ProviderPolicy(
        provider_id="openai-responses-preview",
        allowed_data_classes=[DataClass.PUBLIC],
        allow_tool_calls=True,
        requires_approval_for_tool_calls=True,
    )


def test_tool_policy_denies_builtin_web_search() -> None:
    decision = evaluate_provider_tool_policy(
        requested_tool=ProviderRequestedTool(
            tool_type=ProviderRequestedToolType.BUILTIN_WEB_SEARCH,
            name="web_search",
        ),
        provider_policy=_policy(),
        data_class=DataClass.PUBLIC,
    )

    assert decision.reason_code == "BUILTIN_WEB_SEARCH_DEFAULT_DENY"
    assert decision.execution_allowed is False
    assert decision.proposal_allowed is False


def test_tool_policy_denies_mcp_tools() -> None:
    decision = evaluate_provider_tool_policy(
        requested_tool=ProviderRequestedTool(
            tool_type=ProviderRequestedToolType.MCP,
            name="drive_connector",
        ),
        provider_policy=_policy(),
        data_class=DataClass.PUBLIC,
    )

    assert decision.reason_code == "MCP_TOOL_DEFAULT_DENY"
    assert decision.execution_allowed is False


def test_tool_policy_allows_custom_tool_proposal_only() -> None:
    decision = evaluate_provider_tool_policy(
        requested_tool=ProviderRequestedTool(
            tool_type=ProviderRequestedToolType.CUSTOM_FUNCTION,
            name="draft_remediation",
        ),
        provider_policy=_policy(),
        data_class=DataClass.PUBLIC,
    )

    assert decision.reason_code == "CUSTOM_TOOL_PROPOSAL_REQUIRES_APPROVAL"
    assert decision.proposal_allowed is True
    assert decision.execution_allowed is False


def test_anthropic_tool_policy_denies_server_tools_with_specific_reason() -> None:
    decision = evaluate_provider_tool_policy(
        requested_tool=ProviderRequestedTool(
            tool_type=ProviderRequestedToolType.BUILTIN_CODE_EXECUTION,
            name="code_execution",
        ),
        provider_policy=_policy(),
        data_class=DataClass.PUBLIC,
        execution_surface="anthropic_messages_native",
    )

    assert decision.reason_code == "ANTHROPIC_SERVER_CODE_EXECUTION_DEFAULT_DENY"
    assert decision.execution_allowed is False


def test_anthropic_tool_policy_keeps_custom_tools_proposal_only() -> None:
    decision = evaluate_provider_tool_policy(
        requested_tool=ProviderRequestedTool(
            tool_type=ProviderRequestedToolType.CUSTOM_FUNCTION,
            name="lookup_public_status",
        ),
        provider_policy=_policy(),
        data_class=DataClass.PUBLIC,
        execution_surface="anthropic_messages_native",
    )

    assert decision.reason_code == "CUSTOM_TOOL_PROPOSAL_REQUIRES_APPROVAL"
    assert decision.proposal_allowed is True
    assert decision.execution_allowed is False
