from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from imperaos.control_plane.provider_governance import stable_hash_payload
from imperaos.control_plane.provider_runtime_evidence import ProviderEvidenceWriter
from imperaos.control_plane.providers import get_native_provider_adapter

ProviderRuntimeMode = Literal["offline_conformance", "dry_run", "canary_live", "disabled"]


@dataclass(frozen=True)
class ProviderInvocationRequest:
    provider_kind: str
    model: str
    profile: str
    runtime_mode: ProviderRuntimeMode
    prompt: str
    agent_id: str | None = None
    workflow_id: str | None = None
    approval_context: dict[str, Any] | None = None


@dataclass(frozen=True)
class ProviderInvocationResult:
    status: Literal["pass", "blocked", "conditional", "error"]
    invocation_id: str
    provider_kind: str
    runtime_mode: str
    request_hash: str
    response_hash: str | None
    artifact_path: str | None
    blocking_reasons: tuple[str, ...]
    raw_persistence: bool
    evidence_mode: Literal["hash_only"]

    def to_payload(self) -> dict[str, Any]:
        return {
            "schemaVersion": "provider.invocation.v1",
            "status": self.status,
            "invocationId": self.invocation_id,
            "providerKind": self.provider_kind,
            "runtimeMode": self.runtime_mode,
            "requestHash": self.request_hash,
            "responseHash": self.response_hash,
            "artifactPath": self.artifact_path,
            "blockingReasons": list(self.blocking_reasons),
            "rawPersistence": self.raw_persistence,
            "evidenceMode": self.evidence_mode,
        }


class ProviderInvocationCoordinator:
    def __init__(
        self,
        *,
        output_dir: str | Path = "artifacts/provider-runtime/invocations",
    ) -> None:
        self.output_dir = Path(output_dir)

    def invoke(self, request: ProviderInvocationRequest) -> ProviderInvocationResult:
        invocation_id = _invocation_id(request)
        request_hash = stable_hash_payload(
            {
                "provider_kind": request.provider_kind,
                "model": request.model,
                "runtime_mode": request.runtime_mode,
                "prompt": request.prompt,
                "agent_id": request.agent_id,
                "workflow_id": request.workflow_id,
            }
        )
        if request.runtime_mode == "disabled":
            return self._write_blocked(
                request,
                invocation_id=invocation_id,
                request_hash=request_hash,
                reasons=["PROVIDER_RUNTIME_DISABLED"],
            )
        if request.provider_kind not in {"openai_responses", "anthropic_messages"}:
            return self._write_blocked(
                request,
                invocation_id=invocation_id,
                request_hash=request_hash,
                reasons=["PROVIDER_UNSUPPORTED"],
            )
        if request.runtime_mode == "canary_live":
            if os.environ.get("IMPERAOS_PROVIDER_LIVE_CANARY_OPT_IN") != "1":
                return self._write_blocked(
                    request,
                    invocation_id=invocation_id,
                    request_hash=request_hash,
                    reasons=["PROVIDER_LIVE_CANARY_REQUIRES_EXPLICIT_OPT_IN"],
                )
            credential_name = _credential_env_name(request.provider_kind)
            if not os.environ.get(credential_name):
                return self._write_blocked(
                    request,
                    invocation_id=invocation_id,
                    request_hash=request_hash,
                    reasons=["PROVIDER_CREDENTIAL_MISSING"],
                )
            return self._write_blocked(
                request,
                invocation_id=invocation_id,
                request_hash=request_hash,
                reasons=["PROVIDER_LIVE_CANARY_NOT_IMPLEMENTED"],
            )

        adapter = get_native_provider_adapter(request.provider_kind)
        envelope = adapter.build_request(
            prompt=request.prompt,
            model=request.model,
            profile=request.profile,
            custom_tools=[{"name": "draft_remediation", "description": "Draft only"}],
        )
        raw_fixture = _offline_fixture_response(request.provider_kind, request.model)
        parsed = adapter.parse_response(raw_fixture)
        response_hash = stable_hash_payload(
            {
                "provider_kind": parsed.provider_kind,
                "output_text": parsed.output_text,
                "metadata": parsed.metadata,
            }
        )
        policy_decision = {
            "decision": "allow",
            "reasonCodes": ["PROVIDER_POLICY_PASS"],
            "policyHash": "sha256:provider-governance-v1",
        }
        write_result = ProviderEvidenceWriter(output_dir=self.output_dir).write_invocation(
            invocation_id=invocation_id,
            provider_kind=request.provider_kind,
            model=request.model,
            runtime_mode=request.runtime_mode,
            status="pass",
            policy_decision=policy_decision,
            request_hash=envelope.request_hash,
            response_hash=response_hash,
            tool_policy=envelope.tool_policy,
            blocking_reasons=[],
            raw_inputs_for_scan=[
                request.prompt,
                parsed.output_text,
                os.environ.get(_credential_env_name(request.provider_kind), ""),
            ],
        )
        if write_result.status == "error":
            return ProviderInvocationResult(
                status="error",
                invocation_id=invocation_id,
                provider_kind=request.provider_kind,
                runtime_mode=request.runtime_mode,
                request_hash=envelope.request_hash,
                response_hash=response_hash,
                artifact_path=None,
                blocking_reasons=write_result.blocking_reasons,
                raw_persistence=False,
                evidence_mode="hash_only",
            )
        return ProviderInvocationResult(
            status="pass",
            invocation_id=invocation_id,
            provider_kind=request.provider_kind,
            runtime_mode=request.runtime_mode,
            request_hash=envelope.request_hash,
            response_hash=response_hash,
            artifact_path=write_result.artifact_path,
            blocking_reasons=(),
            raw_persistence=False,
            evidence_mode="hash_only",
        )

    def _write_blocked(
        self,
        request: ProviderInvocationRequest,
        *,
        invocation_id: str,
        request_hash: str,
        reasons: list[str],
    ) -> ProviderInvocationResult:
        write_result = ProviderEvidenceWriter(output_dir=self.output_dir).write_invocation(
            invocation_id=invocation_id,
            provider_kind=request.provider_kind,
            model=request.model,
            runtime_mode=request.runtime_mode,
            status="blocked",
            policy_decision={
                "decision": "deny",
                "reasonCodes": reasons,
                "policyHash": "sha256:provider-governance-v1",
            },
            request_hash=request_hash,
            response_hash=None,
            tool_policy={
                "serverToolsPolicy": "denied",
                "customToolsPolicy": "proposal_only",
                "requestedServerTools": [],
            },
            blocking_reasons=reasons,
            raw_inputs_for_scan=[
                request.prompt,
                os.environ.get(_credential_env_name(request.provider_kind), ""),
            ],
        )
        return ProviderInvocationResult(
            status="blocked" if write_result.status != "error" else "error",
            invocation_id=invocation_id,
            provider_kind=request.provider_kind,
            runtime_mode=request.runtime_mode,
            request_hash=request_hash,
            response_hash=None,
            artifact_path=write_result.artifact_path,
            blocking_reasons=write_result.blocking_reasons or tuple(reasons),
            raw_persistence=False,
            evidence_mode="hash_only",
        )


def _invocation_id(request: ProviderInvocationRequest) -> str:
    digest = stable_hash_payload(
        {
            "provider_kind": request.provider_kind,
            "model": request.model,
            "runtime_mode": request.runtime_mode,
            "prompt": request.prompt,
            "workflow_id": request.workflow_id,
        }
    ).removeprefix("sha256:")[:16]
    return f"provider-inv-{digest}"


def _credential_env_name(provider_kind: str) -> str:
    if provider_kind == "anthropic_messages":
        return "IMPERAOS_ANTHROPIC_API_KEY"
    return "IMPERAOS_OPENAI_API_KEY"


def _offline_fixture_response(provider_kind: str, model: str) -> dict[str, Any]:
    if provider_kind == "anthropic_messages":
        return {
            "id": "msg_offline_fixture",
            "model": model,
            "content": [{"type": "text", "text": "Read-only triage summary drafted."}],
            "usage": {"input_tokens": 12, "output_tokens": 7},
        }
    return {
        "id": "resp_offline_fixture",
        "model": model,
        "output": [
            {
                "type": "message",
                "content": [
                    {"type": "output_text", "text": "Read-only triage summary drafted."}
                ],
            }
        ],
        "usage": {"input_tokens": 12, "output_tokens": 7},
    }
