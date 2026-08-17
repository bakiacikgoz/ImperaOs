from __future__ import annotations

import json
import re
import time
from collections.abc import Mapping, Sequence
from typing import Any

from imperaos.model_providers.errors import ProviderPolicyError, ProviderSchemaError
from imperaos.model_providers.models import (
    ChatMessage,
    DataClass,
    ModelProviderRecord,
    ProviderCallRequest,
    ProviderPolicy,
    stable_hash_text,
)
from imperaos.model_providers.native.types import (
    AnthropicMessagesRequest,
    AnthropicMessagesResult,
    ProviderContentBlock,
    ProviderEvidenceMode,
    ProviderRequestedTool,
    ProviderRequestedToolType,
    ProviderStopReason,
    ProviderStoragePolicy,
    ProviderToolPolicyStatus,
    ProviderToolProposal,
)
from imperaos.model_providers.redaction import BEARER_RE, EMAIL_RE, SECRET_RE
from imperaos.model_providers.tool_policy import evaluate_provider_tool_policy

SECRET_LIKE_RE = re.compile(r"\b(?:sk|pk|rk|ak)-[A-Za-z0-9_\-]{12,}\b")
SUPPORTED_STOP_REASONS = {
    ProviderStopReason.END_TURN.value,
    ProviderStopReason.TOOL_USE.value,
    ProviderStopReason.MAX_TOKENS.value,
    ProviderStopReason.STOP_SEQUENCE.value,
    ProviderStopReason.PAUSE_TURN.value,
    ProviderStopReason.REFUSAL.value,
    ProviderStopReason.MODEL_CONTEXT_WINDOW_EXCEEDED.value,
}


class AnthropicMessagesNativeAdapter:
    def __init__(
        self,
        *,
        provider: ModelProviderRecord,
        policy: ProviderPolicy,
        env: Mapping[str, str] | None = None,
        enabled: bool = False,
    ):
        self.provider = provider
        self.policy = policy
        self.env = env or {}
        self.enabled = enabled

    def build_payload(
        self,
        *,
        request: ProviderCallRequest,
        storage_policy: ProviderStoragePolicy | None = None,
        requested_tools: Sequence[ProviderRequestedTool] | None = None,
    ) -> AnthropicMessagesRequest:
        if not self.enabled:
            raise ProviderPolicyError("NATIVE_ADAPTER_DISABLED_BY_DEFAULT")
        return build_anthropic_messages_payload(
            provider=self.provider,
            policy=self.policy,
            request=request,
            storage_policy=storage_policy,
            requested_tools=requested_tools,
        )

    def normalize_result(
        self,
        *,
        request: AnthropicMessagesRequest,
        provider_response: Mapping[str, Any],
        started_at_monotonic: float | None = None,
    ) -> AnthropicMessagesResult:
        return normalize_anthropic_messages_result(
            request=request,
            provider_response=provider_response,
            started_at_monotonic=started_at_monotonic,
        )


def build_anthropic_messages_payload(
    *,
    provider: ModelProviderRecord,
    policy: ProviderPolicy,
    request: ProviderCallRequest,
    storage_policy: ProviderStoragePolicy | None = None,
    requested_tools: Sequence[ProviderRequestedTool] | None = None,
) -> AnthropicMessagesRequest:
    storage = storage_policy or ProviderStoragePolicy(provider_id=provider.provider_id)
    _enforce_storage_policy(storage)
    data_class = request.data_classes[0] if request.data_classes else DataClass.PUBLIC
    decisions = [
        evaluate_provider_tool_policy(
            requested_tool=tool,
            provider_policy=policy,
            data_class=data_class,
            execution_surface="anthropic_messages_native",
        )
        for tool in requested_tools or []
    ]
    denied = [item for item in decisions if item.status == ProviderToolPolicyStatus.DENY]
    if denied:
        raise ProviderPolicyError(denied[0].reason_code)

    payload: dict[str, Any] = {
        "model": request.model,
        "max_tokens": policy.max_output_tokens or 256,
        "messages": [_message_to_anthropic_message(item) for item in request.messages],
        "metadata": {
            "call_id_hash": stable_hash_text(request.call_id),
            "run_id_hash": stable_hash_text(request.run_id),
            "provider_id": provider.provider_id,
        },
    }
    if request.system:
        payload["system"] = request.system

    tools = [_custom_tool_payload(tool) for tool in requested_tools or []]
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = {"type": "auto"}
    else:
        payload["tool_choice"] = {"type": "none"}

    request_hash = stable_hash_text(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    if request_hash is None:
        raise ProviderPolicyError("ANTHROPIC_MESSAGES_REQUEST_HASH_FAILED")
    return AnthropicMessagesRequest(
        provider_id=provider.provider_id,
        model=request.model,
        request_hash=request_hash,
        payload=payload,
        storage_policy=storage,
        tool_policy_decisions=decisions,
        canary_only=True,
        live_canary_attempted=False,
        raw_payload_persisted=False,
    )


def normalize_anthropic_messages_result(
    *,
    request: AnthropicMessagesRequest,
    provider_response: Mapping[str, Any],
    started_at_monotonic: float | None = None,
) -> AnthropicMessagesResult:
    stop_reason = str(provider_response.get("stop_reason") or "")
    if stop_reason not in SUPPORTED_STOP_REASONS:
        raise ProviderSchemaError("ANTHROPIC_MESSAGES_UNKNOWN_STOP_REASON")
    if stop_reason == ProviderStopReason.PAUSE_TURN:
        raise ProviderPolicyError("ANTHROPIC_MESSAGES_PAUSE_TURN_BLOCKED")
    if stop_reason in {
        ProviderStopReason.REFUSAL,
        ProviderStopReason.MODEL_CONTEXT_WINDOW_EXCEEDED,
    }:
        raise ProviderPolicyError(f"ANTHROPIC_MESSAGES_{stop_reason.upper()}_BLOCKED")

    content = provider_response.get("content")
    if not isinstance(content, list):
        raise ProviderSchemaError("ANTHROPIC_MESSAGES_CONTENT_MISSING")

    output_text_parts: list[str] = []
    proposals: list[ProviderToolProposal] = []
    blocks: list[ProviderContentBlock] = []
    has_tool_use = False
    for item in content:
        if not isinstance(item, Mapping):
            raise ProviderSchemaError("ANTHROPIC_MESSAGES_CONTENT_BLOCK_MALFORMED")
        block_type = str(item.get("type") or "")
        if block_type == "text":
            text = item.get("text")
            if not isinstance(text, str):
                raise ProviderSchemaError("ANTHROPIC_MESSAGES_TEXT_BLOCK_MISSING_TEXT")
            _reject_secret_like_output(text)
            output_text_parts.append(text)
            blocks.append(
                ProviderContentBlock(
                    block_type="text",
                    text_hash=stable_hash_text(text),
                )
            )
        elif block_type == "tool_use":
            has_tool_use = True
            proposal, block = _tool_use_to_proposal(request=request, item=item)
            proposals.append(proposal)
            blocks.append(block)
        elif block_type == "tool_result":
            raise ProviderPolicyError("ANTHROPIC_TOOL_RESULT_LOOP_NOT_IMPLEMENTED")
        else:
            raise ProviderSchemaError("ANTHROPIC_MESSAGES_UNSUPPORTED_CONTENT_BLOCK")

    if stop_reason == ProviderStopReason.MAX_TOKENS and has_tool_use:
        raise ProviderPolicyError("ANTHROPIC_MESSAGES_MAX_TOKENS_INCOMPLETE_TOOL_BLOCKED")

    output_text = "\n".join(part for part in output_text_parts if part)
    raw_usage = provider_response.get("usage")
    usage = raw_usage if isinstance(raw_usage, dict) else None
    latency_ms = (
        int((time.perf_counter() - started_at_monotonic) * 1000)
        if started_at_monotonic is not None
        else None
    )
    return AnthropicMessagesResult(
        provider_id=request.provider_id,
        model=str(provider_response.get("model") or request.model),
        status="pass",
        reason_code="ANTHROPIC_MESSAGES_NORMALIZED",
        stop_reason=stop_reason,
        output_text_hash=stable_hash_text(output_text) if output_text else None,
        content_blocks=blocks,
        tool_proposals=proposals,
        usage=usage,
        latency_ms=latency_ms,
        tool_result_loop_supported=False,
        raw_response_persisted=False,
    )


def _enforce_storage_policy(storage: ProviderStoragePolicy) -> None:
    if storage.remote_store_allowed:
        raise ProviderPolicyError("ANTHROPIC_MESSAGES_REMOTE_STORE_NOT_ALLOWED")
    if storage.request_store_flag:
        raise ProviderPolicyError("ANTHROPIC_MESSAGES_STORE_FLAG_NOT_SUPPORTED")
    if storage.cache_allowed:
        raise ProviderPolicyError("ANTHROPIC_MESSAGES_CACHE_NOT_ALLOWED")
    if storage.raw_payload_persistence:
        raise ProviderPolicyError("ANTHROPIC_MESSAGES_RAW_PAYLOAD_PERSISTENCE_REJECTED")
    if storage.evidence_mode != ProviderEvidenceMode.HASH_ONLY:
        raise ProviderPolicyError("ANTHROPIC_MESSAGES_HASH_ONLY_EVIDENCE_REQUIRED")


def _message_to_anthropic_message(message: ChatMessage) -> dict[str, Any]:
    if message.role == "system":
        raise ProviderSchemaError("ANTHROPIC_MESSAGES_SYSTEM_MESSAGE_USE_SYSTEM_FIELD")
    if message.role == "tool":
        raise ProviderPolicyError("ANTHROPIC_TOOL_RESULT_LOOP_NOT_IMPLEMENTED")
    if message.role not in {"user", "assistant"}:
        raise ProviderSchemaError("ANTHROPIC_MESSAGES_UNSUPPORTED_ROLE")
    return {
        "role": message.role,
        "content": [{"type": "text", "text": message.content}],
    }


def _custom_tool_payload(tool: ProviderRequestedTool) -> dict[str, Any]:
    if tool.tool_type != ProviderRequestedToolType.CUSTOM_FUNCTION:
        raise ProviderPolicyError("ANTHROPIC_MESSAGES_NON_CUSTOM_TOOL_BLOCKED")
    return {
        "name": tool.name,
        "description": tool.description or "",
        "input_schema": tool.parameters,
    }


def _tool_use_to_proposal(
    *,
    request: AnthropicMessagesRequest,
    item: Mapping[str, Any],
) -> tuple[ProviderToolProposal, ProviderContentBlock]:
    tool_id = item.get("id")
    name = item.get("name")
    arguments = item.get("input")
    if not isinstance(tool_id, str) or not tool_id:
        raise ProviderSchemaError("ANTHROPIC_MESSAGES_TOOL_USE_ID_MISSING")
    if not isinstance(name, str) or not name:
        raise ProviderSchemaError("ANTHROPIC_MESSAGES_TOOL_NAME_MISSING")
    if not isinstance(arguments, Mapping):
        raise ProviderSchemaError("ANTHROPIC_MESSAGES_TOOL_INPUT_MALFORMED")
    parsed_args = dict(arguments)
    redacted_preview = _redact_mapping(parsed_args)
    args_json = json.dumps(parsed_args, sort_keys=True, separators=(",", ":"))
    args_hash = stable_hash_text(args_json)
    if args_hash is None:
        raise ProviderSchemaError("ANTHROPIC_MESSAGES_TOOL_ARGUMENT_HASH_FAILED")
    proposal_hash = stable_hash_text(f"{request.provider_id}:{tool_id}:{name}:{args_hash}")
    proposal = ProviderToolProposal(
        proposal_id=proposal_hash or args_hash,
        provider_id=request.provider_id,
        provider_tool_id=tool_id,
        tool_name=name,
        execution_mode="proposal_only",
        arguments_hash=args_hash,
        redacted_arguments_preview=redacted_preview,
        data_class=DataClass.PUBLIC,
        risk_tier="medium",
        governance_action="requires_approval",
    )
    block = ProviderContentBlock(
        block_type="tool_use",
        tool_name=name,
        tool_id=tool_id,
        arguments_hash=args_hash,
    )
    return proposal, block


def _redact_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, str):
            redacted[key] = _redact_text(item)
        elif isinstance(item, Mapping):
            redacted[key] = _redact_mapping(item)
        elif isinstance(item, list):
            redacted[key] = [
                _redact_text(entry)
                if isinstance(entry, str)
                else _redact_mapping(entry)
                if isinstance(entry, Mapping)
                else entry
                for entry in item
            ]
        else:
            redacted[key] = item
    return redacted


def _redact_text(value: str) -> str:
    result = EMAIL_RE.sub("[REDACTED_EMAIL]", value)
    result = SECRET_RE.sub("[REDACTED_SECRET]", result)
    return BEARER_RE.sub("Bearer [REDACTED_TOKEN]", result)


def _reject_secret_like_output(value: str) -> None:
    if (
        SECRET_LIKE_RE.search(value)
        or BEARER_RE.search(value)
        or "SECRET_LIKE_OUTPUT_FIXTURE" in value
    ):
        raise ProviderPolicyError("ANTHROPIC_MESSAGES_SECRET_LIKE_OUTPUT_REJECTED")
