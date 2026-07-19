from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from imperaos.control_plane.models import (
    NativeRequestEnvelope,
    ProviderCapabilities,
    ProviderPolicyDecision,
    ProviderRetentionPolicy,
    ProviderToolPolicy,
)

PROVIDER_POLICY_HASH = "sha256:provider-governance-v1"


def stable_hash_payload(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode(
        "utf-8"
    )
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def strict_retention_policy() -> ProviderRetentionPolicy:
    return ProviderRetentionPolicy(store=False, evidenceMode="hash_only", rawPersistence=False)


def strict_tool_policy(
    *,
    server_tools: list[str] | None = None,
    custom_tools_requested: bool = False,
) -> ProviderToolPolicy:
    _ = custom_tools_requested
    return ProviderToolPolicy(
        serverToolsPolicy="denied",
        customToolsPolicy="proposal_only",
        requestedServerTools=server_tools or [],
    )


def external_provider_capabilities(*, supports_streaming: bool) -> ProviderCapabilities:
    return ProviderCapabilities(
        supportsStreaming=supports_streaming,
        supportsServerTools=False,
        supportsCustomTools=True,
        supportsStoreFalse=True,
    )


def evaluate_provider_policy(
    envelope: NativeRequestEnvelope,
    *,
    profile: str,
) -> ProviderPolicyDecision:
    del profile
    reasons: list[str] = []
    payload = envelope.native_payload

    if envelope.raw_persistence or envelope.retention_policy.raw_persistence:
        reasons.append("PROVIDER_RAW_PERSISTENCE_DENIED")
    if envelope.retention_policy.store or payload.get("store") is True:
        reasons.append("PROVIDER_RETENTION_POLICY_VIOLATION")
    if envelope.retention_policy.evidence_mode != "hash_only":
        reasons.append("PROVIDER_EVIDENCE_HASH_ONLY_REQUIRED")
    if envelope.tool_policy.requested_server_tools:
        reasons.append("PROVIDER_SERVER_TOOLS_DENIED")
    if envelope.tool_policy.server_tools_policy != "denied":
        reasons.append("PROVIDER_SERVER_TOOLS_POLICY_UNSAFE")
    if envelope.tool_policy.custom_tools_policy != "proposal_only":
        reasons.append("PROVIDER_CUSTOM_TOOLS_MUST_BE_PROPOSAL_ONLY")

    decision = "deny" if reasons else "allow"
    return ProviderPolicyDecision(
        decision=decision,
        reasonCodes=sorted(set(reasons)) or ["PROVIDER_POLICY_PASS"],
        policyHash=PROVIDER_POLICY_HASH,
    )
