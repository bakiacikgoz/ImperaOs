from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from imperaos.model_providers.models import (
    ProviderAttempt,
    ProviderCallEnvelope,
    ProviderCallRequest,
    ProviderPolicyDecision,
    ProviderResponse,
    RedactedProviderInput,
    RedactionSummary,
    stable_hash_text,
)


def build_provider_call_envelope(
    *,
    request: ProviderCallRequest,
    decision: ProviderPolicyDecision,
    provider_kind: str,
    redacted_input: RedactedProviderInput | None,
    response: ProviderResponse | None,
    error: Exception | None,
    attempts: list[ProviderAttempt],
) -> ProviderCallEnvelope:
    prompt_text = "\n".join(item.content for item in request.messages)
    response_text = response.content if response else None
    summary = redacted_input.summary if redacted_input is not None else RedactionSummary()
    if error is not None:
        attempts = [
            *attempts,
            ProviderAttempt(
                provider_id=request.provider_id,
                provider_kind=provider_kind,
                success=False,
                reason_code=getattr(error, "reason_code", "PROVIDER_GENERATION_FAILED"),
                error=_redact_error(str(error)),
            ),
        ]
    return ProviderCallEnvelope(
        call_id=request.call_id,
        run_id=request.run_id,
        provider_id=request.provider_id,
        provider_kind=provider_kind,
        model=request.model,
        data_classes=redacted_input.data_classes if redacted_input else request.data_classes,
        prompt_hash=stable_hash_text(prompt_text) or "sha256:",
        system_hash=stable_hash_text(request.system),
        redaction_summary=summary,
        policy_decision=decision,
        request_metadata={
            "message_count": len(request.messages),
            "has_system": request.system is not None,
            "json_mode": request.json_mode,
            "json_schema": request.json_schema is not None,
            "tool_count": len(request.tools),
            "stream": request.stream,
            "timeout_s": request.timeout_s,
        },
        response_hash=stable_hash_text(response_text),
        usage=response.usage if response else None,
        attempts=attempts,
        completed_at_utc=datetime.now(UTC),
    )


class ProviderCallEnvelopeWriter:
    def __init__(self, root_dir: str | Path = "artifacts/model-provider-calls"):
        self.root_dir = Path(root_dir)

    def write(self, envelope: ProviderCallEnvelope) -> Path:
        self.root_dir.mkdir(parents=True, exist_ok=True)
        path = self.root_dir / f"{envelope.call_id}.json"
        payload = envelope.model_dump(mode="json")
        text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        _assert_no_raw_sensitive_strings(text)
        path.write_text(text + "\n", encoding="utf-8")
        return path


def _redact_error(message: str) -> str:
    redacted = message
    for marker in ("Authorization", "Bearer ", "api_key", "OPENAI_API_KEY"):
        redacted = redacted.replace(marker, "[REDACTED]")
    return redacted[:500]


def _assert_no_raw_sensitive_strings(text: str) -> None:
    forbidden_markers = ("sk-", "Bearer ", "Authorization:")
    if any(marker in text for marker in forbidden_markers):
        raise ValueError("provider call envelope contains sensitive marker")
