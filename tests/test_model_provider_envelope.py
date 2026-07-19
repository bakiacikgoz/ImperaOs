from __future__ import annotations

import json

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


def test_envelope_contains_hashes_not_raw_prompt(tmp_path) -> None:
    request = ProviderCallRequest(
        call_id="call-envelope",
        run_id="run",
        provider_id="openai-public",
        model="model",
        messages=[ChatMessage(role="user", content="secret prompt user@example.com")],
        data_classes=[DataClass.PUBLIC],
    )
    decision = ProviderPolicyDecision(
        status=ProviderDecisionStatus.ALLOW_WITH_REDACTION,
        reason_code="PROVIDER_REDACTION_REQUIRED",
        provider_id="openai-public",
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
    text = path.read_text(encoding="utf-8")
    payload = json.loads(text)

    assert payload["prompt_hash"].startswith("sha256:")
    assert "secret prompt" not in text
    assert "user@example.com" not in text
