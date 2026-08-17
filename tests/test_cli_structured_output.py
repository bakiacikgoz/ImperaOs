from __future__ import annotations

import json

from typer.testing import CliRunner

from imperaos.cli import app
from imperaos.schemas.models import OrchestratorResult

runner = CliRunner()


class FakeOrchestrator:
    def process_fast_chat(
        self,
        user_input: str,
        session_context: dict[str, str] | None = None,
        *,
        stream: bool = False,
        candidate_reason: str = "short_message",
        on_token=None,
    ) -> OrchestratorResult:
        del session_context, candidate_reason
        if stream and on_token is not None:
            on_token("Mer")
            on_token("haba")
        return OrchestratorResult(
            final_text="Merhaba",
            used_path="llm_stream_fast" if stream else "llm_only_fast",
            fallback_events=[],
            trace_id="trace-fast",
            metrics={"fast_path_taken": True},
        )

    def process(
        self,
        user_input: str,
        session_context: dict[str, str] | None = None,
        use_router: bool = True,
    ) -> OrchestratorResult:
        del user_input, session_context, use_router
        return OrchestratorResult(
            final_text="normal",
            used_path="llm_only",
            fallback_events=[],
            trace_id="trace-normal",
            metrics={"fast_path_taken": False},
        )

    def trace_events(self, request_id: str) -> list[dict[str, object]]:
        return [
            {"request_id": request_id, "stage": "request_received", "data": {}},
            {"request_id": request_id, "stage": "final_response", "data": {}},
        ]


def test_chat_json_stream_emits_token_and_final(monkeypatch) -> None:
    monkeypatch.setattr("imperaos.cli._build_orchestrator", lambda *a, **k: FakeOrchestrator())
    result = runner.invoke(
        app,
        ["chat", "--profile", "lite", "--once", "selam", "--json-stream", "--stream"],
    )

    assert result.exit_code == 0
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    events = [json.loads(line)["event"] for line in lines]
    assert "token" in events
    assert "final" in events


def test_chat_json_emits_single_payload(monkeypatch) -> None:
    monkeypatch.setattr("imperaos.cli._build_orchestrator", lambda *a, **k: FakeOrchestrator())
    result = runner.invoke(
        app,
        ["chat", "--profile", "lite", "--once", "selam", "--json", "--no-stream"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["final_text"] in {"Merhaba", "normal"}
    assert "trace_events" in payload
