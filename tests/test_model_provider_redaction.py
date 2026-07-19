from __future__ import annotations

from imperaos.model_providers.models import (
    ChatMessage,
    DataClass,
    ProviderCallRequest,
    ProviderDecisionStatus,
    ProviderPolicyDecision,
)
from imperaos.model_providers.redaction import redact_provider_input


def test_redaction_removes_email_and_secret_markers() -> None:
    request = ProviderCallRequest(
        call_id="call",
        run_id="run",
        provider_id="remote",
        model="model",
        messages=[
            ChatMessage(role="user", content="mail me at user@example.com with sk-1234567890abcdef")
        ],
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

    assert "user@example.com" not in redacted.messages[0].content
    assert "sk-1234567890abcdef" not in redacted.messages[0].content
    assert redacted.summary.replacements["email"] == 1
    assert redacted.summary.replacements["secret"] == 1
