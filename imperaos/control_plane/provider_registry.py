from __future__ import annotations

import os
from datetime import UTC, datetime

from imperaos.control_plane.models import (
    ProviderGovernanceSnapshot,
    ProviderRegistryEntry,
)


def _external_credential_state(env_name: str) -> tuple[str, list[str]]:
    if os.environ.get(env_name):
        return "redacted", []
    return "missing", ["blocked_external_credentials"]


def build_provider_governance_snapshot(
    *,
    profile: str,
    generated_at: datetime | None = None,
) -> ProviderGovernanceSnapshot:
    del profile
    openai_state, openai_reasons = _external_credential_state("OPENAI_API_KEY")
    anthropic_state, anthropic_reasons = _external_credential_state("ANTHROPIC_API_KEY")
    providers = [
        ProviderRegistryEntry(
            providerKind="ollama",
            displayName="Ollama Local",
            status="conditional",
            credentialState="not_required",
            canaryOnly=False,
            supportsStreaming=True,
            serverToolsPolicy="denied",
            customToolsPolicy="proposal_only",
            retentionPolicy="hash_only_store_false",
            lastConformanceStatus="unknown",
            blockingReasons=[],
        ),
        ProviderRegistryEntry(
            providerKind="transformers",
            displayName="Transformers Local",
            status="conditional",
            credentialState="not_required",
            canaryOnly=False,
            supportsStreaming=False,
            serverToolsPolicy="denied",
            customToolsPolicy="proposal_only",
            retentionPolicy="hash_only_store_false",
            lastConformanceStatus="unknown",
            blockingReasons=[],
        ),
        ProviderRegistryEntry(
            providerKind="openai_responses",
            displayName="OpenAI Responses Native Preview",
            status="canary_only" if openai_state == "redacted" else "blocked",
            credentialState=openai_state,
            canaryOnly=True,
            supportsStreaming=True,
            serverToolsPolicy="denied",
            customToolsPolicy="proposal_only",
            retentionPolicy="hash_only_store_false",
            lastConformanceStatus="pass",
            blockingReasons=openai_reasons,
        ),
        ProviderRegistryEntry(
            providerKind="anthropic_messages",
            displayName="Anthropic Claude Messages Native Preview",
            status="canary_only" if anthropic_state == "redacted" else "blocked",
            credentialState=anthropic_state,
            canaryOnly=True,
            supportsStreaming=True,
            serverToolsPolicy="denied",
            customToolsPolicy="proposal_only",
            retentionPolicy="hash_only_store_false",
            lastConformanceStatus="pass",
            blockingReasons=anthropic_reasons,
        ),
    ]
    blocking = sorted({reason for provider in providers for reason in provider.blocking_reasons})
    return ProviderGovernanceSnapshot(
        generatedAtUtc=generated_at or datetime.now(UTC),
        providers=providers,
        overallStatus="conditional" if providers else "blocked",
        blockingReasons=blocking,
    )


def inspect_provider_entry(provider_kind: str, *, profile: str) -> ProviderRegistryEntry:
    snapshot = build_provider_governance_snapshot(profile=profile)
    for provider in snapshot.providers:
        if provider.provider_kind == provider_kind:
            return provider
    raise KeyError(provider_kind)
