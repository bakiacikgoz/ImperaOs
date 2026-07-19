from __future__ import annotations

import pytest

from imperaos.model_providers.errors import ProviderPolicyError, ProviderSchemaError
from imperaos.model_providers.models import (
    ChatMessage,
    DataClass,
    ModelProviderRecord,
    ProviderCallRequest,
    ProviderKind,
    ProviderPolicy,
)
from imperaos.model_providers.native.openai_responses import (
    build_openai_responses_payload,
    normalize_openai_responses_result,
)
from imperaos.model_providers.native.types import (
    ProviderRequestedTool,
    ProviderRequestedToolType,
    ProviderStoragePolicy,
)


def _provider() -> ModelProviderRecord:
    return ModelProviderRecord(
        provider_id="openai-responses-preview",
        kind=ProviderKind.OPENAI_RESPONSES,
        enabled=False,
        base_url="https://api.openai.com/v1",
        api_key_env="OPENAI_API_KEY",
        auth_mode="bearer_env",
        default_model="gpt-5.1",
        data_boundary="public_cloud",
    )


def _policy() -> ProviderPolicy:
    return ProviderPolicy(
        provider_id="openai-responses-preview",
        allowed_data_classes=[DataClass.PUBLIC],
        allow_tool_calls=True,
        requires_approval_for_tool_calls=True,
        max_output_tokens=256,
    )


def _request() -> ProviderCallRequest:
    return ProviderCallRequest(
        call_id="call-native",
        run_id="run-native",
        provider_id="openai-responses-preview",
        model="gpt-5.1",
        messages=[ChatMessage(role="user", content="public fixture")],
        data_classes=[DataClass.PUBLIC],
    )


def test_openai_responses_payload_forces_store_false() -> None:
    native = build_openai_responses_payload(
        provider=_provider(),
        policy=_policy(),
        request=_request(),
    )

    assert native.payload["store"] is False
    assert native.payload["parallel_tool_calls"] is False
    assert native.raw_payload_persisted is False
    assert native.request_hash.startswith("sha256:")


def test_openai_responses_structured_output_uses_imperaos_name_only() -> None:
    request = _request().model_copy(
        update={
            "json_schema": {
                "type": "object",
                "properties": {"status": {"type": "string"}},
                "required": ["status"],
                "additionalProperties": False,
            }
        }
    )

    native = build_openai_responses_payload(
        provider=_provider(),
        policy=_policy(),
        request=request,
    )

    structured_format = native.payload["text"]["format"]
    assert structured_format["name"] == "imperaos_provider_response"
    former_name = "ae" + "gis" + "os_provider_response"
    assert structured_format["name"] != former_name


def test_openai_responses_store_true_rejected() -> None:
    with pytest.raises(ProviderPolicyError, match="OPENAI_RESPONSES_STORE_TRUE_REJECTED"):
        build_openai_responses_payload(
            provider=_provider(),
            policy=_policy(),
            request=_request(),
            storage_policy=ProviderStoragePolicy(
                provider_id="openai-responses-preview",
                request_store_flag=True,
            ),
        )


def test_openai_responses_denies_builtin_web_search() -> None:
    with pytest.raises(ProviderPolicyError, match="BUILTIN_WEB_SEARCH_DEFAULT_DENY"):
        build_openai_responses_payload(
            provider=_provider(),
            policy=_policy(),
            request=_request(),
            requested_tools=[
                ProviderRequestedTool(
                    tool_type=ProviderRequestedToolType.BUILTIN_WEB_SEARCH,
                    name="web_search",
                )
            ],
        )


def test_openai_responses_allows_custom_tool_proposal_only() -> None:
    native = build_openai_responses_payload(
        provider=_provider(),
        policy=_policy(),
        request=_request(),
        requested_tools=[
            ProviderRequestedTool(
                tool_type=ProviderRequestedToolType.CUSTOM_FUNCTION,
                name="draft_remediation",
                parameters={
                    "type": "object",
                    "properties": {"summary": {"type": "string"}},
                    "required": ["summary"],
                    "additionalProperties": False,
                },
            )
        ],
    )

    assert native.payload["tools"][0]["type"] == "function"
    assert native.payload["tools"][0]["strict"] is True
    assert native.tool_policy_decisions[0].execution_allowed is False
    assert native.tool_policy_decisions[0].proposal_allowed is True


def test_openai_responses_normalizes_text_json_and_tool_proposal() -> None:
    native = build_openai_responses_payload(
        provider=_provider(),
        policy=_policy(),
        request=_request(),
    )

    text_result = normalize_openai_responses_result(
        request=native,
        provider_response={
            "status": "completed",
            "model": "gpt-5.1",
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": "{\"status\":\"green\"}"}],
                }
            ],
        },
    )
    tool_result = normalize_openai_responses_result(
        request=native,
        provider_response={
            "status": "completed",
            "model": "gpt-5.1",
            "output": [
                {
                    "type": "function_call",
                    "name": "draft_remediation",
                    "arguments": "{\"summary\":\"ok\"}",
                }
            ],
        },
    )

    assert text_result.output_text_hash is not None
    assert text_result.structured_json_hash is not None
    assert tool_result.tool_proposals[0].tool_name == "draft_remediation"
    assert tool_result.tool_proposals[0].arguments_hash.startswith("sha256:")


def test_openai_responses_rejects_unknown_output_block() -> None:
    native = build_openai_responses_payload(
        provider=_provider(),
        policy=_policy(),
        request=_request(),
    )

    with pytest.raises(ProviderSchemaError, match="OPENAI_RESPONSES_UNSUPPORTED_OUTPUT_BLOCK"):
        normalize_openai_responses_result(
            request=native,
            provider_response={
                "status": "completed",
                "model": "gpt-5.1",
                "output": [{"type": "not_supported"}],
            },
        )
