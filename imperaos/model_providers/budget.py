from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from imperaos.model_providers.models import ProviderBudgetDecision, ProviderPolicy


def evaluate_provider_budget(
    *,
    provider_id: str,
    policy: ProviderPolicy,
    prompt_chars: int,
    state_path: str | Path | None = None,
    now: datetime | None = None,
    persist: bool = False,
) -> ProviderBudgetDecision:
    current = now or datetime.now(UTC)
    path = Path(state_path) if state_path is not None else None
    state = _load_state(path) if path is not None else {}
    provider_state = state.get(provider_id, {}) if isinstance(state, dict) else {}
    window_started = _parse_dt(provider_state.get("window_started_at")) or current
    calls_in_window = int(provider_state.get("calls_in_window") or 0)
    canary_calls_today = int(provider_state.get("canary_calls_today") or 0)

    if current - window_started >= timedelta(minutes=1):
        window_started = current
        calls_in_window = 0

    if prompt_chars > policy.max_prompt_chars:
        return _decision(
            provider_id=provider_id,
            policy=policy,
            prompt_chars=prompt_chars,
            calls_in_window=calls_in_window,
            state_path=path,
            status="denied",
            reason_code="PROVIDER_BUDGET_PROMPT_TOO_LARGE",
        )
    if policy.canary_call_budget <= 0:
        return _decision(
            provider_id=provider_id,
            policy=policy,
            prompt_chars=prompt_chars,
            calls_in_window=calls_in_window,
            state_path=path,
            status="denied",
            reason_code="PROVIDER_CANARY_BUDGET_DISABLED",
        )
    if canary_calls_today >= policy.canary_call_budget:
        return _decision(
            provider_id=provider_id,
            policy=policy,
            prompt_chars=prompt_chars,
            calls_in_window=calls_in_window,
            state_path=path,
            status="denied",
            reason_code="PROVIDER_CANARY_BUDGET_EXCEEDED",
        )
    if policy.rate_limit_per_minute <= 0 or calls_in_window >= policy.rate_limit_per_minute:
        return _decision(
            provider_id=provider_id,
            policy=policy,
            prompt_chars=prompt_chars,
            calls_in_window=calls_in_window,
            state_path=path,
            status="denied",
            reason_code="PROVIDER_RATE_LIMITED",
        )

    if persist and path is not None:
        state[provider_id] = {
            "window_started_at": window_started.isoformat(),
            "calls_in_window": calls_in_window + 1,
            "canary_calls_today": canary_calls_today + 1,
            "updated_at": current.isoformat(),
        }
        _write_state(path, state)

    return _decision(
        provider_id=provider_id,
        policy=policy,
        prompt_chars=prompt_chars,
        calls_in_window=calls_in_window,
        state_path=path,
        status="allow",
        reason_code="PROVIDER_BUDGET_ALLOWED",
        allowed=True,
    )


def _decision(
    *,
    provider_id: str,
    policy: ProviderPolicy,
    prompt_chars: int,
    calls_in_window: int,
    state_path: Path | None,
    status: str,
    reason_code: str,
    allowed: bool = False,
) -> ProviderBudgetDecision:
    return ProviderBudgetDecision(
        status=status,
        reason_code=reason_code,
        provider_id=provider_id,
        prompt_chars=prompt_chars,
        max_prompt_chars=policy.max_prompt_chars,
        canary_call_budget=policy.canary_call_budget,
        rate_limit_per_minute=policy.rate_limit_per_minute,
        calls_in_window=calls_in_window,
        state_path=str(state_path) if state_path is not None else None,
        allowed=allowed,
    )


def _load_state(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _write_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _parse_dt(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed
