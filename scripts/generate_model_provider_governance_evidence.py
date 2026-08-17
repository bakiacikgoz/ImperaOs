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
    from scripts.run_provider_governance_gate import run_gate
except ModuleNotFoundError:
    from run_provider_governance_gate import run_gate

DEFAULT_OUTPUT_DIR = Path("artifacts/model-provider-governance/v1")


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _policy_payload(*, registry, provider_id: str, data_class: DataClass) -> dict[str, Any]:
    provider = registry.get(provider_id)
    if provider is None:
        return {
            "contractVersion": "model_provider.policy_decision/v1",
            "providerId": provider_id,
            "reasonCode": "PROVIDER_NOT_FOUND",
            "safeToCallProvider": False,
        }
    decision = evaluate_provider_policy(
        request=ProviderCallRequest(
            call_id=f"evidence-{provider_id}-{data_class}",
            run_id="provider-governance-evidence",
            provider_id=provider.provider_id,
            model=provider.default_model,
            messages=[ChatMessage(role="user", content="public governance evidence prompt")],
            data_classes=[data_class],
        ),
        provider=provider,
        policy=registry.policy_for(provider.provider_id),
        governance_context=GovernanceContext(remote_providers_enabled=True),
    )
    return {
        "contractVersion": "model_provider.policy_decision/v1",
        "generatedAtUtc": _now(),
        "providerId": decision.provider_id,
        "status": str(decision.status),
        "reasonCode": decision.reason_code,
        "safeToCallProvider": decision.safe_to_call_provider,
        "redactionRequired": decision.redaction_required,
        "effectiveDataClasses": [str(item) for item in decision.effective_data_classes],
        "userMessage": decision.user_message,
    }


def generate_evidence(*, profile: str, output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    config = RuntimeConfig.from_profile(profile)
    registry = resolve_model_provider_registry(config=config, profile=profile)

    gate = run_gate(profile=profile, output_dir=output_dir)
    registry_snapshot = registry.model_dump(mode="json")
    for provider in registry_snapshot["providers"]:
        provider.pop("api_key", None)

    public_local = _policy_payload(
        registry=registry,
        provider_id="local-ollama" if registry.get("local-ollama") else "local-transformers",
        data_class=DataClass.PUBLIC,
    )
    confidential_cloud = _policy_payload(
        registry=registry,
        provider_id="openai-public",
        data_class=DataClass.CONFIDENTIAL,
    )

    request = ProviderCallRequest(
        call_id="provider-envelope-sample",
        run_id="provider-governance-evidence",
        provider_id="openai-public",
        model="model",
        messages=[ChatMessage(role="user", content="email user@example.com with sk-test-secret")],
        data_classes=[DataClass.PUBLIC],
    )
    decision = ProviderPolicyDecision(
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
    redacted = redact_provider_input(request=request, decision=decision)
    envelope = build_provider_call_envelope(
        request=request,
        decision=decision,
        provider_kind="openai_compatible",
        redacted_input=redacted,
        response=None,
        error=None,
        attempts=[],
    )
    envelope_path = ProviderCallEnvelopeWriter(output_dir).write(envelope)
    envelope_sample_path = output_dir / "provider-envelope-sample.redacted.json"
    envelope_path.replace(envelope_sample_path)

    ui_summary = {
        "contractVersion": "operator-panel.provider-governance-ui/v1",
        "generatedAtUtc": _now(),
        "statesCovered": [
            "loading",
            "empty",
            "local_ready",
            "remote_disabled",
            "auth_env_missing",
            "policy_blocked",
            "malformed_bridge_response",
        ],
        "primaryUiRawJson": False,
    }

    _write_json(output_dir / "provider-registry-snapshot.redacted.json", registry_snapshot)
    _write_json(output_dir / "provider-policy-simulation-public-local.json", public_local)
    _write_json(
        output_dir / "provider-policy-simulation-confidential-public-cloud-blocked.json",
        confidential_cloud,
    )
    _write_json(output_dir / "provider-ui-snapshot-summary.json", ui_summary)

    closure = _closure_markdown(profile=profile, gate=gate, output_dir=output_dir)
    (output_dir / "PROVIDER_GOVERNANCE_V1_CLOSURE.md").write_text(closure, encoding="utf-8")

    return {
        "version": "model_provider.governance_evidence/v1",
        "status": gate["status"],
        "outputDir": output_dir.as_posix(),
        "files": sorted(path.name for path in output_dir.iterdir() if path.is_file()),
    }


def _closure_markdown(*, profile: str, gate: dict[str, Any], output_dir: Path) -> str:
    return "\n".join(
        [
            "# Provider Governance V1 Closure",
            "",
            f"- Generated at: {_now()}",
            f"- Profile: `{profile}`",
            f"- Gate status: `{gate['status']}`",
            f"- Evidence root: `{output_dir.as_posix()}`",
            "",
            "## Closure Answers",
            "",
            f"- Remote providers default disabled: `{not gate['remoteProvidersEnabled']}`",
            "- Secrets in artifacts/log evidence: `not detected by provider gate`",
            "- Raw prompt/response in provider envelopes: `not persisted`",
            "- Legacy provider chain: `covered by legacy provider/config tests`",
            "- Operator Panel provider state: `covered by provider UI tests and browser smoke`",
            "- Live network required by default: `false`",
            "",
            "## Known Limits",
            "",
            "- Provider registry is read-only in Operator Panel.",
            "- Remote live canary remains opt-in and outside the default gate.",
            "- Native provider adapters beyond OpenAI-compatible are V2 work.",
            "",
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate provider governance V1 evidence.")
    parser.add_argument("--profile", default="enterprise")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)

    result = generate_evidence(profile=args.profile, output_dir=args.output_dir)
    if args.json_output:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"status={result['status']} output_dir={result['outputDir']}")
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
