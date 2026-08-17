from __future__ import annotations

from datetime import UTC, datetime

from imperaos.control_plane.provider_registry import build_provider_governance_snapshot


def test_provider_registry_snapshot_defaults_external_providers_fail_closed(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    snapshot = build_provider_governance_snapshot(
        profile="enterprise",
        generated_at=datetime(2026, 6, 13, 12, 0, tzinfo=UTC),
    )

    assert snapshot.contract_version == "control-plane.provider-governance/v1"
    assert snapshot.overall_status == "conditional"
    providers = {item.provider_kind: item for item in snapshot.providers}

    assert providers["ollama"].credential_state == "not_required"
    assert providers["transformers"].credential_state == "not_required"

    openai = providers["openai_responses"]
    assert openai.status == "blocked"
    assert openai.credential_state == "missing"
    assert openai.canary_only is True
    assert openai.server_tools_policy == "denied"
    assert openai.custom_tools_policy == "proposal_only"
    assert openai.retention_policy == "hash_only_store_false"
    assert "blocked_external_credentials" in openai.blocking_reasons

    anthropic = providers["anthropic_messages"]
    assert anthropic.status == "blocked"
    assert anthropic.credential_state == "missing"
    assert anthropic.canary_only is True
    assert anthropic.server_tools_policy == "denied"
    assert anthropic.custom_tools_policy == "proposal_only"
    assert anthropic.retention_policy == "hash_only_store_false"


def test_provider_registry_redacts_configured_external_credentials(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret-value")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-secret-value")

    snapshot = build_provider_governance_snapshot(profile="enterprise")
    payload = snapshot.model_dump(mode="json", by_alias=True)
    serialized = str(payload)

    assert "sk-test-secret-value" not in serialized
    assert "anthropic-secret-value" not in serialized
    providers = {item["providerKind"]: item for item in payload["providers"]}
    assert providers["openai_responses"]["credentialState"] == "redacted"
    assert providers["anthropic_messages"]["credentialState"] == "redacted"
