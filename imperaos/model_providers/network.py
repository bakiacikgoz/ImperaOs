from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

from imperaos.model_providers.models import (
    DataBoundary,
    ModelProviderRecord,
    ProviderNetworkDecision,
    ProviderPolicy,
)


def evaluate_provider_network(
    *,
    provider: ModelProviderRecord,
    policy: ProviderPolicy,
) -> ProviderNetworkDecision:
    if provider.base_url is None:
        return ProviderNetworkDecision(
            status="allow",
            reason_code="PROVIDER_NETWORK_LOCAL",
            provider_id=provider.provider_id,
            data_boundary=provider.data_boundary,
            allowed=True,
        )
    parsed = urlparse(str(provider.base_url))
    host = (parsed.hostname or "").lower()
    allowed_hosts = [item.lower() for item in policy.allowed_hosts]
    if not parsed.scheme or not host:
        return _deny(provider, policy, "PROVIDER_HOST_INVALID", parsed.scheme, host)
    if provider.data_boundary in {DataBoundary.PUBLIC_CLOUD, DataBoundary.AGGREGATOR}:
        if parsed.scheme != "https":
            return _deny(provider, policy, "PROVIDER_PUBLIC_TLS_REQUIRED", parsed.scheme, host)
        if host not in allowed_hosts:
            return _deny(provider, policy, "PROVIDER_HOST_NOT_ALLOWLISTED", parsed.scheme, host)
    elif provider.data_boundary in {DataBoundary.INTERNAL, DataBoundary.PRIVATE_CLOUD}:
        if host not in allowed_hosts and not _is_local_or_private_host(host):
            return _deny(provider, policy, "PROVIDER_HOST_NOT_ALLOWLISTED", parsed.scheme, host)
    elif provider.data_boundary == DataBoundary.UNKNOWN:
        return _deny(provider, policy, "PROVIDER_DATA_BOUNDARY_UNKNOWN", parsed.scheme, host)
    return ProviderNetworkDecision(
        status="allow",
        reason_code="PROVIDER_HOST_ALLOWED",
        provider_id=provider.provider_id,
        scheme=parsed.scheme,
        host=host,
        data_boundary=provider.data_boundary,
        allowed_hosts=allowed_hosts,
        allowed=True,
    )


def _deny(
    provider: ModelProviderRecord,
    policy: ProviderPolicy,
    reason_code: str,
    scheme: str | None,
    host: str | None,
) -> ProviderNetworkDecision:
    return ProviderNetworkDecision(
        status="denied",
        reason_code=reason_code,
        provider_id=provider.provider_id,
        scheme=scheme,
        host=host,
        data_boundary=provider.data_boundary,
        allowed_hosts=[item.lower() for item in policy.allowed_hosts],
        allowed=False,
    )


def _is_local_or_private_host(host: str) -> bool:
    if host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".local"):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local
