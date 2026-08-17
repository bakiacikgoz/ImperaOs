from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from imperaos.model_providers.adapters.openai_compatible import OpenAICompatibleProvider
from imperaos.model_providers.errors import (
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderSchemaError,
)
from imperaos.model_providers.models import (
    AuthMode,
    ChatMessage,
    DataBoundary,
    ModelProviderRecord,
    ProviderCallRequest,
    ProviderKind,
    RetentionPolicy,
)


class _Handler(BaseHTTPRequestHandler):
    status_code = 200
    response_payload: object = {
        "model": "mock-model",
        "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
    }
    seen_auth: str | None = None

    def do_POST(self):  # noqa: N802
        type(self).seen_auth = self.headers.get("Authorization")
        self.rfile.read(int(self.headers.get("Content-Length", "0")))
        self.send_response(type(self).status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        payload = type(self).response_payload
        if isinstance(payload, str):
            self.wfile.write(payload.encode("utf-8"))
        else:
            self.wfile.write(json.dumps(payload).encode("utf-8"))

    def log_message(self, *args):  # noqa: ANN002
        return


@pytest.fixture()
def server():
    _Handler.status_code = 200
    _Handler.response_payload = {
        "model": "mock-model",
        "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
    }
    _Handler.seen_auth = None
    httpd = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}/v1"
    finally:
        httpd.shutdown()
        thread.join(timeout=5)


def _provider(base_url: str) -> ModelProviderRecord:
    return ModelProviderRecord(
        provider_id="mock-openai-compatible",
        kind=ProviderKind.OPENAI_COMPATIBLE,
        enabled=True,
        base_url=base_url,
        api_key_env="MOCK_API_KEY",
        auth_mode=AuthMode.BEARER_ENV,
        default_model="mock-model",
        data_boundary=DataBoundary.INTERNAL,
        retention_policy=RetentionPolicy.CUSTOMER_CONTROLLED,
    )


def _request() -> ProviderCallRequest:
    return ProviderCallRequest(
        call_id="call",
        run_id="run",
        provider_id="mock-openai-compatible",
        model="mock-model",
        messages=[ChatMessage(role="user", content="hello")],
    )


def test_openai_compatible_generate_maps_response(server) -> None:
    adapter = OpenAICompatibleProvider(
        provider=_provider(server),
        env={"MOCK_API_KEY": "sk-test-secret-value"},
    )

    response = adapter.generate(_request())

    assert response.content == "ok"
    assert _Handler.seen_auth == "Bearer sk-test-secret-value"


def test_openai_compatible_missing_secret_raises_auth(server) -> None:
    adapter = OpenAICompatibleProvider(provider=_provider(server), env={})

    with pytest.raises(ProviderAuthError):
        adapter.generate(_request())


def test_openai_compatible_429_maps_rate_limit(server) -> None:
    _Handler.status_code = 429
    adapter = OpenAICompatibleProvider(provider=_provider(server), env={"MOCK_API_KEY": "value"})

    with pytest.raises(ProviderRateLimitError):
        adapter.generate(_request())


def test_openai_compatible_invalid_json_maps_schema(server) -> None:
    _Handler.response_payload = "{not-json"
    adapter = OpenAICompatibleProvider(provider=_provider(server), env={"MOCK_API_KEY": "value"})

    with pytest.raises(ProviderSchemaError):
        adapter.generate(_request())
