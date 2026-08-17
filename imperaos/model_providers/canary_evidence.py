from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from imperaos.model_providers.models import ProviderCanaryResult, ProviderRouteShadowDecision

FORBIDDEN_EVIDENCE_KEYS = {"raw_prompt", "raw_response", "raw_messages", "prompt", "response"}
FORBIDDEN_TEXT_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{8,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._-]{8,}"),
    re.compile(r"Authorization\s*:", re.IGNORECASE),
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
)


def write_canary_evidence(
    *,
    result: ProviderCanaryResult,
    evidence_root: str | Path,
) -> Path:
    root = Path(evidence_root)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{result.canary_id}.json"
    payload = result.model_dump(mode="json")
    text = _safe_json(payload)
    path.write_text(text + "\n", encoding="utf-8")
    return path


def write_router_shadow_evidence(
    *,
    decision: ProviderRouteShadowDecision,
    evidence_root: str | Path = "artifacts/model-provider-governance/router-shadow",
) -> Path:
    root = Path(evidence_root)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"router-shadow-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json"
    text = _safe_json(decision.model_dump(mode="json"))
    path.write_text(text + "\n", encoding="utf-8")
    return path


def verify_canary_evidence_root(evidence_root: str | Path) -> dict[str, Any]:
    root = Path(evidence_root)
    if not root.exists():
        return _verify_result("fail", "PROVIDER_CANARY_EVIDENCE_MISSING", [], [])
    files = sorted(path for path in root.glob("*.json") if path.is_file())
    issues: list[dict[str, str]] = []
    verified: list[str] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        text_issues = scan_evidence_text(text)
        if text_issues:
            issues.extend({"path": str(path), "reason": item} for item in text_issues)
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            issues.append({"path": str(path), "reason": "PROVIDER_CANARY_EVIDENCE_INVALID_JSON"})
            continue
        key_issues = _scan_forbidden_keys(payload)
        if key_issues:
            issues.extend({"path": str(path), "reason": item} for item in key_issues)
            continue
        try:
            result = ProviderCanaryResult.model_validate(payload)
        except ValidationError:
            issues.append({"path": str(path), "reason": "PROVIDER_CANARY_SCHEMA_INVALID"})
            continue
        if result.raw_content_persisted:
            issues.append({"path": str(path), "reason": "PROVIDER_CANARY_RAW_CONTENT_PERSISTED"})
            continue
        if (
            result.data_boundary == "public_cloud"
            and result.status == "pass"
            and any(item != "public" for item in result.model_dump(mode="json")["data_classes"])
        ):
            issues.append({"path": str(path), "reason": "PROVIDER_PUBLIC_CLOUD_FORBIDDEN_DATA"})
            continue
        verified.append(str(path))
    status = "pass" if verified and not issues else "fail"
    reason = (
        "PROVIDER_CANARY_EVIDENCE_VERIFIED"
        if status == "pass"
        else "PROVIDER_CANARY_EVIDENCE_FAILED"
    )
    return _verify_result(status, reason, verified, issues)


def scan_evidence_text(text: str) -> list[str]:
    issues: list[str] = []
    for pattern in FORBIDDEN_TEXT_PATTERNS:
        if pattern.search(text):
            issues.append("PROVIDER_CANARY_SECRET_OR_PII_MARKER")
    return list(dict.fromkeys(issues))


def _safe_json(payload: dict[str, Any]) -> str:
    key_issues = _scan_forbidden_keys(payload)
    if key_issues:
        raise ValueError(",".join(key_issues))
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False)
    text_issues = scan_evidence_text(text)
    if text_issues:
        raise ValueError(",".join(text_issues))
    return text


def _scan_forbidden_keys(value: Any, path: str = "") -> list[str]:
    issues: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key)
            next_path = f"{path}.{key_text}" if path else key_text
            if key_text in FORBIDDEN_EVIDENCE_KEYS:
                issues.append(f"PROVIDER_CANARY_FORBIDDEN_KEY:{next_path}")
            issues.extend(_scan_forbidden_keys(item, next_path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            issues.extend(_scan_forbidden_keys(item, f"{path}[{index}]"))
    return issues


def _verify_result(
    status: str,
    reason_code: str,
    verified_files: list[str],
    issues: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "version": "model_provider.canary_verify/v1",
        "status": status,
        "reasonCode": reason_code,
        "verifiedFiles": verified_files,
        "issues": issues,
        "generatedAtUtc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
