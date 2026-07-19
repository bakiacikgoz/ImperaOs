from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

PROVIDER_ID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{1,63}$")
ENV_NAME_PATTERN = re.compile(r"^[A-Z0-9_]{3,128}$")


class ProviderKind(StrEnum):
    LOCAL_OLLAMA = "local_ollama"
    LOCAL_TRANSFORMERS = "local_transformers"
    OPENAI_COMPATIBLE = "openai_compatible"
    OPENAI_RESPONSES = "openai_responses"
    ANTHROPIC_MESSAGES = "anthropic_messages"
    OPENAI = "openai"
    AZURE_OPENAI = "azure_openai"
    ANTHROPIC = "anthropic"
    GOOGLE_GEMINI = "google_gemini"
    DEEPSEEK = "deepseek"
    OPENROUTER = "openrouter"
    CUSTOM_HTTP = "custom_http"
    COMPANY_INTERNAL_API = "company_internal_api"


class AuthMode(StrEnum):
    NONE = "none"
    BEARER_ENV = "bearer_env"
    CUSTOM_HEADER_ENV = "custom_header_env"
    AZURE_AD = "azure_ad"
    MANAGED_IDENTITY = "managed_identity"


class DataBoundary(StrEnum):
    LOCAL = "local"
    INTERNAL = "internal"
    PRIVATE_CLOUD = "private_cloud"
    PUBLIC_CLOUD = "public_cloud"
    AGGREGATOR = "aggregator"
    UNKNOWN = "unknown"


class RetentionPolicy(StrEnum):
    NONE_CLAIMED = "none_claimed"
    ZERO_RETENTION = "zero_retention"
    PROVIDER_DEFAULT = "provider_default"
    CUSTOMER_CONTROLLED = "customer_controlled"
    UNKNOWN = "unknown"


class RiskTier(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    BLOCKED = "blocked"


class DataClass(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    REGULATED = "regulated"
    PII_REDACTED = "pii_redacted"
    RAW_PII = "raw_pii"
    SECRET = "secret"
    CREDENTIAL = "credential"
    PAYMENT = "payment"


class ProviderDecisionStatus(StrEnum):
    ALLOW = "allow"
    ALLOW_WITH_REDACTION = "allow_with_redaction"
    REQUIRE_APPROVAL = "require_approval"
    DENY = "deny"
    BLOCKED_NOT_CONFIGURED = "blocked_not_configured"


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str = Field(pattern=r"^(system|user|assistant|tool)$")
    content: str = Field(default="", max_length=200_000)
    name: str | None = Field(default=None, max_length=120)


class ToolSpec(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str = Field(max_length=120)
    description: str | None = Field(default=None, max_length=2000)


class ProviderModelInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    display_name: str | None = None
    configured: bool = False
    installed: bool = False
    source: str = "config"
    warnings: list[str] = Field(default_factory=list)


class ProviderHealth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    reason_code: str
    message: str
    checked_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ModelProviderRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: str
    kind: ProviderKind
    enabled: bool = False
    display_name: str | None = Field(default=None, max_length=120)
    base_url: HttpUrl | None = None
    api_key_env: str | None = None
    auth_mode: AuthMode = AuthMode.NONE
    default_model: str = Field(max_length=160)
    models: list[str] = Field(default_factory=list)
    data_boundary: DataBoundary = DataBoundary.LOCAL
    retention_policy: RetentionPolicy = RetentionPolicy.UNKNOWN
    data_residency: str | None = Field(default=None, max_length=80)
    supports_streaming: bool = False
    supports_json_mode: bool = False
    supports_json_schema: bool = False
    supports_tool_calling: bool = False
    supports_vision: bool = False
    cost_policy_id: str | None = Field(default=None, max_length=80)
    fallback_priority: int = Field(default=100, ge=0, le=999)
    risk_tier: RiskTier | None = None

    @field_validator("provider_id")
    @classmethod
    def _validate_provider_id(cls, value: str) -> str:
        if not PROVIDER_ID_PATTERN.match(value):
            raise ValueError("provider_id must match ^[a-zA-Z0-9][a-zA-Z0-9_.-]{1,63}$")
        return value

    @field_validator("api_key_env")
    @classmethod
    def _validate_api_key_env(cls, value: str | None) -> str | None:
        if value is not None and not ENV_NAME_PATTERN.match(value):
            raise ValueError("api_key_env must be an environment variable name")
        return value

    @model_validator(mode="after")
    def _validate_remote_shape(self) -> ModelProviderRecord:
        remote_kinds = {
            ProviderKind.OPENAI_COMPATIBLE,
            ProviderKind.OPENAI_RESPONSES,
            ProviderKind.ANTHROPIC_MESSAGES,
            ProviderKind.OPENAI,
            ProviderKind.AZURE_OPENAI,
            ProviderKind.ANTHROPIC,
            ProviderKind.GOOGLE_GEMINI,
            ProviderKind.DEEPSEEK,
            ProviderKind.OPENROUTER,
            ProviderKind.CUSTOM_HTTP,
            ProviderKind.COMPANY_INTERNAL_API,
        }
        if self.kind in remote_kinds and self.base_url is None:
            raise ValueError("remote providers require base_url")
        if self.auth_mode != AuthMode.NONE and not self.api_key_env:
            raise ValueError("auth_mode requires api_key_env")
        if (
            self.data_boundary in {DataBoundary.PUBLIC_CLOUD, DataBoundary.AGGREGATOR}
            and self.base_url is not None
            and self.base_url.scheme != "https"
        ):
            raise ValueError("public cloud and aggregator providers require https base_url")
        if self.risk_tier is None:
            inferred = {
                DataBoundary.LOCAL: RiskTier.LOW,
                DataBoundary.INTERNAL: RiskTier.MEDIUM,
                DataBoundary.PRIVATE_CLOUD: RiskTier.MEDIUM,
                DataBoundary.PUBLIC_CLOUD: RiskTier.HIGH,
                DataBoundary.AGGREGATOR: RiskTier.HIGH,
                DataBoundary.UNKNOWN: RiskTier.BLOCKED,
            }[self.data_boundary]
            self.risk_tier = inferred
        return self

    def safe_dump(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")
        payload.pop("api_key", None)
        return payload


class ProviderPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: str
    allowed_data_classes: list[DataClass] = Field(default_factory=list)
    blocked_data_classes: list[DataClass] = Field(
        default_factory=lambda: [
            DataClass.SECRET,
            DataClass.CREDENTIAL,
            DataClass.PAYMENT,
            DataClass.RAW_PII,
        ]
    )
    requires_redaction: bool = True
    allow_tool_calls: bool = False
    requires_approval_for_tool_calls: bool = True
    allow_streaming: bool = True
    max_input_tokens: int | None = Field(default=None, ge=1)
    max_prompt_chars: int = Field(default=12_000, ge=1)
    max_output_tokens: int | None = Field(default=None, ge=1)
    timeout_ms: int = Field(default=15_000, ge=1_000, le=300_000)
    max_retries: int = Field(default=0, ge=0, le=5)
    daily_call_budget: int = Field(default=1_000, ge=0)
    canary_call_budget: int = Field(default=0, ge=0)
    rate_limit_per_minute: int = Field(default=10, ge=0)
    allowed_hosts: list[str] = Field(default_factory=list)
    daily_cost_limit_usd: float | None = Field(default=None, ge=0.0)
    fallback_allowed_to: list[str] = Field(default_factory=list)
    evidence_required: bool = True


class ProviderCallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    call_id: str
    run_id: str
    provider_id: str
    model: str
    messages: list[ChatMessage] = Field(default_factory=list)
    system: str | None = None
    data_classes: list[DataClass] = Field(default_factory=lambda: [DataClass.PUBLIC])
    json_mode: bool = False
    json_schema: dict[str, Any] | None = None
    tools: list[ToolSpec] = Field(default_factory=list)
    stream: bool = False
    timeout_s: float = Field(default=60.0, ge=1.0, le=300.0)
    idempotency_key: str | None = None


class ProviderPolicyDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ProviderDecisionStatus
    reason_code: str
    provider_id: str
    effective_data_classes: list[DataClass]
    redaction_required: bool
    approval_required: bool
    evidence_required: bool
    fallback_allowed: bool
    safe_to_call_provider: bool
    user_message: str
    internal_detail: str | None = None


class RedactionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    applied: bool = False
    replacements: dict[str, int] = Field(default_factory=dict)
    input_sha256: str | None = None
    redacted_sha256: str | None = None


class RedactedProviderInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    messages: list[ChatMessage]
    system: str | None = None
    data_classes: list[DataClass]
    summary: RedactionSummary


class ProviderAttempt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: str
    provider_kind: ProviderKind | str
    success: bool
    status_code: int | None = None
    reason_code: str | None = None
    error: str | None = None
    latency_ms: int | None = None


class ProviderResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: str
    model: str
    content: str
    finish_reason: str | None = None
    usage: dict[str, Any] | None = None
    raw_response_hash: str | None = None
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)


class ProviderStreamEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event: str
    delta: str = ""
    finish_reason: str | None = None


class ProviderCallEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "model_provider.call_envelope/v1"
    call_id: str
    run_id: str
    provider_id: str
    provider_kind: str
    model: str
    data_classes: list[DataClass]
    prompt_hash: str
    system_hash: str | None = None
    redaction_summary: RedactionSummary
    policy_decision: ProviderPolicyDecision
    request_metadata: dict[str, Any]
    response_hash: str | None = None
    usage: dict[str, Any] | None = None
    attempts: list[ProviderAttempt] = Field(default_factory=list)
    created_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at_utc: datetime | None = None


class ProviderBudgetDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    reason_code: str
    provider_id: str
    prompt_chars: int
    max_prompt_chars: int
    canary_call_budget: int
    rate_limit_per_minute: int
    calls_in_window: int = 0
    allowed: bool = False
    state_path: str | None = None


class ProviderNetworkDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    reason_code: str
    provider_id: str
    scheme: str | None = None
    host: str | None = None
    data_boundary: DataBoundary
    allowed_hosts: list[str] = Field(default_factory=list)
    allowed: bool = False


class ProviderCanaryStatus(StrEnum):
    SKIPPED = "skipped"
    DENIED = "denied"
    PASS = "pass"
    FAIL = "fail"


class ProviderCanaryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: str
    profile: str = "balanced"
    data_classes: list[DataClass] = Field(default_factory=lambda: [DataClass.PUBLIC])
    prompt_fixture_id: str = "public_smoke"
    allow_live: bool = False
    evidence_root: str = "artifacts/model-provider-governance/canary"


class ProviderCanaryResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = "model_provider.canary_result/v1"
    canary_id: str
    provider_id: str
    provider_kind: ProviderKind | str
    data_boundary: DataBoundary
    risk_tier: RiskTier | str
    data_classes: list[DataClass]
    status: ProviderCanaryStatus
    reason_code: str
    live_call_attempted: bool = False
    raw_content_persisted: bool = False
    policy_decision: ProviderPolicyDecision | None = None
    redaction_summary: RedactionSummary | None = None
    budget_decision: ProviderBudgetDecision | None = None
    network_decision: ProviderNetworkDecision | None = None
    request_hash: str | None = None
    response_hash: str | None = None
    status_code_class: str | None = None
    latency_ms: int | None = None
    usage: dict[str, Any] | None = None
    retry_count: int = 0
    error_class: str | None = None
    evidence_path: str | None = None
    generated_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ProviderRouteShadowRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_type: str = "chat"
    data_classes: list[DataClass] = Field(default_factory=lambda: [DataClass.PUBLIC])
    required_capabilities: list[str] = Field(default_factory=list)
    preferred_provider_id: str | None = None


class ProviderRouteCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: str
    provider_kind: ProviderKind | str
    data_boundary: DataBoundary
    risk_tier: RiskTier | str
    allowed: bool
    reason_code: str
    score: int


class ProviderRouteShadowDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = "model_provider.router_shadow/v1"
    shadow_only: bool = True
    task_type: str
    data_classes: list[DataClass]
    required_capabilities: list[str]
    requested_provider_id: str | None = None
    recommended_provider_id: str | None = None
    fallback_provider_id: str | None = None
    allowed_providers: list[str] = Field(default_factory=list)
    blocked_providers: list[ProviderRouteCandidate] = Field(default_factory=list)
    candidates: list[ProviderRouteCandidate] = Field(default_factory=list)
    reason_code: str
    evidence_path: str | None = None
    generated_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ProviderConformanceStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    SKIPPED = "skipped"


class ProviderConformanceCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    check_id: str
    status: ProviderConformanceStatus
    reason_code: str
    summary: str
    evidence: dict[str, Any] = Field(default_factory=dict)


class ProviderConformanceEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: str
    provider_kind: ProviderKind | str
    data_boundary: DataBoundary
    risk_tier: RiskTier | str
    enabled: bool
    summary_status: ProviderConformanceStatus
    pass_count: int
    skipped_count: int
    fail_count: int
    checks: list[ProviderConformanceCheck]


class ProviderConformanceMatrix(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = "model_provider.conformance_matrix/v1"
    profile: str
    mode: str = Field(pattern=r"^(offline|live)$")
    remote_providers_enabled: bool = False
    providers: list[ProviderConformanceEntry]
    generated_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))


class NativeAdapterV2ToolPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_tools_allowed: bool = False
    server_tools_allowed: bool = False
    approval_required: bool = True
    reason_code: str = "NATIVE_ADAPTER_SERVER_TOOLS_DENY_BY_DEFAULT"


class NativeAdapterV2Request(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = "model_provider.native_adapter_request/v2"
    call_id: str
    run_id: str
    provider_id: str
    model: str
    messages: list[ChatMessage] = Field(default_factory=list)
    data_classes: list[DataClass] = Field(default_factory=lambda: [DataClass.PUBLIC])
    json_schema: dict[str, Any] | None = None
    stream: bool = False
    tool_policy: NativeAdapterV2ToolPolicy = Field(default_factory=NativeAdapterV2ToolPolicy)
    canary_only: bool = True


class NativeAdapterV2Response(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = "model_provider.native_adapter_response/v2"
    call_id: str
    provider_id: str
    model: str
    status: str = Field(pattern=r"^(skipped|denied|pass|fail)$")
    reason_code: str
    content_hash: str | None = None
    usage: dict[str, Any] | None = None
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    raw_content_persisted: bool = False
    generated_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ResolvedProviderRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    contract_version: str = "model_provider.registry/v1"
    profile: str
    remote_providers_enabled: bool = False
    providers: list[ModelProviderRecord]
    policies: list[ProviderPolicy] = Field(default_factory=list)
    generated_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def get(self, provider_id: str) -> ModelProviderRecord | None:
        return next((item for item in self.providers if item.provider_id == provider_id), None)

    def policy_for(self, provider_id: str) -> ProviderPolicy:
        explicit = next((item for item in self.policies if item.provider_id == provider_id), None)
        if explicit is not None:
            return explicit
        provider = self.get(provider_id)
        if provider is None:
            return ProviderPolicy(provider_id=provider_id)
        if provider.data_boundary == DataBoundary.LOCAL:
            return ProviderPolicy(
                provider_id=provider_id,
                allowed_data_classes=[
                    DataClass.PUBLIC,
                    DataClass.INTERNAL,
                    DataClass.CONFIDENTIAL,
                    DataClass.REGULATED,
                    DataClass.PII_REDACTED,
                ],
                requires_redaction=False,
                evidence_required=False,
                canary_call_budget=25,
                rate_limit_per_minute=10,
            )
        if provider.data_boundary in {DataBoundary.INTERNAL, DataBoundary.PRIVATE_CLOUD}:
            return ProviderPolicy(
                provider_id=provider_id,
                allowed_data_classes=[DataClass.PUBLIC, DataClass.INTERNAL],
                requires_redaction=True,
                evidence_required=True,
                canary_call_budget=5,
                rate_limit_per_minute=2,
            )
        if provider.data_boundary == DataBoundary.PUBLIC_CLOUD:
            return ProviderPolicy(
                provider_id=provider_id,
                allowed_data_classes=[DataClass.PUBLIC],
                requires_redaction=True,
                evidence_required=True,
                canary_call_budget=1,
                rate_limit_per_minute=1,
            )
        return ProviderPolicy(
            provider_id=provider_id,
            requires_redaction=True,
            evidence_required=True,
        )


def stable_hash_text(value: str | None) -> str | None:
    if value is None:
        return None
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()
