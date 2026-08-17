from __future__ import annotations

from pathlib import Path

from imperaos.model_providers.envelope import (
    ProviderCallEnvelopeWriter,
    build_provider_call_envelope,
)
from imperaos.model_providers.models import (
    ChatMessage,
    DataClass,
    ProviderCallRequest,
    ProviderDecisionStatus,
    ProviderPolicyDecision,
)
from imperaos.model_providers.redaction import redact_provider_input


def test_fake_api_key_does_not_leak_to_envelope(tmp_path: Path) -> None:
    fake_key = "sk-test-secret-value-do-not-print"
    request = ProviderCallRequest(
        call_id="call-no-secret",
        run_id="run",
        provider_id="remote",
        model="model",
        messages=[ChatMessage(role="user", content=f"use {fake_key}")],
        data_classes=[DataClass.PUBLIC],
    )
    decision = ProviderPolicyDecision(
        status=ProviderDecisionStatus.ALLOW_WITH_REDACTION,
        reason_code="PROVIDER_REDACTION_REQUIRED",
        provider_id="remote",
        effective_data_classes=[DataClass.PUBLIC],
        redaction_required=True,
        approval_required=False,
        evidence_required=True,
        fallback_allowed=False,
        safe_to_call_provider=True,
        user_message="ok",
    )
    redacted = redact_provider_input(request=request, decision=decision)
    envelope = build_provider_call_envelope(
        request=request,
        decision=decision,
        provider_kind="openai_compatible",
        redacted_input=redacted,
        response=None,
        error=None,
        attempts=[],
    )
    path = ProviderCallEnvelopeWriter(tmp_path).write(envelope)

    assert fake_key not in path.read_text(encoding="utf-8")
