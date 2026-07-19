from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import Field

from imperaos.memory.context_pack import MemoryContextPack, empty_context_pack
from imperaos.memory.models import (
    MemoryPolicyAction,
    MemoryPolicyDecision,
    MemoryWriteResult,
    StrictModel,
    hash_identity,
    sha256_text,
    stable_id,
    utc_now,
)
from imperaos.memory.principal_resolver import (
    AgentMemoryPrincipalResolver,
    PrincipalResolutionInput,
    ResolvedMemoryPrincipal,
    parse_memory_scope,
)
from imperaos.memory.redaction import MemoryRedactor
from imperaos.memory.semantic.runtime_adapter import SemanticRuntimeAdapter
from imperaos.runtime.config import RuntimeConfig

ReadDecisionAction = Literal["allow", "degrade", "deny", "disabled"]
WriteDecisionAction = Literal["allow", "proposal_only", "requires_approval", "deny", "disabled"]


class AgentMemoryRuntimePolicyDecision(StrictModel):
    schema_version: Literal["agent-memory-runtime-policy-decision/v1"] = Field(
        default="agent-memory-runtime-policy-decision/v1",
        alias="schemaVersion",
    )
    operation: Literal["read", "write"]
    action: ReadDecisionAction | WriteDecisionAction
    status: Literal["pass", "empty", "degraded", "denied", "disabled", "error"]
    profile: str
    semantic_runtime_mode: Literal["disabled", "shadow", "enforced"] = Field(
        default="disabled",
        alias="semanticRuntimeMode",
    )
    workspace_hash: str | None = Field(default=None, alias="workspaceHash")
    principal_hash: str | None = Field(default=None, alias="principalHash")
    requested_scope_hashes: tuple[str, ...] = Field(
        default_factory=tuple,
        alias="requestedScopeHashes",
    )
    allowed_scope_hashes: tuple[str, ...] = Field(
        default_factory=tuple,
        alias="allowedScopeHashes",
    )
    denied_scope_hashes: tuple[str, ...] = Field(default_factory=tuple, alias="deniedScopeHashes")
    reason_codes: tuple[str, ...] = Field(default_factory=tuple, alias="reasonCodes")
    evidence_ref: str | None = Field(default=None, alias="evidenceRef")
    raw_content_included: Literal[False] = Field(default=False, alias="rawContentIncluded")


class AgentMemoryRuntimePolicyReadResult(StrictModel):
    decision: AgentMemoryRuntimePolicyDecision
    context_pack: MemoryContextPack = Field(alias="contextPack")
    resolved_principal: ResolvedMemoryPrincipal | None = Field(
        default=None,
        alias="resolvedPrincipal",
    )
    raw_content_included: Literal[False] = Field(default=False, alias="rawContentIncluded")


class AgentMemoryRuntimePolicyDoctorReport(StrictModel):
    schema_version: Literal["agent-memory-runtime-policy-doctor/v1"] = Field(
        default="agent-memory-runtime-policy-doctor/v1",
        alias="schemaVersion",
    )
    status: Literal["pass", "degraded", "disabled", "blocked"]
    policy_enforcement_enabled: bool = Field(alias="policyEnforcementEnabled")
    semantic_runtime_mode: Literal["disabled", "shadow", "enforced"] = Field(
        alias="semanticRuntimeMode",
    )
    workspace_authority_enabled: bool = Field(alias="workspaceAuthorityEnabled")
    semantic_runtime_available: bool = Field(alias="semanticRuntimeAvailable")
    reason_codes: tuple[str, ...] = Field(default_factory=tuple, alias="reasonCodes")
    raw_content_included: Literal[False] = Field(default=False, alias="rawContentIncluded")


class MemoryRuntimePolicyEvaluationCase(StrictModel):
    case_id: str = Field(alias="caseId")
    operation: Literal["read", "write"]
    requester_role: str = Field(alias="requesterRole")
    actor_id: str = Field(alias="actorId")
    principal_id: str | None = Field(default=None, alias="principalId")
    agent_id: str | None = Field(default=None, alias="agentId")
    team_id: str | None = Field(default=None, alias="teamId")
    case_scope_id: str | None = Field(default=None, alias="caseScopeId")
    query: str = ""
    summary: str = ""
    scope: str | None = None
    expected_status: str = Field(alias="expectedStatus")
    expected_reason: str | None = Field(default=None, alias="expectedReason")


class MemoryRuntimePolicyEvaluationReport(StrictModel):
    schema_version: Literal["agent-memory-runtime-policy-evaluation/v1"] = Field(
        default="agent-memory-runtime-policy-evaluation/v1",
        alias="schemaVersion",
    )
    status: Literal["pass", "fail"]
    case_count: int = Field(alias="caseCount", ge=0)
    passed_count: int = Field(alias="passedCount", ge=0)
    failed_count: int = Field(alias="failedCount", ge=0)
    failures: tuple[dict[str, str], ...] = ()
    artifact_path: str | None = Field(default=None, alias="artifactPath")
    generated_at_utc: datetime = Field(default_factory=utc_now, alias="generatedAtUtc")
    raw_content_included: Literal[False] = Field(default=False, alias="rawContentIncluded")


class AgentMemoryPolicyGateway:
    def __init__(
        self,
        *,
        config: RuntimeConfig,
        bridge: object,
        workspace_authority: object | None = None,
        evidence_root: str | Path = "artifacts/memory-runtime-policy",
    ) -> None:
        self.config = config
        self.bridge = bridge
        self.workspace_authority = workspace_authority
        self.evidence_root = Path(evidence_root)
        self.resolver = AgentMemoryPrincipalResolver(
            config=config,
            workspace_authority=workspace_authority,
        )

    def doctor(self) -> AgentMemoryRuntimePolicyDoctorReport:
        runtime = self.config.memory.runtime
        reasons: list[str] = []
        if not runtime.policy_enforcement_enabled:
            reasons.append("MEMORY_RUNTIME_POLICY_DISABLED")
        if not self.config.memory.workspace_authority.enabled:
            reasons.append("MEMORY_WORKSPACE_AUTHORITY_DISABLED")
        if runtime.semantic_runtime_mode != "disabled" and not (
            self.config.memory.semantic.enabled
            and self.config.memory.semantic.runtime_injection_enabled
        ):
            reasons.append("MEMORY_SEMANTIC_RUNTIME_UNAVAILABLE")
        status: Literal["pass", "degraded", "disabled", "blocked"] = "pass"
        if not runtime.policy_enforcement_enabled:
            status = "disabled"
        elif self._strict and reasons:
            status = "blocked"
        elif reasons:
            status = "degraded"
        return AgentMemoryRuntimePolicyDoctorReport(
            status=status,
            policyEnforcementEnabled=runtime.policy_enforcement_enabled,
            semanticRuntimeMode=runtime.semantic_runtime_mode,
            workspaceAuthorityEnabled=self.config.memory.workspace_authority.enabled,
            semanticRuntimeAvailable=bool(
                self.config.memory.semantic.enabled
                and self.config.memory.semantic.runtime_injection_enabled
            ),
            reasonCodes=tuple(reasons),
            rawContentIncluded=False,
        )

    def retrieve_context(self, request: object) -> AgentMemoryRuntimePolicyReadResult:
        if not self.config.memory.runtime.policy_enforcement_enabled:
            pack = self.bridge._retrieve_context_unenforced(request)
            return AgentMemoryRuntimePolicyReadResult(
                decision=self._decision(
                    operation="read",
                    action="disabled",
                    status=pack.status,
                    reason_codes=("MEMORY_RUNTIME_POLICY_DISABLED",),
                ),
                contextPack=pack,
            )
        resolved = self._resolve_request(request)
        if resolved.status in {"denied", "error"}:
            reason = resolved.reason_codes or ("MEMORY_RUNTIME_POLICY_DENIED",)
            pack = empty_context_pack(
                run_id=request.run_id,
                query=request.query,
                status="error" if self._strict else "degraded",
                degraded_reason=reason[0],
            ).model_copy(
                update={
                    "denied_scopes": list(resolved.denied_scopes or resolved.requested_scopes),
                }
            )
            decision = self._write_decision_evidence(
                self._decision(
                    operation="read",
                    action="deny",
                    status="error" if self._strict else "denied",
                    resolved=resolved,
                    reason_codes=reason,
                ),
                query_hash=sha256_text(request.query),
                hit_hashes=(),
            )
            return AgentMemoryRuntimePolicyReadResult(
                decision=decision,
                contextPack=pack.model_copy(update={"evidence_ref": decision.evidence_ref}),
                resolvedPrincipal=resolved,
            )

        semantic_mode = self.config.memory.runtime.semantic_runtime_mode
        if semantic_mode in {"shadow", "enforced"}:
            semantic = SemanticRuntimeAdapter(
                config=self.config,
                workspace_authority=self.workspace_authority,
                evidence_root=self.evidence_root / "semantic",
            ).retrieve(
                run_id=request.run_id,
                query=request.query,
                resolved=resolved,
                mode=semantic_mode,
                limit=self.config.memory.runtime.context_top_k,
                max_context_chars=self.config.memory.runtime.max_context_chars,
            )
            if semantic_mode == "enforced":
                if semantic.status == "blocked":
                    decision = self._write_decision_evidence(
                        self._decision(
                            operation="read",
                            action="deny",
                            status="denied",
                            resolved=resolved,
                            reason_codes=semantic.reason_codes
                            or ("MEMORY_SEMANTIC_RUNTIME_BLOCKED",),
                        ),
                        query_hash=sha256_text(request.query),
                        hit_hashes=semantic.hit_id_hashes,
                    )
                    pack = empty_context_pack(
                        run_id=request.run_id,
                        query=request.query,
                        status="error" if self._strict else "degraded",
                        degraded_reason=decision.reason_codes[0],
                    ).model_copy(update={"evidence_ref": decision.evidence_ref})
                    return AgentMemoryRuntimePolicyReadResult(
                        decision=decision,
                        contextPack=pack,
                        resolvedPrincipal=resolved,
                    )
                if semantic.context_pack is not None:
                    decision = self._write_decision_evidence(
                        self._decision(
                            operation="read",
                            action="allow",
                            status=semantic.context_pack.status,
                            resolved=resolved,
                            reason_codes=semantic.reason_codes,
                        ),
                        query_hash=sha256_text(request.query),
                        hit_hashes=semantic.hit_id_hashes,
                    )
                    return AgentMemoryRuntimePolicyReadResult(
                        decision=decision,
                        contextPack=semantic.context_pack.model_copy(
                            update={"evidence_ref": decision.evidence_ref}
                        ),
                        resolvedPrincipal=resolved,
                    )
        pack = self.bridge._retrieve_context_unenforced(
            replace(
                request,
                actor_id=resolved.principal_id,
                principal_id=resolved.principal_id,
                workspace_id=resolved.workspace_id,
            )
        )
        reasons = tuple(resolved.reason_codes)
        if semantic_mode == "shadow":
            reasons = tuple(dict.fromkeys((*reasons, "MEMORY_SEMANTIC_RUNTIME_SHADOW")))
        decision = self._write_decision_evidence(
            self._decision(
                operation="read",
                action="degrade" if resolved.status == "degraded" else "allow",
                status=pack.status,
                resolved=resolved,
                reason_codes=reasons,
            ),
            query_hash=sha256_text(request.query),
            hit_hashes=tuple(hash_identity(hit.memory_id) for hit in pack.hits),
        )
        return AgentMemoryRuntimePolicyReadResult(
            decision=decision,
            contextPack=pack.model_copy(update={"evidence_ref": decision.evidence_ref}),
            resolvedPrincipal=resolved,
        )

    def propose_post_run_write(self, **kwargs: object) -> MemoryWriteResult:
        if not self.config.memory.runtime.policy_enforcement_enabled:
            return self.bridge._propose_post_run_write_unenforced(**kwargs)
        run_id = str(kwargs["run_id"])
        user_input = str(kwargs.get("user_input") or "")
        assistant_output = str(kwargs.get("assistant_output") or "")
        redaction = MemoryRedactor().redact_candidate(
            candidate_text=f"{user_input}\n{assistant_output}",
            privacy_mode=True,
        )
        request = PrincipalResolutionInput(
            actor_id=str(kwargs.get("actor_id") or ""),
            requester_role=str(kwargs.get("role") or "operator"),
            principal_id=str(kwargs["actor_id"]) if kwargs.get("actor_id") else None,
            agent_id=kwargs.get("agent_id") if isinstance(kwargs.get("agent_id"), str) else None,
        )
        resolved = self.resolver.resolve(request)
        if redaction.secret_detected:
            return self._denied_write(
                run_id=run_id,
                reason="MEMORY_RUNTIME_WRITE_SECRET_DENIED",
                resolved=resolved,
                content_hash=redaction.content_hash,
            )
        if resolved.status in {"denied", "error"}:
            return self._denied_write(
                run_id=run_id,
                reason=(resolved.reason_codes or ("MEMORY_RUNTIME_POLICY_DENIED",))[0],
                resolved=resolved,
            )
        if not self.config.memory.runtime.post_run_write_enabled:
            return self._denied_write(
                run_id=run_id,
                reason="MEMORY_RUNTIME_WRITE_DISABLED",
                resolved=resolved,
                action="disabled",
                status="error",
            )
        scope_type, scope_owner = _write_scope(kwargs, resolved)
        result = self.bridge._propose_post_run_write_unenforced(
            **{
                **kwargs,
                "actor_id": resolved.principal_id,
                "scope": scope_type,
                "owner": kwargs.get("owner") or scope_owner,
            }
        )
        reason_codes = tuple(result.blocking_reasons)
        decision = self._write_decision_evidence(
            self._decision(
                operation="write",
                action=_write_action(result.status),
                status=_write_status(result.status),
                resolved=resolved,
                reason_codes=reason_codes,
            ),
            content_hash=result.content_hash,
        )
        return result.model_copy(update={"evidence_ref": decision.evidence_ref})

    @property
    def _strict(self) -> bool:
        return self.config.profile_name in set(
            self.config.memory.runtime.strict_fail_closed_profiles
        )

    def _resolve_request(self, request: object) -> ResolvedMemoryPrincipal:
        return self.resolver.resolve(
            PrincipalResolutionInput(
                actor_id=request.actor_id,
                requester_role=request.requester_role,
                workspace_id=request.workspace_id,
                principal_id=request.principal_id,
                agent_id=request.agent_id,
                team_id=request.team_id,
                case_id=request.case_id,
                project_id=request.project_id,
            )
        )

    def _decision(
        self,
        *,
        operation: Literal["read", "write"],
        action: ReadDecisionAction | WriteDecisionAction,
        status: Literal["pass", "empty", "degraded", "denied", "disabled", "error"],
        resolved: ResolvedMemoryPrincipal | None = None,
        reason_codes: tuple[str, ...] = (),
    ) -> AgentMemoryRuntimePolicyDecision:
        return AgentMemoryRuntimePolicyDecision(
            operation=operation,
            action=action,
            status=status,
            profile=self.config.profile_name,
            semanticRuntimeMode=self.config.memory.runtime.semantic_runtime_mode,
            workspaceHash=hash_identity(resolved.workspace_id) if resolved else None,
            principalHash=resolved.principal_hash if resolved else None,
            requestedScopeHashes=tuple(
                hash_identity(scope) for scope in (resolved.requested_scopes if resolved else ())
            ),
            allowedScopeHashes=tuple(
                hash_identity(scope) for scope in (resolved.allowed_scopes if resolved else ())
            ),
            deniedScopeHashes=tuple(
                hash_identity(scope) for scope in (resolved.denied_scopes if resolved else ())
            ),
            reasonCodes=tuple(dict.fromkeys(reason_codes)),
            rawContentIncluded=False,
        )

    def _write_decision_evidence(
        self,
        decision: AgentMemoryRuntimePolicyDecision,
        *,
        query_hash: str | None = None,
        content_hash: str | None = None,
        hit_hashes: tuple[str, ...] = (),
    ) -> AgentMemoryRuntimePolicyDecision:
        events_dir = self.evidence_root / "events"
        events_dir.mkdir(parents=True, exist_ok=True)
        event_id = stable_id(
            "mem_policy_evt",
            decision.operation,
            decision.workspace_hash,
            decision.principal_hash,
            query_hash,
            content_hash,
            utc_now().isoformat(),
        )
        payload = {
            "schemaVersion": "agent-memory-runtime-policy-event/v1",
            "eventId": event_id,
            "operation": decision.operation,
            "action": decision.action,
            "status": decision.status,
            "profile": decision.profile,
            "semanticRuntimeMode": decision.semantic_runtime_mode,
            "workspaceHash": decision.workspace_hash,
            "principalHash": decision.principal_hash,
            "requestedScopeHashes": list(decision.requested_scope_hashes),
            "allowedScopeHashes": list(decision.allowed_scope_hashes),
            "deniedScopeHashes": list(decision.denied_scope_hashes),
            "queryHash": query_hash,
            "contentHash": content_hash,
            "hitIdHashes": list(hit_hashes),
            "reasonCodes": list(decision.reason_codes),
            "rawContentIncluded": False,
            "rawPromptIncluded": False,
            "rawResponseIncluded": False,
            "rawMemoryIncluded": False,
            "createdAtUtc": utc_now().isoformat(),
        }
        path = events_dir / f"{event_id}.json"
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return decision.model_copy(update={"evidence_ref": str(path)})

    def _denied_write(
        self,
        *,
        run_id: str,
        reason: str,
        resolved: ResolvedMemoryPrincipal | None,
        content_hash: str | None = None,
        action: WriteDecisionAction = "deny",
        status: Literal["denied", "error"] = "denied",
    ) -> MemoryWriteResult:
        decision = self._write_decision_evidence(
            self._decision(
                operation="write",
                action=action,
                status=status,
                resolved=resolved,
                reason_codes=(reason,),
            ),
            content_hash=content_hash,
        )
        return MemoryWriteResult(
            status="denied" if status == "denied" else "error",
            proposalId=stable_id("mem_prop", run_id, reason),
            policyDecision=MemoryPolicyDecision(
                decision=MemoryPolicyAction.DENY,
                reasonCode=reason,
                indexWriteAllowed=False,
                blockingReasons=[reason],
            ),
            evidenceRef=decision.evidence_ref,
            contentHash=content_hash,
            blockingReasons=[reason],
            rawContentIncluded=False,
        )


def _write_scope(
    kwargs: dict[str, object],
    resolved: ResolvedMemoryPrincipal,
) -> tuple[str, str]:
    scope_type = str(kwargs.get("scope") or "personal")
    if ":" in scope_type:
        parsed = parse_memory_scope(scope_type)
        return parsed.scope_type, parsed.scope_id
    for raw_scope in resolved.allowed_scopes:
        parsed = parse_memory_scope(raw_scope)
        if parsed.scope_type == scope_type:
            return parsed.scope_type, parsed.scope_id
    return scope_type, resolved.principal_id


def _write_action(status: str) -> WriteDecisionAction:
    if status == "written":
        return "allow"
    if status == "proposal_only":
        return "proposal_only"
    if status == "approval_required":
        return "requires_approval"
    if status == "error":
        return "disabled"
    return "deny"


def _write_status(
    status: str,
) -> Literal["pass", "empty", "degraded", "denied", "disabled", "error"]:
    if status in {"written", "proposal_only", "approval_required"}:
        return "pass"
    if status == "conflict":
        return "denied"
    if status == "error":
        return "error"
    return "denied"
