from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Iterator, Mapping
from typing import Any

from imperaos.model_providers.errors import (
    ProviderAuthError,
    ProviderGenerationError,
    ProviderRateLimitError,
    ProviderSchemaError,
    ProviderTimeoutError,
)
from imperaos.model_providers.models import (
    ChatMessage,
    ModelProviderRecord,
    ProviderCallRequest,
    ProviderResponse,
    ProviderStreamEvent,
)


class OpenAICompatibleProvider:
    def __init__(
        self,
        *,
        provider: ModelProviderRecord,
        env: Mapping[str, str] | None = None,
    ):
        self.provider = provider
        self.env = env or os.environ

    def generate(self, request: ProviderCallRequest) -> ProviderResponse:
        payload = self._payload(request, stream=False)
        raw = self._post_json(payload=payload, timeout_s=request.timeout_s)
        return self._parse_response(raw, request=request)

    def generate_stream(self, request: ProviderCallRequest) -> Iterator[ProviderStreamEvent]:
        payload = self._payload(request, stream=True)
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self._chat_completions_url(),
            data=body,
            headers=self._headers(),
            method="POST",
        )
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=request.timeout_s) as response:  # noqa: S310
                for raw_line in response:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data = line.removeprefix("data:").strip()
                    if data == "[DONE]":
                        yield ProviderStreamEvent(event="done")
                        return
                    parsed = json.loads(data)
                    choice = parsed.get("choices", [{}])[0]
                    delta = choice.get("delta", {})
                    yield ProviderStreamEvent(
                        event="delta",
                        delta=str(delta.get("content") or ""),
                        finish_reason=choice.get("finish_reason"),
                    )
        except TimeoutError as exc:
            raise ProviderTimeoutError("provider stream timed out") from exc
        except urllib.error.HTTPError as exc:
            raise _map_http_error(exc) from exc
        except json.JSONDecodeError as exc:
            raise ProviderSchemaError("provider stream returned malformed JSON") from exc
        finally:
            _ = started

    def models(self, refresh: bool = False) -> list[str]:
        _ = refresh
        return self.provider.models or [self.provider.default_model]

    def _payload(self, request: ProviderCallRequest, *, stream: bool) -> dict[str, Any]:
        messages = [
            {"role": item.role, "content": item.content}
            for item in _messages_with_system(request.messages, request.system)
        ]
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": messages,
            "stream": stream,
        }
        if request.json_mode:
            payload["response_format"] = {"type": "json_object"}
        if request.tools:
            payload["tools"] = [tool.model_dump(mode="json") for tool in request.tools]
            payload["tool_choice"] = "auto"
        return payload

    def _post_json(self, *, payload: dict[str, Any], timeout_s: float) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self._chat_completions_url(),
            data=body,
            headers=self._headers(),
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as response:  # noqa: S310
                raw = response.read().decode("utf-8")
        except TimeoutError as exc:
            raise ProviderTimeoutError("provider call timed out") from exc
        except urllib.error.HTTPError as exc:
            raise _map_http_error(exc) from exc
        except urllib.error.URLError as exc:
            raise ProviderGenerationError(_redact_error(str(exc))) from exc
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ProviderSchemaError("provider returned malformed JSON") from exc
        if not isinstance(parsed, dict):
            raise ProviderSchemaError("provider response must be a JSON object")
        return parsed

    def _parse_response(
        self,
        raw: dict[str, Any],
        *,
        request: ProviderCallRequest,
    ) -> ProviderResponse:
        choices = raw.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ProviderSchemaError("provider response missing choices")
        choice = choices[0]
        if not isinstance(choice, dict):
            raise ProviderSchemaError("provider choice must be an object")
        message = choice.get("message")
        if not isinstance(message, dict):
            raise ProviderSchemaError("provider response missing message")
        content = message.get("content")
        tool_calls = message.get("tool_calls") or []
        if content is None:
            content = ""
        if not isinstance(content, str):
            raise ProviderSchemaError("provider message content must be a string")
        return ProviderResponse(
            provider_id=self.provider.provider_id,
            model=str(raw.get("model") or request.model),
            content=content,
            finish_reason=choice.get("finish_reason"),
            usage=raw.get("usage") if isinstance(raw.get("usage"), dict) else None,
            raw_response_hash=None,
            tool_calls=tool_calls if isinstance(tool_calls, list) else [],
        )

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.provider.api_key_env:
            secret = self.env.get(self.provider.api_key_env)
            if not secret:
                raise ProviderAuthError("provider secret env var is not configured")
            headers["Authorization"] = f"Bearer {secret}"
        return headers

    def _chat_completions_url(self) -> str:
        base = str(self.provider.base_url).rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        return f"{base}/chat/completions"


def _messages_with_system(messages: list[ChatMessage], system: str | None) -> list[ChatMessage]:
    if not system:
        return messages
    return [ChatMessage(role="system", content=system), *messages]


def _map_http_error(exc: urllib.error.HTTPError) -> ProviderGenerationError:
    if exc.code in {401, 403}:
        return ProviderAuthError("provider authentication failed")
    if exc.code == 429:
        return ProviderRateLimitError("provider rate limited the request")
    return ProviderGenerationError(f"provider HTTP error {exc.code}")


def _redact_error(message: str) -> str:
    return message.replace("Authorization", "[REDACTED]").replace("Bearer ", "Bearer [REDACTED] ")
