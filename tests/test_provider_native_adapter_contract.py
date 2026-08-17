from __future__ import annotations

import pytest

from imperaos.model_providers.adapters.openai_responses import OpenAIResponsesNativeAdapter
from imperaos.model_providers.errors import ProviderPolicyError
from imperaos.model_providers.models import (
    ChatMessage,
    ModelProviderRecord,
    NativeAdapterV2Request,
    NativeAdapterV2ToolPolicy,
    ProviderKind,
)


def _provider() -> ModelProviderRecord:
    return ModelProviderRecord(
        provider_id="openai-public",
        kind=ProviderKind.OPENAI,
        enabled=False,
        base_url="https://api.openai.com/v1",
        api_key_env="OPENAI_API_KEY",
        auth_mode="bearer_env",
        default_model="gpt-5.1",
        data_boundary="public_cloud",
    )


def test_openai_responses_native_adapter_is_disabled_by_default() -> None:
    adapter = OpenAIResponsesNativeAdapter(provider=_provider(), env={})
    request = NativeAdapterV2Request(
        call_id="native-adapter-disabled",
        run_id="run",
        provider_id="openai-public",
        model="gpt-5.1",
        messages=[ChatMessage(role="user", content="hello")],
    )

    response = adapter.generate(request)

    assert response.status == "skipped"
    assert response.reason_code == "NATIVE_ADAPTER_DISABLED_BY_DEFAULT"
    assert response.raw_content_persisted is False


def test_native_adapter_rejects_server_tools_before_network() -> None:
    adapter = OpenAIResponsesNativeAdapter(provider=_provider(), env={}, enabled=True)
    request = NativeAdapterV2Request(
        call_id="native-adapter-server-tools",
        run_id="run",
        provider_id="openai-public",
        model="gpt-5.1",
        messages=[ChatMessage(role="user", content="hello")],
        tool_policy=NativeAdapterV2ToolPolicy(server_tools_allowed=True),
    )

    with pytest.raises(ProviderPolicyError, match="NATIVE_ADAPTER_SERVER_TOOLS_DENY_BY_DEFAULT"):
        adapter.generate(request)
