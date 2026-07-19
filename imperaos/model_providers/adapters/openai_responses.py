from __future__ import annotations

from collections.abc import Mapping

from imperaos.model_providers.errors import ProviderPolicyError
from imperaos.model_providers.models import (
    ModelProviderRecord,
    NativeAdapterV2Request,
    NativeAdapterV2Response,
)


class OpenAIResponsesNativeAdapter:
    """Disabled-by-default native adapter contract skeleton.

    The V2 native path is intentionally canary-only until product docs, tool
    policy, and redaction evidence are reviewed for the exact API revision.
    """

    def __init__(
        self,
        *,
        provider: ModelProviderRecord,
        env: Mapping[str, str] | None = None,
        enabled: bool = False,
    ):
        self.provider = provider
        self.env = env or {}
        self.enabled = enabled

    def generate(self, request: NativeAdapterV2Request) -> NativeAdapterV2Response:
        if request.tool_policy.server_tools_allowed:
            raise ProviderPolicyError("NATIVE_ADAPTER_SERVER_TOOLS_DENY_BY_DEFAULT")
        if not request.canary_only:
            raise ProviderPolicyError("NATIVE_ADAPTER_CANARY_ONLY_REQUIRED")
        if not self.enabled:
            return NativeAdapterV2Response(
                call_id=request.call_id,
                provider_id=request.provider_id,
                model=request.model,
                status="skipped",
                reason_code="NATIVE_ADAPTER_DISABLED_BY_DEFAULT",
                raw_content_persisted=False,
            )
        raise ProviderPolicyError("NATIVE_ADAPTER_LIVE_IMPLEMENTATION_NOT_ENABLED")
