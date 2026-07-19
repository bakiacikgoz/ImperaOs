from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import UTC, datetime

from imperaos.model_providers.models import (
    DataBoundary,
    ModelProviderRecord,
    ProviderPolicy,
)


def doctor_provider(
    *,
    provider: ModelProviderRecord,
    policy: ProviderPolicy,
    remote_providers_enabled: bool,
    env: Mapping[str, str] | None = None,
    network_check: bool = False,
) -> dict[str, object]:
    values = env or os.environ
    secret_present = provider.api_key_env is None or provider.api_key_env in values
    status = "ready"
    reason_code = "PROVIDER_READY"
    warnings: list[str] = []

    if not provider.enabled:
        status = "blocked"
        reason_code = "PROVIDER_DISABLED"
    elif provider.data_boundary != DataBoundary.LOCAL and not remote_providers_enabled:
        status = "blocked"
        reason_code = "PROVIDER_REMOTE_DISABLED"
    elif not secret_present:
        status = "not_configured"
        reason_code = "PROVIDER_SECRET_MISSING"

    return {
        "contractVersion": "model_provider.doctor/v1",
        "providerId": provider.provider_id,
        "providerKind": provider.kind,
        "status": status,
        "reasonCode": reason_code,
        "displayName": provider.display_name or provider.provider_id,
        "capabilities": {
            "streaming": provider.supports_streaming,
            "jsonMode": provider.supports_json_mode,
            "jsonSchema": provider.supports_json_schema,
            "toolCalling": provider.supports_tool_calling,
            "vision": provider.supports_vision,
        },
        "policy": policy.model_dump(mode="json"),
        "secretRefPresent": bool(provider.api_key_env),
        "secretValuePresent": secret_present,
        "networkCheck": "skipped" if not network_check else "not_implemented",
        "models": provider.models or [provider.default_model],
        "warnings": warnings,
        "checkedAtUtc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
