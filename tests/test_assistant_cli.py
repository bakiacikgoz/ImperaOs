from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from imperaos.cli import _assistant_trace_stream_event, app

runner = CliRunner()


def test_assistant_trace_stream_event_flattens_data_and_skips_terminal_trace() -> None:
    approval = _assistant_trace_stream_event(
        {
            "stage": "approval_pending",
            "request_id": "request-1",
            "data": {
                "approval_id": "approval-1",
                "title": "Approval required",
                "risk": "medium",
            },
        }
    )

    assert approval == (
        "approval_pending",
        {
            "approval_id": "approval-1",
            "title": "Approval required",
            "risk": "medium",
            "stage": "approval_pending",
            "request_id": "request-1",
        },
    )
    assert (
        _assistant_trace_stream_event(
            {
                "stage": "final_response",
                "request_id": "request-1",
                "data": {"final_text": "duplicate"},
            }
        )
        is None
    )


def test_assistant_models_exposes_product_contract(monkeypatch) -> None:
    def fake_provider_models_payload(*, profile: str, requested_provider: str) -> dict[str, object]:
        assert profile == "enterprise"
        assert requested_provider == "all"
        return {
            "contractVersion": "operator-panel.assistant-provider-models/v4",
            "profile": profile,
            "providers": [
                {
                    "provider": "local-ollama",
                    "available": True,
                    "models": [{"id": "llama3.1", "label": "llama3.1", "source": "ollama"}],
                    "disabledReason": None,
                    "errorCode": None,
                },
                {
                    "provider": "local-transformers",
                    "available": False,
                    "models": [],
                    "disabledReason": "HF_MODEL_NOT_CONFIGURED",
                    "errorCode": "HF_MODEL_NOT_CONFIGURED",
                },
            ],
        }

    monkeypatch.setattr("imperaos.cli._provider_models_payload", fake_provider_models_payload)

    result = runner.invoke(app, ["assistant", "models", "--profile", "enterprise", "--json"])

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["schemaVersion"] == "assistant.provider-models/v1"
    assert payload["profile"] == "enterprise"
    assert payload["providers"][0]["provider"] == "local-ollama"
    assert payload["providers"][0]["status"] == "available"
    assert payload["providers"][1]["status"] == "unavailable"
    assert payload["providers"][1]["blockingReasons"] == ["HF_MODEL_NOT_CONFIGURED"]
    assert payload["selectedDefault"] == {"provider": "local-ollama", "model": "llama3.1"}


def test_assistant_doctor_reports_model_discovery_without_fake_ready(monkeypatch) -> None:
    monkeypatch.setattr(
        "imperaos.cli._provider_models_payload",
        lambda *, profile, requested_provider: {
            "profile": profile,
            "providers": [
                {
                    "provider": "local-ollama",
                    "available": False,
                    "models": [],
                    "errorCode": "OLLAMA_NOT_INSTALLED",
                    "disabledReason": None,
                }
            ],
        },
    )

    result = runner.invoke(app, ["assistant", "doctor", "--profile", "enterprise", "--json"])

    assert result.exit_code == 3, result.stdout
    payload = json.loads(result.stdout)
    assert payload["schemaVersion"] == "assistant.doctor/v1"
    assert payload["status"] == "setup_required"
    assert "ASSISTANT_MODEL_UNAVAILABLE" in payload["blockingReasons"]
    assert payload["previewFallbackAllowed"] is False


def test_assistant_turn_streams_contract_events(tmp_path: Path, monkeypatch) -> None:
    prompt_path = tmp_path / "compiled_prompt.md"
    prompt_path.write_text("Summarize the selected run.", encoding="utf-8")

    def fake_events(**kwargs):
        assert kwargs["profile"] == "enterprise"
        assert kwargs["session_id"] == "session-1"
        assert kwargs["turn_id"] == "turn-1"
        assert kwargs["prompt"] == "Summarize the selected run."
        return [
            {
                "event": "delta",
                "data": {"text": "Done"},
            },
            {
                "event": "final",
                "data": {"finalText": "Done"},
            },
        ]

    monkeypatch.setattr("imperaos.cli._assistant_turn_events", fake_events)

    result = runner.invoke(
        app,
        [
            "assistant",
            "turn",
            "--profile",
            "enterprise",
            "--session-id",
            "session-1",
            "--turn-id",
            "turn-1",
            "--prompt-file",
            str(prompt_path),
            "--stream-json",
        ],
    )

    assert result.exit_code == 0, result.stdout
    events = [json.loads(line) for line in result.stdout.splitlines()]
    assert [event["event"] for event in events] == ["text_delta", "final"]
    assert all(event["contractVersion"] == "3.0" for event in events)
    assert all(event["assistantTurnId"] == "turn-1" for event in events)
    assert [event["sequence"] for event in events] == [1, 2]
    assert [event["eventId"] for event in events] == ["turn-1-1", "turn-1-2"]
    assert all(event["traceId"] == "trace-turn-1" for event in events)
    assert all(event["dataClass"] == "internal" for event in events)
