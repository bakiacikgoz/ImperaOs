from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from typing import Any
from uuid import uuid4

SENSITIVE_KEY_MARKERS = {
    "input",
    "user_input",
    "assistant_output",
    "prompt",
    "content",
    "text",
    "snippet",
    "raw_payload",
    "stdout",
    "stderr",
    "secret",
    "token",
    "password",
    "api_key",
    "key",
}


def redact_trace_payload(
    data: dict[str, Any],
    *,
    pii_patterns: list[str] | None = None,
) -> dict[str, Any]:
    salt = uuid4().hex
    patterns = [re.compile(pattern, flags=re.IGNORECASE) for pattern in (pii_patterns or [])]
    return _redact_obj(data, salt=salt, patterns=patterns, mode="trace", key_path=())


def redact_audit_payload(
    data: dict[str, Any],
    *,
    pii_patterns: list[str] | None = None,
) -> dict[str, Any]:
    secret = os.getenv("IMPERAOS_AUDIT_SECRET", "imperaos-dev-secret")
    patterns = [re.compile(pattern, flags=re.IGNORECASE) for pattern in (pii_patterns or [])]
    return _redact_obj(data, salt=secret, patterns=patterns, mode="audit", key_path=())


def fingerprint_args(args: list[str], *, pii_patterns: list[str] | None = None) -> str:
    payload = redact_audit_payload({"args": args}, pii_patterns=pii_patterns)
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _redact_obj(
    obj: Any,
    *,
    salt: str,
    patterns: list[re.Pattern[str]],
    mode: str,
    key_path: tuple[str, ...],
) -> Any:
    if isinstance(obj, dict):
        return {
            str(key): _redact_obj(
                value,
                salt=salt,
                patterns=patterns,
                mode=mode,
                key_path=(*key_path, str(key)),
            )
            for key, value in obj.items()
        }
    if isinstance(obj, list):
        return [
            _redact_obj(
                item,
                salt=salt,
                patterns=patterns,
                mode=mode,
                key_path=(*key_path, "[]"),
            )
            for item in obj
        ]
    if isinstance(obj, str):
        return _redact_text(
            obj,
            salt=salt,
            patterns=patterns,
            mode=mode,
            key_path=key_path,
        )
    return obj


def _redact_text(
    text: str,
    *,
    salt: str,
    patterns: list[re.Pattern[str]],
    mode: str,
    key_path: tuple[str, ...],
) -> dict[str, Any] | str:
    if not text:
        return ""
    matched = any(pattern.search(text) for pattern in patterns)
    forced = _is_sensitive_key(key_path)
    if not matched and not forced:
        return text
    digest = _hash_text(text, salt=salt, mode=mode)
    return {
        "type": "redacted_text",
        "len": len(text),
        "hash": digest,
        "matched_pii": matched,
    }


def _hash_text(text: str, *, salt: str, mode: str) -> str:
    encoded = text.encode("utf-8")
    if mode == "audit":
        return hmac.new(salt.encode("utf-8"), encoded, hashlib.sha256).hexdigest()
    return hashlib.sha256((salt + text).encode("utf-8")).hexdigest()


def _is_sensitive_key(key_path: tuple[str, ...]) -> bool:
    if not key_path:
        return False
    last = key_path[-1].lower()
    return any(marker in last for marker in SENSITIVE_KEY_MARKERS)
