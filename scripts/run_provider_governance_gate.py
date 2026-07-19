from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from imperaos.model_providers.envelope import (
    ProviderCallEnvelopeWriter,
    build_provider_call_envelope,
)
from imperaos.model_providers.models import (
    ChatMessage,
    DataBoundary,
    DataClass,
    ProviderCallRequest,
    ProviderDecisionStatus,
    ProviderPolicyDecision,
)
from imperaos.model_providers.policy import GovernanceContext, evaluate_provider_policy
from imperaos.model_providers.redaction import redact_provider_input
from imperaos.model_providers.registry import resolve_model_provider_registry
from imperaos.runtime.config import RuntimeConfig

try:
    from scripts.generate_provider_canary_evidence import generate_canary_evidence
except ModuleNotFoundError:
    from generate_provider_canary_evidence import generate_canary_evidence

FORBIDDEN_MARKERS = (
    "sk-",
    "Bearer ",
    "Authorization:",
    "raw_prompt",
    "raw_response",
    "raw_messages",
)


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _request(provider_id: str, model: str, data_classes: list[DataClass]) -> ProviderCallRequest:
    return ProviderCallRequest(
        call_id=f"gate-{provider_id}-{'-'.join(str(item) for item in data_classes)}",
        run_id="provider-governance-gate",
        provider_id=provider_id,
        model=model,
        messages=[ChatMessage(role="user", content="public provider governance gate prompt")],
        data_classes=data_classes,
    )


def run_gate(*, profile: str, output_dir: Path | None = None) -> dict[str, Any]:
    config = RuntimeConfig.from_profile(profile)
    registry = resolve_model_provider_registry(config=config, profile=profile)
    blocking_reasons: list[str] = []
    warnings: list[str] = []

    if registry.remote_providers_enabled:
        blocking_reasons.append("remote_providers_enabled_by_default")

    for provider in registry.providers:
        if provider.data_boundary in {DataBoundary.PUBLIC_CLOUD, DataBoundary.AGGREGATOR}:
            if provider.enabled:
                blocking_reasons.append(f"public_cloud_provider_enabled:{provider.provider_id}")
            if provider.base_url is not None and provider.base_url.scheme != "https":
                blocking_reasons.append(f"public_cloud_provider_not_https:{provider.provider_id}")
        if provider.api_key_env:
            provider_json = json.dumps(provider.safe_dump(), sort_keys=True)
            if "sk-" in provider_json or "Bearer " in provider_json:
                blocking_reasons.append(f"secret_value_in_provider_record:{provider.provider_id}")

    local = registry.get("local-ollama") or registry.get("local-transformers")
    if local is None:
        blocking_reasons.append("local_provider_missing")
    else:
        decision = evaluate_provider_policy(
            request=_request(local.provider_id, local.default_model, [DataClass.CONFIDENTIAL]),
            provider=local,
            policy=registry.policy_for(local.provider_id),
            governance_context=GovernanceContext(remote_providers_enabled=False),
        )
        if not decision.safe_to_call_provider:
            blocking_reasons.append("local_confidential_not_allowed")

    public = registry.get("openai-public")
    if public is None:
        warnings.append("openai_public_fixture_missing")
    else:
        decision = evaluate_provider_policy(
            request=_request(public.provider_id, public.default_model, [DataClass.CONFIDENTIAL]),
            provider=public,
            policy=registry.policy_for(public.provider_id),
            governance_context=GovernanceContext(remote_providers_enabled=True),
        )
        if (
            decision.safe_to_call_provider
            or decision.reason_code != "PROVIDER_DATA_BOUNDARY_DENIED"
        ):
            blocking_reasons.append("public_cloud_confidential_not_denied")

    secret_sample = "sk-test-secret-value-do-not-print"
    request = ProviderCallRequest(
        call_id="gate-envelope-redaction-sample",
        run_id="provider-governance-gate",
        provider_id="openai-public",
        model="model",
        messages=[ChatMessage(role="user", content=f"use {secret_sample} with user@example.com")],
        data_classes=[DataClass.PUBLIC],
    )
    redaction_decision = ProviderPolicyDecision(
        status=ProviderDecisionStatus.ALLOW_WITH_REDACTION,
        reason_code="PROVIDER_REDACTION_REQUIRED",
        provider_id=request.provider_id,
        effective_data_classes=[DataClass.PUBLIC],
        redaction_required=True,
        approval_required=False,
        evidence_required=True,
        fallback_allowed=False,
        safe_to_call_provider=True,
        user_message="Provider call is allowed only after redaction.",
    )
    redacted = redact_provider_input(request=request, decision=redaction_decision)
    envelope = build_provider_call_envelope(
        request=request,
        decision=redaction_decision,
        provider_kind="openai_compatible",
        redacted_input=redacted,
        response=None,
        error=None,
        attempts=[],
    )
    envelope_text = json.dumps(envelope.model_dump(mode="json"), sort_keys=True)
    if secret_sample in envelope_text or "user@example.com" in envelope_text:
        blocking_reasons.append("raw_sensitive_text_in_envelope_sample")

    canary_output_dir = (
        output_dir / "canary"
        if output_dir is not None
        else Path("artifacts/model-provider-governance/canary")
    )
    canary_gate = generate_canary_evidence(profile=profile, output_dir=canary_output_dir)
    canary_verify = canary_gate["verify"]
    if canary_verify["status"] != "pass":
        blocking_reasons.append("provider_canary_evidence_verify_failed")

    scan_paths = [
        Path("artifacts/model-provider-governance"),
        Path("artifacts/model-provider-calls"),
    ]
    for root in scan_paths:
        if not root.exists():
            continue
        for path in root.glob("**/*.json"):
            text = path.read_text(encoding="utf-8", errors="ignore")
            if any(marker in text for marker in FORBIDDEN_MARKERS):
                blocking_reasons.append(f"forbidden_marker_in_artifact:{path.as_posix()}")

    status = "pass" if not blocking_reasons else "fail"
    report: dict[str, Any] = {
        "version": "model_provider.governance_gate/v1",
        "generatedAtUtc": _now(),
        "profile": profile,
        "status": status,
        "remoteProvidersEnabled": registry.remote_providers_enabled,
        "blockingReasons": blocking_reasons,
        "warnings": warnings,
        "checks": {
            "remoteDefaultDisabled": not registry.remote_providers_enabled,
            "publicCloudConfidentialDenied": "public_cloud_confidential_not_denied"
            not in blocking_reasons,
            "localConfidentialAllowed": "local_confidential_not_allowed" not in blocking_reasons,
            "redactedEnvelopeSample": "raw_sensitive_text_in_envelope_sample"
            not in blocking_reasons,
            "artifactSecretScan": not any(
                item.startswith("forbidden_marker_in_artifact") for item in blocking_reasons
            ),
            "providerCanaryEvidenceVerified": "provider_canary_evidence_verify_failed"
            not in blocking_reasons,
        },
    }

    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        gate_path = output_dir / "provider-governance-gate.json"
        gate_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        ProviderCallEnvelopeWriter(output_dir).write(envelope)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the provider governance V1 gate.")
    parser.add_argument("--profile", default="enterprise")
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args(argv)

    report = run_gate(profile=args.profile, output_dir=args.output_dir)
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"status={report['status']} profile={report['profile']}")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
