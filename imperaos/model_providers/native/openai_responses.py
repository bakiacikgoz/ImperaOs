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
    OpenAIResponsesRequest,
    OpenAIResponsesResult,
    ProviderEvidenceMode,
    ProviderRequestedTool,
    ProviderRequestedToolType,
    ProviderStoragePolicy,
    ProviderToolPolicyStatus,
    ProviderToolProposal,
)
from imperaos.model_providers.redaction import BEARER_RE, EMAIL_RE, SECRET_RE
from imperaos.model_providers.tool_policy import evaluate_provider_tool_policy

SECRET_LIKE_RE = re.compile(r"\b(?:sk|pk|rk|ak)-[A-Za-z0-9_\-]{12,}\b")


class OpenAIResponsesNativeAdapter:
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
    ) -> OpenAIResponsesRequest:
        if not self.enabled:
            raise ProviderPolicyError("NATIVE_ADAPTER_DISABLED_BY_DEFAULT")
        return build_openai_responses_payload(
            provider=self.provider,
            policy=self.policy,
            request=request,
            storage_policy=storage_policy,
            requested_tools=requested_tools,
        )

    def normalize_result(
        self,
        *,
        request: OpenAIResponsesRequest,
        provider_response: Mapping[str, Any],
        started_at_monotonic: float | None = None,
    ) -> OpenAIResponsesResult:
        return normalize_openai_responses_result(
            request=request,
            provider_response=provider_response,
            started_at_monotonic=started_at_monotonic,
        )


def build_openai_responses_payload(
    *,
    provider: ModelProviderRecord,
    policy: ProviderPolicy,
    request: ProviderCallRequest,
    storage_policy: ProviderStoragePolicy | None = None,
    requested_tools: Sequence[ProviderRequestedTool] | None = None,
) -> OpenAIResponsesRequest:
    storage = storage_policy or ProviderStoragePolicy(provider_id=provider.provider_id)
    _enforce_storage_policy(storage)
    data_class = request.data_classes[0] if request.data_classes else DataClass.PUBLIC
    decisions = [
        evaluate_provider_tool_policy(
            requested_tool=tool,
            provider_policy=policy,
            data_class=data_class,
            execution_surface="openai_responses_native",
        )
        for tool in requested_tools or []
    ]
    denied = [item for item in decisions if item.status == ProviderToolPolicyStatus.DENY]
    if denied:
        raise ProviderPolicyError(denied[0].reason_code)

    payload: dict[str, Any] = {
        "model": request.model,
        "input": [_message_to_input_item(item) for item in request.messages],
        "store": False,
        "stream": False,
        "parallel_tool_calls": False,
        "metadata": {
            "call_id_hash": stable_hash_text(request.call_id),
            "run_id_hash": stable_hash_text(request.run_id),
            "provider_id": provider.provider_id,
        },
    }
    if request.system:
        payload["instructions"] = request.system
    if policy.max_output_tokens is not None:
        payload["max_output_tokens"] = policy.max_output_tokens
    if request.json_schema is not None:
        payload["text"] = {
            "format": {
                "type": "json_schema",
                "name": "imperaos_provider_response",
                "strict": True,
                "schema": request.json_schema,
            }
        }
    tools = [_custom_tool_payload(tool) for tool in requested_tools or []]
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    request_hash = stable_hash_text(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    if request_hash is None:
        raise ProviderPolicyError("OPENAI_RESPONSES_REQUEST_HASH_FAILED")
    return OpenAIResponsesRequest(
        provider_id=provider.provider_id,
        model=request.model,
        request_hash=request_hash,
        payload=payload,
        storage_policy=storage,
        tool_policy_decisions=decisions,
        raw_payload_persisted=False,
    )


def normalize_openai_responses_result(
    *,
    request: OpenAIResponsesRequest,
    provider_response: Mapping[str, Any],
    started_at_monotonic: float | None = None,
) -> OpenAIResponsesResult:
    status = str(provider_response.get("status") or "")
    if status and status not in {"completed", "incomplete"}:
        raise ProviderSchemaError("OPENAI_RESPONSES_UNSUPPORTED_STATUS")
    output = provider_response.get("output")
    if not isinstance(output, list):
        raise ProviderSchemaError("OPENAI_RESPONSES_OUTPUT_MISSING")

    output_text_parts: list[str] = []
    structured_json_text: str | None = None
    proposals: list[ProviderToolProposal] = []
    for item in output:
        if not isinstance(item, Mapping):
            raise ProviderSchemaError("OPENAI_RESPONSES_OUTPUT_ITEM_MALFORMED")
        item_type = str(item.get("type") or "")
        if item_type == "message":
            text_parts = _extract_message_text(item)
            output_text_parts.extend(text_parts)
            if _looks_like_json_text(text_parts):
                structured_json_text = "\n".join(text_parts)
        elif item_type == "function_call":
            proposals.append(_function_call_to_proposal(request=request, item=item))
        else:
            raise ProviderSchemaError("OPENAI_RESPONSES_UNSUPPORTED_OUTPUT_BLOCK")

    output_text = "\n".join(part for part in output_text_parts if part)
    _reject_secret_like_output(output_text)
    usage = (
        provider_response.get("usage") if isinstance(provider_response.get("usage"), dict) else None
    )
    latency_ms = (
        int((time.perf_counter() - started_at_monotonic) * 1000)
        if started_at_monotonic is not None
        else None
    )
    return OpenAIResponsesResult(
        provider_id=request.provider_id,
        model=str(provider_response.get("model") or request.model),
        status="pass",
        reason_code="OPENAI_RESPONSES_NORMALIZED",
        output_text_hash=stable_hash_text(output_text) if output_text else None,
        structured_json_hash=stable_hash_text(structured_json_text)
        if structured_json_text
        else None,
        tool_proposals=proposals,
        usage=usage,
        latency_ms=latency_ms,
        raw_response_persisted=False,
    )


def _enforce_storage_policy(storage: ProviderStoragePolicy) -> None:
    if storage.remote_store_allowed:
        raise ProviderPolicyError("OPENAI_RESPONSES_REMOTE_STORE_NOT_ALLOWED")
    if storage.request_store_flag:
        raise ProviderPolicyError("OPENAI_RESPONSES_STORE_TRUE_REJECTED")
    if storage.cache_allowed:
        raise ProviderPolicyError("OPENAI_RESPONSES_CACHE_NOT_ALLOWED")
    if storage.raw_payload_persistence:
        raise ProviderPolicyError("OPENAI_RESPONSES_RAW_PAYLOAD_PERSISTENCE_REJECTED")
    if storage.evidence_mode != ProviderEvidenceMode.HASH_ONLY:
        raise ProviderPolicyError("OPENAI_RESPONSES_HASH_ONLY_EVIDENCE_REQUIRED")


def _message_to_input_item(message: ChatMessage) -> dict[str, Any]:
    role = "developer" if message.role == "system" else message.role
    return {
        "role": role,
        "content": [{"type": "input_text", "text": message.content}],
    }


def _custom_tool_payload(tool: ProviderRequestedTool) -> dict[str, Any]:
    if tool.tool_type != ProviderRequestedToolType.CUSTOM_FUNCTION:
        raise ProviderPolicyError("OPENAI_RESPONSES_NON_CUSTOM_TOOL_BLOCKED")
    return {
        "type": "function",
        "name": tool.name,
        "description": tool.description or "",
        "strict": True,
        "parameters": tool.parameters,
    }


def _extract_message_text(item: Mapping[str, Any]) -> list[str]:
    content = item.get("content")
    if not isinstance(content, list):
        raise ProviderSchemaError("OPENAI_RESPONSES_MESSAGE_CONTENT_MALFORMED")
    parts: list[str] = []
    for block in content:
        if not isinstance(block, Mapping):
            raise ProviderSchemaError("OPENAI_RESPONSES_MESSAGE_BLOCK_MALFORMED")
        if block.get("type") != "output_text":
            raise ProviderSchemaError("OPENAI_RESPONSES_UNSUPPORTED_MESSAGE_BLOCK")
        text = block.get("text")
        if not isinstance(text, str):
            raise ProviderSchemaError("OPENAI_RESPONSES_OUTPUT_TEXT_MISSING")
        parts.append(text)
    return parts


def _looks_like_json_text(parts: list[str]) -> bool:
    text = "\n".join(parts).strip()
    return text.startswith("{") and text.endswith("}")


def _function_call_to_proposal(
    *,
    request: OpenAIResponsesRequest,
    item: Mapping[str, Any],
) -> ProviderToolProposal:
    name = item.get("name")
    arguments = item.get("arguments")
    if not isinstance(name, str) or not name:
        raise ProviderSchemaError("OPENAI_RESPONSES_FUNCTION_NAME_MISSING")
    if isinstance(arguments, str):
        try:
            parsed_args = json.loads(arguments) if arguments else {}
        except json.JSONDecodeError as exc:
            raise ProviderSchemaError("OPENAI_RESPONSES_FUNCTION_ARGUMENTS_MALFORMED") from exc
    elif isinstance(arguments, Mapping):
        parsed_args = dict(arguments)
    else:
        parsed_args = {}
    redacted_preview = _redact_mapping(parsed_args)
    args_json = json.dumps(parsed_args, sort_keys=True, separators=(",", ":"))
    args_hash = stable_hash_text(args_json)
    if args_hash is None:
        raise ProviderSchemaError("OPENAI_RESPONSES_FUNCTION_ARGUMENT_HASH_FAILED")
    proposal_hash = stable_hash_text(f"{request.provider_id}:{name}:{args_hash}")
    return ProviderToolProposal(
        proposal_id=proposal_hash or args_hash,
        provider_id=request.provider_id,
        tool_name=name,
        arguments_hash=args_hash,
        redacted_arguments_preview=redacted_preview,
        data_class=DataClass.PUBLIC,
        risk_tier="medium",
        governance_action="requires_approval",
    )


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
        raise ProviderPolicyError("OPENAI_RESPONSES_SECRET_LIKE_OUTPUT_REJECTED")
