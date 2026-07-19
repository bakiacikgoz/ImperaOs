from __future__ import annotations

import re

from imperaos.model_providers.models import (
    ChatMessage,
    DataClass,
    ProviderCallRequest,
    ProviderPolicyDecision,
    RedactedProviderInput,
    RedactionSummary,
    stable_hash_text,
)

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
SECRET_RE = re.compile(r"\b(?:sk|pk|rk|ak)-[A-Za-z0-9_\-]{12,}\b")
BEARER_RE = re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{12,}\b", re.IGNORECASE)


def redact_provider_input(
    *,
    request: ProviderCallRequest,
    decision: ProviderPolicyDecision,
) -> RedactedProviderInput:
    raw_text = _request_text(request)
    replacements: dict[str, int] = {}

    def redact_text(value: str) -> str:
        result = value
        result, count = EMAIL_RE.subn("[REDACTED_EMAIL]", result)
        replacements["email"] = replacements.get("email", 0) + count
        result, count = SECRET_RE.subn("[REDACTED_SECRET]", result)
        replacements["secret"] = replacements.get("secret", 0) + count
        result, count = BEARER_RE.subn("Bearer [REDACTED_TOKEN]", result)
        replacements["bearer_token"] = replacements.get("bearer_token", 0) + count
        return result

    if decision.redaction_required:
        messages = [
            ChatMessage(role=item.role, content=redact_text(item.content), name=item.name)
            for item in request.messages
        ]
        system = redact_text(request.system) if request.system else None
    else:
        messages = list(request.messages)
        system = request.system

    redacted_text = "\n".join([system or "", *[item.content for item in messages]])
    data_classes = list(request.data_classes)
    if replacements and DataClass.RAW_PII in data_classes:
        data_classes = [
            DataClass.PII_REDACTED if item == DataClass.RAW_PII else item
            for item in data_classes
        ]

    return RedactedProviderInput(
        messages=messages,
        system=system,
        data_classes=data_classes,
        summary=RedactionSummary(
            applied=decision.redaction_required and any(replacements.values()),
            replacements={key: value for key, value in replacements.items() if value},
            input_sha256=stable_hash_text(raw_text),
            redacted_sha256=stable_hash_text(redacted_text),
        ),
    )


def _request_text(request: ProviderCallRequest) -> str:
    return "\n".join([request.system or "", *[item.content for item in request.messages]])
