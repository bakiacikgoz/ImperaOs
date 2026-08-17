from __future__ import annotations


class ModelProviderError(RuntimeError):
    """Base class for model provider governance errors."""

    reason_code = "MODEL_PROVIDER_ERROR"


class ProviderRegistryError(ModelProviderError):
    reason_code = "INVALID_PROVIDER_REGISTRY"


class DuplicateProviderId(ProviderRegistryError):
    reason_code = "DUPLICATE_PROVIDER_ID"


class InvalidProviderConfig(ProviderRegistryError):
    reason_code = "INVALID_PROVIDER_CONFIG"


class ProviderNotFound(ModelProviderError):
    reason_code = "PROVIDER_NOT_FOUND"


class ProviderNotConfigured(ModelProviderError):
    reason_code = "PROVIDER_NOT_CONFIGURED"


class ProviderPolicyError(ModelProviderError):
    reason_code = "PROVIDER_POLICY_ERROR"


class ProviderAuthError(ModelProviderError):
    reason_code = "PROVIDER_AUTH_FAILED"


class ProviderRateLimitError(ModelProviderError):
    reason_code = "PROVIDER_RATE_LIMITED"


class ProviderTimeoutError(ModelProviderError):
    reason_code = "PROVIDER_TIMEOUT"


class ProviderSchemaError(ModelProviderError):
    reason_code = "PROVIDER_SCHEMA_ERROR"


class ProviderGenerationError(ModelProviderError):
    reason_code = "PROVIDER_GENERATION_FAILED"


REASON_CODES: dict[str, str] = {
    "PROVIDER_READY": "Provider is configured and allowed by current policy.",
    "PROVIDER_DISABLED": "Provider is disabled in the resolved registry.",
    "PROVIDER_SECRET_MISSING": "Required secret environment variable is not present.",
    "PROVIDER_NOT_FOUND": "Provider id does not exist in the resolved registry.",
    "PROVIDER_DATA_BOUNDARY_DENIED": "Provider cannot receive the requested data classes.",
    "PROVIDER_BLOCKED_DATA_CLASS": "The request contains data classes that are always blocked.",
    "PROVIDER_REDACTION_REQUIRED": "Provider call is allowed only after redaction.",
    "PROVIDER_UNSUPPORTED_CAPABILITY": (
        "The request asks for a capability the provider cannot satisfy."
    ),
    "PROVIDER_FALLBACK_DOWNGRADE_DENIED": (
        "Fallback would downgrade the data boundary without policy allow."
    ),
    "PROVIDER_REMOTE_DISABLED": "Remote provider calls are disabled by configuration.",
    "PROVIDER_AUTH_FAILED": "Provider authentication failed.",
    "PROVIDER_RATE_LIMITED": "Provider returned a rate limit response.",
    "PROVIDER_TIMEOUT": "Provider call timed out.",
    "PROVIDER_SCHEMA_ERROR": "Provider returned an invalid response shape.",
    "INVALID_PROVIDER_REGISTRY": "Provider registry config is invalid.",
    "INLINE_SECRET_REJECTED": "Raw secret values are not allowed in provider config.",
}
