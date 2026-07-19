from __future__ import annotations

from typing import Any

from imperaos.control_plane.models import NativeRequestEnvelope, ProviderNativeResult
from imperaos.control_plane.provider_governance import (
    stable_hash_payload,
    strict_retention_policy,
    strict_tool_policy,
)


class OpenAIResponsesAdapter:
    kind = "openai_responses"

    def build_request(
        self,
        *,
        prompt: str,
        model: str,
        profile: str = "enterprise",
        server_tools: list[str] | None = None,
        custom_tools: list[dict[str, Any]] | None = None,
    ) -> NativeRequestEnvelope:
        tool_policy = strict_tool_policy(
            server_tools=server_tools,
            custom_tools_requested=bool(custom_tools),
        )
        retention = strict_retention_policy()
        native_tools = [
            {
                "type": "function",
                "name": str(tool.get("name", "unnamed_tool")),
                "description": str(tool.get("description", "")),
                "execution_mode": "proposal_only",
            }
            for tool in custom_tools or []
        ]
        native_payload: dict[str, Any] = {
            "model": model,
            "input": [{"role": "user", "content": [{"type": "input_text", "text": prompt}]}],
            "store": False,
            "parallel_tool_calls": False,
            "tools": native_tools,
        }
        return NativeRequestEnvelope(
            providerKind=self.kind,
            model=model,
            profile=profile,
            requestHash=stable_hash_payload(native_payload),
            rawPersistence=False,
            toolPolicy=tool_policy,
            retentionPolicy=retention,
            nativePayload=native_payload,
        )

    def parse_response(self, raw: dict[str, Any]) -> ProviderNativeResult:
        output_text = ""
        for item in raw.get("output", []):
            if not isinstance(item, dict):
                continue
            for content in item.get("content", []):
                if isinstance(content, dict) and content.get("type") == "output_text":
                    output_text += str(content.get("text", ""))
        return ProviderNativeResult(
            providerKind=self.kind,
            outputText=output_text,
            rawResponsePersisted=False,
            metadata={
                "response_id": raw.get("id"),
                "model": raw.get("model"),
                "usage": raw.get("usage", {}),
            },
        )

    def conformance_fixtures(self) -> list[dict[str, Any]]:
        return [
            {
                "fixture_id": "openai_responses_read_only_summary",
                "prompt": "Summarize queue errors without mutation.",
                "model": "gpt-4.1-mini",
                "custom_tools": [{"name": "create_ticket", "description": "Draft only"}],
            }
        ]
