from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel, ConfigDict, Field

from imperaos.computer_use.models import ActionCategory, RiskClass


class BrowserAllowlistPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    allowlisted_domains: list[str] = Field(default_factory=list)
    sensitive_keywords: list[str] = Field(
        default_factory=lambda: [
            "login",
            "mfa",
            "password",
            "payment",
            "billing",
            "bank",
            "wallet",
            "admin",
            "security",
            "secret",
        ]
    )
    low_risk_actions: list[ActionCategory] = Field(
        default_factory=lambda: [ActionCategory.READ_ONLY]
    )
    raw_evidence_allowed: bool = False
    confidence_threshold: float = Field(default=0.86, ge=0.0, le=1.0)

    def allows_url(self, url: str) -> bool:
        normalized = url.strip().lower()
        return any(
            normalized.startswith(f"https://{domain.lower()}")
            or normalized.startswith(f"http://{domain.lower()}")
            or f".{domain.lower()}/" in normalized
            for domain in self.allowlisted_domains
        )

    def detects_sensitive_surface(self, url: str, target_ref: str = "") -> bool:
        haystack = f"{url} {target_ref}".lower()
        return any(keyword in haystack for keyword in self.sensitive_keywords)

    def risk_for_category(self, category: ActionCategory) -> RiskClass:
        if category in self.low_risk_actions:
            return RiskClass.LOW
        if category == ActionCategory.MUTATION:
            return RiskClass.MEDIUM
        if category == ActionCategory.HIGH_RISK:
            return RiskClass.CRITICAL
        return RiskClass.MEDIUM

    def approval_required(self, category: ActionCategory) -> bool:
        return category not in self.low_risk_actions

    def policy_hash(self) -> str:
        raw = json.dumps(self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
