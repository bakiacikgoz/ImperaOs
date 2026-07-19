from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from imperaos.model_providers.models import DataClass, RiskTier


class NativeProviderKind(StrEnum):
    OPENAI_RESPONSES = "openai_responses"
    ANTHROPIC_MESSAGES = "anthropic_messages"
    GEMINI_NATIVE = "gemini_native"


class ProviderEvidenceMode(StrEnum):
    HASH_ONLY = "hash_only"
    REDACTED_PREVIEW = "redacted_preview"


class ProviderStoragePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: str
    remote_store_allowed: bool = False
    request_store_flag: bool = False
    cache_allowed: bool = False
    raw_payload_persistence: bool = False
    evidence_mode: ProviderEvidenceMode = ProviderEvidenceMode.HASH_ONLY


class ProviderRequestedToolType(StrEnum):
    CUSTOM_FUNCTION = "custom_function"
    BUILTIN_WEB_SEARCH = "builtin_web_search"
    BUILTIN_FILE_SEARCH = "builtin_file_search"
    BUILTIN_COMPUTER_USE = "builtin_computer_use"
    BUILTIN_CODE_EXECUTION = "builtin_code_execution"
    BUILTIN_WEB_FETCH = "builtin_web_fetch"
    BUILTIN_BASH = "builtin_bash"
    BUILTIN_TEXT_EDITOR = "builtin_text_editor"
    MCP = "mcp"
    SERVER_TOOL = "server_tool"
    UNKNOWN = "unknown"


class ProviderRequestedTool(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_type: ProviderRequestedToolType
    name: str = Field(max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    parameters: dict[str, Any] = Field(default_factory=lambda: {"type": "object"})
    arguments: dict[str, Any] = Field(default_factory=dict)
    mutating: bool = False


class ProviderToolPolicyStatus(StrEnum):
    ALLOW_PROPOSAL = "allow_proposal"
    DENY = "deny"
    REQUIRES_APPROVAL = "requires_approval"


class ProviderToolPolicyDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ProviderToolPolicyStatus
    requested_tool_type: ProviderRequestedToolType
    reason_code: str
    execution_allowed: bool = False
    proposal_allowed: bool = False
    approval_required: bool = False
    tool_name: str | None = None


class ProviderToolProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_id: str
    provider_id: str
    provider_tool_id: str | None = None
    tool_name: str
    execution_mode: str = Field(default="proposal_only", pattern=r"^proposal_only$")
    arguments_hash: str
    redacted_arguments_preview: dict[str, Any] = Field(default_factory=dict)
    data_class: DataClass = DataClass.PUBLIC
    risk_tier: RiskTier | str
    governance_action: str = Field(pattern=r"^(record_only|requires_approval|deny)$")


class ProviderStopReason(StrEnum):
    END_TURN = "end_turn"
    TOOL_USE = "tool_use"
    MAX_TOKENS = "max_tokens"
    STOP_SEQUENCE = "stop_sequence"
    PAUSE_TURN = "pause_turn"
    REFUSAL = "refusal"
    MODEL_CONTEXT_WINDOW_EXCEEDED = "model_context_window_exceeded"
    UNKNOWN = "unknown"


class ProviderContentBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    block_type: str
    text_hash: str | None = None
    tool_name: str | None = None
    tool_id: str | None = None
    arguments_hash: str | None = None


class OpenAIResponsesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = "model_provider.openai_responses_request/v1"
    provider_id: str
    model: str
    request_hash: str
    payload: dict[str, Any]
    storage_policy: ProviderStoragePolicy
    tool_policy_decisions: list[ProviderToolPolicyDecision] = Field(default_factory=list)
    raw_payload_persisted: bool = False


class OpenAIResponsesResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = "model_provider.openai_responses_result/v1"
    provider_id: str
    model: str
    status: str = Field(pattern=r"^(pass|blocked)$")
    reason_code: str
    output_text_hash: str | None = None
    structured_json_hash: str | None = None
    tool_proposals: list[ProviderToolProposal] = Field(default_factory=list)
    usage: dict[str, Any] | None = None
    latency_ms: int | None = None
    raw_response_persisted: bool = False
    generated_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AnthropicMessagesRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = "model_provider.anthropic_messages_request/v1"
    provider_id: str
    model: str
    request_hash: str
    payload: dict[str, Any]
    storage_policy: ProviderStoragePolicy
    tool_policy_decisions: list[ProviderToolPolicyDecision] = Field(default_factory=list)
    canary_only: bool = True
    live_canary_attempted: bool = False
    raw_payload_persisted: bool = False


class AnthropicMessagesResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = "model_provider.anthropic_messages_result/v1"
    provider_id: str
    model: str
    status: str = Field(pattern=r"^(pass|blocked)$")
    reason_code: str
    stop_reason: ProviderStopReason | str
    output_text_hash: str | None = None
    content_blocks: list[ProviderContentBlock] = Field(default_factory=list)
    tool_proposals: list[ProviderToolProposal] = Field(default_factory=list)
    usage: dict[str, Any] | None = None
    latency_ms: int | None = None
    tool_result_loop_supported: bool = False
    raw_response_persisted: bool = False
    generated_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ProviderNativeConformanceCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    provider_kind: NativeProviderKind = NativeProviderKind.OPENAI_RESPONSES
    mode: str = Field(default="offline_fixture", pattern=r"^offline_fixture$")
    expected_status: str = Field(pattern=r"^(pass|blocked)$")
    expected_reason_code: str | None = None
    fixture_path: str


class ProviderNativeConformanceCaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    status: str = Field(pattern=r"^(pass|blocked|fail)$")
    expected_status: str
    reason_code: str
    expected_reason_code: str | None = None
    matched_expectation: bool
    evidence: dict[str, Any] = Field(default_factory=dict)


class ProviderNativeConformanceReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = "model_provider.native_conformance/v1"
    profile: str
    provider_kind: NativeProviderKind = NativeProviderKind.OPENAI_RESPONSES
    status: str = Field(pattern=r"^(pass|fail)$")
    total_cases: int
    pass_count: int
    expected_blocked_count: int
    unexpected_failure_count: int
    cases: list[ProviderNativeConformanceCaseResult]
    generated_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))


class NativeProviderAdapter(Protocol):
    def build_payload(self, *args: Any, **kwargs: Any) -> OpenAIResponsesRequest:
        ...

    def normalize_result(self, *args: Any, **kwargs: Any) -> OpenAIResponsesResult:
        ...
