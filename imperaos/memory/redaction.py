from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from imperaos.memory.models import sha256_text

SECRET_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)\b(api[_-]?key|token|secret|password)\s*[:=]\s*[A-Za-z0-9._/-]{8,}"),
    re.compile(r"(?i)Authorization:\s*Bearer\s+[A-Za-z0-9._-]+"),
]

PII_PATTERNS = [
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    re.compile(r"\+?\d[\d .().-]{8,}\d"),
]


@dataclass(slots=True)
class MemoryRedactionResult:
    redacted_summary: str
    content_hash: str
    policy_tags: list[str]
    secret_detected: bool
    pii_detected: bool
    raw_content_included: bool = False


class MemoryRedactor:
    def redact_candidate(
        self,
        *,
        candidate_text: str,
        source_metadata: dict[str, Any] | None = None,
        privacy_mode: bool = True,
    ) -> MemoryRedactionResult:
        _ = source_metadata
        text = " ".join(candidate_text.strip().split())
        secret_detected = any(pattern.search(text) for pattern in SECRET_PATTERNS)
        pii_detected = any(pattern.search(text) for pattern in PII_PATTERNS)
        tags: list[str] = []

        redacted = text
        if privacy_mode:
            for pattern in SECRET_PATTERNS:
                redacted = pattern.sub("[REDACTED_SECRET]", redacted)
            for pattern in PII_PATTERNS:
                redacted = pattern.sub("[REDACTED_PII]", redacted)

        if secret_detected:
            tags.append("secret_suspected")
        if pii_detected:
            tags.append("pii_redacted")
        if privacy_mode:
            tags.append("privacy_mode")

        redacted = redacted[:4000]
        return MemoryRedactionResult(
            redacted_summary=redacted,
            content_hash=sha256_text(redacted),
            policy_tags=tags,
            secret_detected=secret_detected,
            pii_detected=pii_detected,
            raw_content_included=False,
        )
