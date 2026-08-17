from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from imperaos.model_providers.errors import ProviderPolicyError, ProviderSchemaError
from imperaos.model_providers.models import (
    ChatMessage,
    DataClass,
    ModelProviderRecord,
    ProviderCallRequest,
    ProviderKind,
    ProviderPolicy,
)
from imperaos.model_providers.native.anthropic_messages import (
    build_anthropic_messages_payload,
    normalize_anthropic_messages_result,
)
from imperaos.model_providers.native.openai_responses import (
    build_openai_responses_payload,
    normalize_openai_responses_result,
)
from imperaos.model_providers.native.types import (
    NativeProviderKind,
    ProviderNativeConformanceCaseResult,
    ProviderNativeConformanceReport,
    ProviderRequestedTool,
    ProviderStoragePolicy,
)

DEFAULT_NATIVE_FIXTURE_DIR = Path("contracts/model_providers/fixtures")


def run_openai_responses_native_conformance(
    *,
    profile: str,
    fixture_dir: Path = DEFAULT_NATIVE_FIXTURE_DIR,
) -> ProviderNativeConformanceReport:
    cases = sorted(fixture_dir.glob("openai_responses_*.json"))
    results = [_run_case(path) for path in cases]
    unexpected_failure_count = sum(not item.matched_expectation for item in results)
    pass_count = sum(item.status == "pass" and item.matched_expectation for item in results)
    expected_blocked_count = sum(
        item.status == "blocked" and item.matched_expectation for item in results
    )
    return ProviderNativeConformanceReport(
        profile=profile,
        provider_kind=NativeProviderKind.OPENAI_RESPONSES,
        status="pass" if unexpected_failure_count == 0 and len(results) >= 10 else "fail",
        total_cases=len(results),
        pass_count=pass_count,
        expected_blocked_count=expected_blocked_count,
        unexpected_failure_count=unexpected_failure_count,
        cases=results,
    )


def run_anthropic_messages_native_conformance(
    *,
    profile: str,
    fixture_dir: Path = DEFAULT_NATIVE_FIXTURE_DIR / "anthropic_messages",
) -> ProviderNativeConformanceReport:
    cases = sorted(fixture_dir.glob("*.json"))
    results = [_run_anthropic_case(path) for path in cases]
    unexpected_failure_count = sum(not item.matched_expectation for item in results)
    pass_count = sum(item.status == "pass" and item.matched_expectation for item in results)
    expected_blocked_count = sum(
        item.status == "blocked" and item.matched_expectation for item in results
    )
    return ProviderNativeConformanceReport(
        profile=profile,
        provider_kind=NativeProviderKind.ANTHROPIC_MESSAGES,
        status="pass" if unexpected_failure_count == 0 and len(results) >= 12 else "fail",
        total_cases=len(results),
        pass_count=pass_count,
        expected_blocked_count=expected_blocked_count,
        unexpected_failure_count=unexpected_failure_count,
        cases=results,
    )


def run_native_conformance(
    *,
    profile: str,
    provider_kind: NativeProviderKind | str,
) -> ProviderNativeConformanceReport:
    kind = NativeProviderKind(provider_kind)
    if kind == NativeProviderKind.OPENAI_RESPONSES:
        return run_openai_responses_native_conformance(profile=profile)
    if kind == NativeProviderKind.ANTHROPIC_MESSAGES:
        return run_anthropic_messages_native_conformance(profile=profile)
    raise ValueError(f"unsupported native provider kind: {provider_kind}")


def run_all_native_conformance(*, profile: str) -> list[ProviderNativeConformanceReport]:
    return [
        run_openai_responses_native_conformance(profile=profile),
        run_anthropic_messages_native_conformance(profile=profile),
    ]


def write_native_conformance_report(
    *,
    report: ProviderNativeConformanceReport,
    output_root: Path,
    stem: str = "native_adapter_gate_report",
) -> dict[str, str]:
    output_root.mkdir(parents=True, exist_ok=True)
    json_path = output_root / f"{stem}.json"
    markdown_path = output_root / f"{stem}.md"
    json_path.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(_markdown(report), encoding="utf-8")
    return {"json": json_path.as_posix(), "markdown": markdown_path.as_posix()}


def verify_native_conformance_evidence(
    *,
    output_root: Path | None = None,
    input_path: Path | None = None,
) -> dict[str, Any]:
    violations: list[str] = []
    forbidden = ("raw_prompt", "raw_response", "Authorization:", "Bearer ", "sk-")
    paths = [input_path] if input_path is not None else list((output_root or Path()).glob("**/*"))
    for path in paths:
        if path is None:
            continue
        if not path.is_file() or path.suffix.lower() not in {".json", ".md"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if any(marker in text for marker in forbidden):
            violations.append(path.as_posix())
    return {
        "status": "pass" if not violations else "fail",
        "reasonCode": (
            "NATIVE_EVIDENCE_SAFE" if not violations else "NATIVE_EVIDENCE_FORBIDDEN_MARKER"
        ),
        "violations": violations,
    }


def _run_case(path: Path) -> ProviderNativeConformanceCaseResult:
    fixture = json.loads(path.read_text(encoding="utf-8"))
    case_id = str(fixture["case_id"])
    expected_status = str(fixture["expected_status"])
    expected_reason_code = fixture.get("expected_reason_code")
    try:
        status, reason_code, evidence = _execute_fixture(fixture)
    except (ProviderPolicyError, ProviderSchemaError, ValidationError, ValueError) as exc:
        status = "blocked"
        reason_code = str(exc) or exc.__class__.__name__
        evidence = {"blocked": True}
    matched = status == expected_status and (
        expected_reason_code is None or reason_code == expected_reason_code
    )
    return ProviderNativeConformanceCaseResult(
        case_id=case_id,
        status=status if matched else "fail",
        expected_status=expected_status,
        reason_code=reason_code,
        expected_reason_code=expected_reason_code,
        matched_expectation=matched,
        evidence={"fixture": path.as_posix(), **evidence},
    )


def _run_anthropic_case(path: Path) -> ProviderNativeConformanceCaseResult:
    fixture = json.loads(path.read_text(encoding="utf-8"))
    case_id = str(fixture["case_id"])
    expected_status = str(fixture["expected_status"])
    expected_reason_code = fixture.get("expected_reason_code")
    try:
        status, reason_code, evidence = _execute_anthropic_fixture(fixture)
    except (ProviderPolicyError, ProviderSchemaError, ValidationError, ValueError) as exc:
        status = "blocked"
        reason_code = str(exc) or exc.__class__.__name__
        evidence = {"blocked": True}
    matched = status == expected_status and (
        expected_reason_code is None or reason_code == expected_reason_code
    )
    return ProviderNativeConformanceCaseResult(
        case_id=case_id,
        status=status if matched else "fail",
        expected_status=expected_status,
        reason_code=reason_code,
        expected_reason_code=expected_reason_code,
        matched_expectation=matched,
        evidence={"fixture": path.as_posix(), **evidence},
    )


def _execute_fixture(fixture: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    if fixture.get("simulate") == "timeout":
        return "blocked", "OPENAI_RESPONSES_TIMEOUT_FIXTURE", {"networkAttempted": False}
    provider = _provider()
    policy = ProviderPolicy.model_validate(
        {
            "provider_id": provider.provider_id,
            "allowed_data_classes": ["public"],
            "blocked_data_classes": [
                "internal",
                "confidential",
                "regulated",
                "raw_pii",
                "secret",
                "credential",
                "payment",
            ],
            "requires_redaction": True,
            "allow_tool_calls": True,
            "requires_approval_for_tool_calls": True,
            "max_output_tokens": 256,
            "canary_call_budget": 1,
            "rate_limit_per_minute": 1,
            "allowed_hosts": ["api.openai.com"],
        }
    )
    request = _request(fixture)
    storage_policy = ProviderStoragePolicy.model_validate(
        {"provider_id": provider.provider_id, **fixture.get("storage_policy", {})}
    )
    requested_tools = [
        ProviderRequestedTool.model_validate(item) for item in fixture.get("requested_tools", [])
    ]
    started = time.perf_counter()
    native_request = build_openai_responses_payload(
        provider=provider,
        policy=policy,
        request=request,
        storage_policy=storage_policy,
        requested_tools=requested_tools,
    )
    provider_response = fixture.get("provider_response")
    if provider_response is None:
        return "pass", "OPENAI_RESPONSES_PAYLOAD_BUILT", _safe_evidence(native_request)
    result = normalize_openai_responses_result(
        request=native_request,
        provider_response=provider_response,
        started_at_monotonic=started,
    )
    return result.status, result.reason_code, {
        **_safe_evidence(native_request),
        "toolProposalCount": len(result.tool_proposals),
        "hasTextHash": result.output_text_hash is not None,
        "hasStructuredJsonHash": result.structured_json_hash is not None,
        "rawResponsePersisted": result.raw_response_persisted,
    }


def _execute_anthropic_fixture(fixture: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    if fixture.get("simulate") == "live_canary_guard":
        allow_live = bool(fixture.get("allow_live", False))
        provider_live = bool(fixture.get("provider_live_env", False))
        anthropic_live = bool(fixture.get("anthropic_live_env", False))
        if not (allow_live and provider_live and anthropic_live):
            return "blocked", "ANTHROPIC_LIVE_CANARY_TRIPLE_OPT_IN_REQUIRED", {
                "networkAttempted": False,
                "liveCanaryAttempted": False,
            }
    provider = _anthropic_provider()
    policy = ProviderPolicy.model_validate(
        {
            "provider_id": provider.provider_id,
            "allowed_data_classes": ["public"],
            "blocked_data_classes": [
                "internal",
                "confidential",
                "regulated",
                "raw_pii",
                "secret",
                "credential",
                "payment",
            ],
            "requires_redaction": True,
            "allow_tool_calls": True,
            "requires_approval_for_tool_calls": True,
            "max_output_tokens": 256,
            "canary_call_budget": 1,
            "rate_limit_per_minute": 1,
            "allowed_hosts": ["api.anthropic.com"],
        }
    )
    request = _anthropic_request(fixture)
    storage_policy = ProviderStoragePolicy.model_validate(
        {"provider_id": provider.provider_id, **fixture.get("storage_policy", {})}
    )
    requested_tools = [
        ProviderRequestedTool.model_validate(item) for item in fixture.get("requested_tools", [])
    ]
    started = time.perf_counter()
    native_request = build_anthropic_messages_payload(
        provider=provider,
        policy=policy,
        request=request,
        storage_policy=storage_policy,
        requested_tools=requested_tools,
    )
    provider_response = fixture.get("provider_response")
    if provider_response is None:
        return "pass", "ANTHROPIC_MESSAGES_PAYLOAD_BUILT", _safe_evidence(native_request)
    result = normalize_anthropic_messages_result(
        request=native_request,
        provider_response=provider_response,
        started_at_monotonic=started,
    )
    return result.status, result.reason_code, {
        **_safe_evidence(native_request),
        "toolProposalCount": len(result.tool_proposals),
        "contentBlockCount": len(result.content_blocks),
        "hasTextHash": result.output_text_hash is not None,
        "stopReason": str(result.stop_reason),
        "toolResultLoopSupported": result.tool_result_loop_supported,
        "rawResponsePersisted": result.raw_response_persisted,
    }


def _anthropic_provider() -> ModelProviderRecord:
    return ModelProviderRecord(
        provider_id="anthropic-messages-preview",
        kind=ProviderKind.ANTHROPIC_MESSAGES,
        enabled=False,
        display_name="Anthropic Messages Native Preview",
        base_url="https://api.anthropic.com",
        api_key_env="ANTHROPIC_API_KEY",
        auth_mode="custom_header_env",
        default_model="claude-sonnet-4-6",
        models=["claude-sonnet-4-6"],
        data_boundary="public_cloud",
        retention_policy="provider_default",
        supports_json_mode=False,
        supports_json_schema=False,
        supports_tool_calling=True,
        risk_tier="high",
    )


def _anthropic_request(fixture: dict[str, Any]) -> ProviderCallRequest:
    request_payload = fixture.get("request") or {}
    messages = [
        ChatMessage.model_validate(item)
        for item in request_payload.get(
            "messages",
            [{"role": "user", "content": "public Anthropic native adapter fixture"}],
        )
    ]
    return ProviderCallRequest(
        call_id=f"native-{fixture['case_id']}",
        run_id="native-adapter-conformance",
        provider_id="anthropic-messages-preview",
        model=str(request_payload.get("model", "claude-sonnet-4-6")),
        messages=messages,
        system=request_payload.get("system"),
        data_classes=[DataClass.PUBLIC],
        json_schema=request_payload.get("json_schema"),
        stream=bool(request_payload.get("stream", False)),
    )


def _provider() -> ModelProviderRecord:
    return ModelProviderRecord(
        provider_id="openai-responses-preview",
        kind=ProviderKind.OPENAI_RESPONSES,
        enabled=False,
        display_name="OpenAI Responses Native Preview",
        base_url="https://api.openai.com/v1",
        api_key_env="OPENAI_API_KEY",
        auth_mode="bearer_env",
        default_model="gpt-5.1",
        models=["gpt-5.1"],
        data_boundary="public_cloud",
        retention_policy="provider_default",
        supports_json_mode=True,
        supports_json_schema=True,
        supports_tool_calling=True,
        risk_tier="high",
    )


def _request(fixture: dict[str, Any]) -> ProviderCallRequest:
    request_payload = fixture.get("request") or {}
    messages = [
        ChatMessage.model_validate(item)
        for item in request_payload.get(
            "messages",
            [{"role": "user", "content": "public native adapter fixture"}],
        )
    ]
    return ProviderCallRequest(
        call_id=f"native-{fixture['case_id']}",
        run_id="native-adapter-conformance",
        provider_id="openai-responses-preview",
        model=str(request_payload.get("model", "gpt-5.1")),
        messages=messages,
        system=request_payload.get("system"),
        data_classes=[DataClass.PUBLIC],
        json_schema=request_payload.get("json_schema"),
        stream=bool(request_payload.get("stream", False)),
    )


def _safe_evidence(native_request: Any) -> dict[str, Any]:
    payload = native_request.payload
    return {
        "networkAttempted": False,
        "requestHash": native_request.request_hash,
        "store": payload.get("store"),
        "parallelToolCalls": payload.get("parallel_tool_calls"),
        "toolPolicyDecisionCount": len(native_request.tool_policy_decisions),
        "rawPayloadPersisted": native_request.raw_payload_persisted,
    }


def _markdown(report: ProviderNativeConformanceReport) -> str:
    lines = [
        "# Native Adapter Gate Report",
        "",
        f"- Profile: `{report.profile}`",
        f"- Provider kind: `{report.provider_kind}`",
        f"- Status: `{report.status}`",
        f"- Total cases: `{report.total_cases}`",
        f"- Expected blocked: `{report.expected_blocked_count}`",
        "",
        "| Case | Status | Reason | Matched |",
        "| --- | --- | --- | --- |",
    ]
    for item in report.cases:
        lines.append(
            f"| {item.case_id} | {item.status} | {item.reason_code} | "
            f"{str(item.matched_expectation).lower()} |"
        )
    lines.append("")
    return "\n".join(lines)
