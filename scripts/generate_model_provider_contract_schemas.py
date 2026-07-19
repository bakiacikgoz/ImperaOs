from __future__ import annotations

import json
from pathlib import Path

from pydantic import TypeAdapter

from imperaos.model_providers.models import (
    ModelProviderRecord,
    NativeAdapterV2Request,
    NativeAdapterV2Response,
    ProviderCallEnvelope,
    ProviderCanaryResult,
    ProviderConformanceMatrix,
    ProviderPolicy,
    ProviderPolicyDecision,
    ProviderRouteShadowDecision,
    ResolvedProviderRegistry,
)
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

SCHEMAS = {
    "provider_registry.schema.json": ResolvedProviderRegistry,
    "provider_record.schema.json": ModelProviderRecord,
    "provider_policy.schema.json": ProviderPolicy,
    "provider_policy_decision.schema.json": ProviderPolicyDecision,
    "provider_call_envelope.schema.json": ProviderCallEnvelope,
    "provider_canary.schema.json": ProviderCanaryResult,
    "provider_router_shadow.schema.json": ProviderRouteShadowDecision,
    "provider_conformance_matrix.schema.json": ProviderConformanceMatrix,
    "native_adapter_v2_request.schema.json": NativeAdapterV2Request,
    "native_adapter_v2_response.schema.json": NativeAdapterV2Response,
    "anthropic_messages_request.schema.json": AnthropicMessagesRequest,
    "anthropic_messages_result.schema.json": AnthropicMessagesResult,
    "openai_responses_request.schema.json": OpenAIResponsesRequest,
    "openai_responses_result.schema.json": OpenAIResponsesResult,
    "provider_content_block.schema.json": ProviderContentBlock,
    "provider_stop_reason.schema.json": ProviderStopReason,
    "provider_storage_policy.schema.json": ProviderStoragePolicy,
    "provider_tool_policy_decision.schema.json": ProviderToolPolicyDecision,
    "provider_tool_proposal.schema.json": ProviderToolProposal,
    "provider_native_conformance_report.schema.json": ProviderNativeConformanceReport,
}


def main() -> None:
    output_dir = Path("contracts/model_providers")
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, model in SCHEMAS.items():
        schema = (
            model.model_json_schema()
            if hasattr(model, "model_json_schema")
            else TypeAdapter(model).json_schema()
        )
        path = output_dir / name
        path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
