from __future__ import annotations

from imperaos.model_providers.canary import run_provider_canary
from imperaos.model_providers.models import DataClass, ProviderCanaryRequest
from imperaos.model_providers.registry import resolve_model_provider_registry
from imperaos.runtime.config import RuntimeConfig


def _registry():
    config = RuntimeConfig.from_profile("enterprise")
    return resolve_model_provider_registry(config=config, profile="enterprise")


def test_canary_skips_without_double_opt_in(tmp_path) -> None:
    result = run_provider_canary(
        request=ProviderCanaryRequest(
            provider_id="openai-public",
            profile="enterprise",
            data_classes=[DataClass.PUBLIC],
            allow_live=False,
            evidence_root=str(tmp_path),
        ),
        registry=_registry(),
        env={},
        evidence_root=tmp_path,
    )

    assert result.status == "skipped"
    assert result.reason_code == "PROVIDER_LIVE_CANARY_DISABLED"
    assert not result.live_call_attempted


def test_public_cloud_confidential_denied_before_adapter(tmp_path) -> None:
    result = run_provider_canary(
        request=ProviderCanaryRequest(
            provider_id="openai-public",
            profile="enterprise",
            data_classes=[DataClass.CONFIDENTIAL],
            allow_live=True,
            evidence_root=str(tmp_path),
        ),
        registry=_registry(),
        env={"IMPERAOS_PROVIDER_LIVE_CANARY": "1"},
        evidence_root=tmp_path,
    )

    assert result.status == "denied"
    assert result.reason_code == "PROVIDER_DATA_BOUNDARY_DENIED"
    assert not result.live_call_attempted
