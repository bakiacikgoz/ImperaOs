from __future__ import annotations

import re
from pathlib import Path

RAW_OR_SECRET_RE = re.compile(
    r"(sk-[A-Za-z0-9_-]+|ghp_[A-Za-z0-9_]+|xoxb-[A-Za-z0-9-]+|"
    r"OPENAI_API_KEY\s*=|ANTHROPIC_API_KEY\s*=|BEGIN PRIVATE KEY|BEGIN RAW|"
    r"rawPrompt|rawResponse|rawScreenshot|rawPromptPersisted\s*[:=]\s*true|"
    r"rawResponsePersisted\s*[:=]\s*true|rawScreenshotPersisted\s*[:=]\s*true)",
    re.I,
)


def scan_text_for_raw_or_secret(text: str) -> list[str]:
    findings: list[str] = []
    for match in RAW_OR_SECRET_RE.finditer(text):
        token = match.group(0)
        if token.lower() in {"rawpromptpersisted:false", "rawresponsepersisted:false"}:
            continue
        findings.append("RAW_OR_SECRET_MARKER_FOUND")
    return sorted(set(findings))


def scan_file_for_raw_or_secret(path: Path) -> list[str]:
    try:
        data = path.read_bytes()
    except OSError:
        return ["ARTIFACT_UNREADABLE"]
    if b"\x00" in data[:4096]:
        return []
    return scan_text_for_raw_or_secret(data.decode("utf-8", errors="ignore"))
