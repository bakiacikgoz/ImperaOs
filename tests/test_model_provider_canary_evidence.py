from __future__ import annotations

import json

from imperaos.model_providers.canary_evidence import (
    verify_canary_evidence_root,
    write_canary_evidence,
)
from imperaos.model_providers.models import (
    DataBoundary,
    DataClass,
    ProviderCanaryResult,
    ProviderCanaryStatus,
    ProviderKind,
    RiskTier,
)


def _result() -> ProviderCanaryResult:
    return ProviderCanaryResult(
        canary_id="provider-canary-local",
        provider_id="local-ollama",
        provider_kind=ProviderKind.LOCAL_OLLAMA,
        data_boundary=DataBoundary.LOCAL,
        risk_tier=RiskTier.LOW,
        data_classes=[DataClass.PUBLIC],
        status=ProviderCanaryStatus.SKIPPED,
        reason_code="PROVIDER_LIVE_CANARY_DISABLED",
        request_hash="sha256:abc",
    )


def test_canary_evidence_write_and_verify_pass(tmp_path) -> None:
    write_canary_evidence(result=_result(), evidence_root=tmp_path)

    verify = verify_canary_evidence_root(tmp_path)

    assert verify["status"] == "pass"


def test_canary_evidence_secret_marker_fails(tmp_path) -> None:
    payload = _result().model_dump(mode="json")
    payload["leak"] = "sk-test-secret-value"
    (tmp_path / "bad.json").write_text(json.dumps(payload), encoding="utf-8")

    verify = verify_canary_evidence_root(tmp_path)

    assert verify["status"] == "fail"
    assert verify["issues"][0]["reason"] == "PROVIDER_CANARY_SECRET_OR_PII_MARKER"
