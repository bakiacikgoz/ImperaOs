from __future__ import annotations

from pathlib import Path

from imperaos.model_providers.native.types import (
    AnthropicMessagesRequest,
    AnthropicMessagesResult,
    OpenAIResponsesRequest,
    OpenAIResponsesResult,
    ProviderContentBlock,
    ProviderNativeConformanceReport,
    ProviderStopReason,
    ProviderStoragePolicy,
    ProviderToolPolicyDecision,
    ProviderToolProposal,
)


def test_native_contract_schemas_are_generated() -> None:
    expected = [
        "anthropic_messages_request.schema.json",
        "anthropic_messages_result.schema.json",
        "openai_responses_request.schema.json",
        "openai_responses_result.schema.json",
        "provider_content_block.schema.json",
        "provider_stop_reason.schema.json",
        "provider_storage_policy.schema.json",
        "provider_tool_policy_decision.schema.json",
        "provider_tool_proposal.schema.json",
        "provider_native_conformance_report.schema.json",
    ]

    for name in expected:
        assert Path("contracts/model_providers", name).exists()


def test_native_contract_models_forbid_raw_payload_defaults() -> None:
    storage = ProviderStoragePolicy(provider_id="openai-responses-preview")
    assert storage.request_store_flag is False
    assert storage.raw_payload_persistence is False

    assert OpenAIResponsesRequest
    assert OpenAIResponsesResult
    assert AnthropicMessagesRequest
    assert AnthropicMessagesResult
    assert ProviderContentBlock
    assert ProviderStopReason.END_TURN == "end_turn"
    assert ProviderToolPolicyDecision
    assert ProviderToolProposal
    assert ProviderNativeConformanceReport
