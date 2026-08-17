from __future__ import annotations

from typing import Any

from imperaos.control_plane.models import NativeRequestEnvelope, ProviderNativeResult
from imperaos.control_plane.provider_governance import (
    stable_hash_payload,
    strict_retention_policy,
    strict_tool_policy,
)


class AnthropicMessagesAdapter:
    kind = "anthropic_messages"

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
                "name": str(tool.get("name", "unnamed_tool")),
                "description": str(tool.get("description", "")),
                "input_schema": tool.get("input_schema", {"type": "object"}),
                "execution_mode": "proposal_only",
            }
            for tool in custom_tools or []
        ]
        native_payload: dict[str, Any] = {
            "model": model,
            "max_tokens": 512,
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": prompt}],
                }
            ],
            "tools": native_tools,
            "metadata": {"imperaos_retention": "hash_only_store_false"},
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
        for content in raw.get("content", []):
            if isinstance(content, dict) and content.get("type") == "text":
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
                "fixture_id": "anthropic_messages_read_only_summary",
                "prompt": "Summarize failed jobs and propose remediation.",
                "model": "claude-3-5-sonnet-latest",
                "custom_tools": [{"name": "draft_ticket"}],
            }
        ]
