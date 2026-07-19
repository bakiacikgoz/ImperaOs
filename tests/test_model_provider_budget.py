from __future__ import annotations

from datetime import UTC, datetime

from imperaos.model_providers.budget import evaluate_provider_budget
from imperaos.model_providers.models import ProviderPolicy


def test_budget_disabled_denies_canary() -> None:
    decision = evaluate_provider_budget(
        provider_id="openai-public",
        policy=ProviderPolicy(provider_id="openai-public", canary_call_budget=0),
        prompt_chars=10,
    )

    assert not decision.allowed
    assert decision.reason_code == "PROVIDER_CANARY_BUDGET_DISABLED"


def test_budget_prompt_limit_denies_before_call() -> None:
    decision = evaluate_provider_budget(
        provider_id="openai-public",
        policy=ProviderPolicy(
            provider_id="openai-public",
            canary_call_budget=1,
            max_prompt_chars=5,
        ),
        prompt_chars=6,
    )

    assert decision.reason_code == "PROVIDER_BUDGET_PROMPT_TOO_LARGE"


def test_rate_limit_window_denies_when_full(tmp_path) -> None:
    state_path = tmp_path / "budget.json"
    policy = ProviderPolicy(
        provider_id="openai-public",
        canary_call_budget=2,
        rate_limit_per_minute=1,
    )
    now = datetime(2026, 6, 10, 8, 0, tzinfo=UTC)
    first = evaluate_provider_budget(
        provider_id="openai-public",
        policy=policy,
        prompt_chars=10,
        state_path=state_path,
        now=now,
        persist=True,
    )
    second = evaluate_provider_budget(
        provider_id="openai-public",
        policy=policy,
        prompt_chars=10,
        state_path=state_path,
        now=now,
    )

    assert first.allowed
    assert second.reason_code == "PROVIDER_RATE_LIMITED"
