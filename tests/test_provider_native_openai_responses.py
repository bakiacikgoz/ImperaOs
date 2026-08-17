from __future__ import annotations

from imperaos.control_plane.provider_governance import evaluate_provider_policy
from imperaos.control_plane.providers.openai_responses import OpenAIResponsesAdapter


def test_openai_responses_request_builder_enforces_retention_and_tool_invariants() -> None:
    adapter = OpenAIResponsesAdapter()
    request = adapter.build_request(
        prompt="Summarize queue errors without mutation.",
        model="gpt-4.1-mini",
        custom_tools=[{"name": "create_ticket", "description": "Draft a ticket"}],
    )

    assert request.provider_kind == "openai_responses"
    assert request.raw_persistence is False
    assert request.native_payload["store"] is False
    assert request.native_payload["parallel_tool_calls"] is False
    assert request.tool_policy.server_tools_policy == "denied"
    assert request.tool_policy.custom_tools_policy == "proposal_only"
    assert request.retention_policy.store is False
    assert request.retention_policy.evidence_mode == "hash_only"
    assert request.native_payload["tools"][0]["execution_mode"] == "proposal_only"
    assert "Summarize queue errors without mutation." not in request.request_hash


def test_openai_responses_policy_denies_server_tools_before_outbound() -> None:
    adapter = OpenAIResponsesAdapter()
    request = adapter.build_request(
        prompt="Use web search.",
        model="gpt-4.1-mini",
        server_tools=["web_search"],
    )

    decision = evaluate_provider_policy(request, profile="enterprise")

    assert decision.decision == "deny"
    assert "PROVIDER_SERVER_TOOLS_DENIED" in decision.reason_codes


def test_openai_responses_parse_response_normalizes_without_raw_body() -> None:
    adapter = OpenAIResponsesAdapter()
    result = adapter.parse_response(
        {
            "id": "resp_123",
            "model": "gpt-4.1-mini",
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": "Draft remediation only."}],
                }
            ],
            "usage": {"input_tokens": 12, "output_tokens": 4},
        }
    )

    assert result.provider_kind == "openai_responses"
    assert result.output_text == "Draft remediation only."
    assert result.raw_response_persisted is False
    assert result.metadata["response_id"] == "resp_123"
