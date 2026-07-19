from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from imperaos.memory.authority import MemoryAuthority, build_memory_authority
from imperaos.memory.context_pack import (
    MemoryContextHit,
    MemoryContextPack,
    context_pack_from_retrieval,
    empty_context_pack,
)
from imperaos.memory.models import (
    MemoryPolicyAction,
    MemoryPolicyDecision,
    MemoryRetrievalRequest,
    MemoryScope,
    MemoryScopeFilter,
    MemoryVisibility,
    MemoryWriteResult,
    hash_identity,
    stable_id,
)
from imperaos.memory.workspace_authority import (
    WorkspaceMemoryAuthority,
    build_workspace_memory_authority,
)
from imperaos.memory.workspace_models import (
    MemoryAccessDecision,
    WorkspaceMemoryQueryRequest,
    WorkspaceMemoryWriteRequest,
)
from imperaos.memory.write_candidate import (
    MemoryWriteCandidateBuilder,
    MemoryWriteCandidateInput,
)
from imperaos.runtime.config import RuntimeConfig


@dataclass(frozen=True, slots=True)
class RuntimeMemoryRequest:
    run_id: str
    query: str
    actor_id: str
    requester_role: str
    agent_id: str | None = None
    team_id: str | None = None
    case_id: str | None = None
    project_id: str | None = None
    workspace_id: str | None = None
    principal_id: str | None = None
    namespace: str = "default"


class MemoryRuntimeBridge:
    def __init__(
        self,
        *,
        config: RuntimeConfig,
        authority: MemoryAuthority,
        workspace_authority: WorkspaceMemoryAuthority | None = None,
        evidence_root: str | Path = "artifacts/memory-runtime",
    ) -> None:
        self.config = config
        self.authority = authority
        self.workspace_authority = workspace_authority
        self.evidence_root = Path(evidence_root)

    @property
    def enabled(self) -> bool:
        return bool(
            self.config.memory.runtime.enabled
            and (
                self.config.memory.v3_enabled
                or self.config.memory.workspace_authority.enabled
            )
        )

    def retrieve_context(self, request: RuntimeMemoryRequest) -> MemoryContextPack:
        if self.config.memory.runtime.policy_enforcement_enabled:
            from imperaos.memory.runtime_policy import AgentMemoryPolicyGateway

            return AgentMemoryPolicyGateway(
                config=self.config,
                bridge=self,
                workspace_authority=self.workspace_authority,
                evidence_root=Path(self.evidence_root).parent / "memory-runtime-policy",
            ).retrieve_context(request).context_pack
        return self._retrieve_context_unenforced(request)

    def _retrieve_context_unenforced(self, request: RuntimeMemoryRequest) -> MemoryContextPack:
        runtime_cfg = self.config.memory.runtime
        if not self.enabled:
            return empty_context_pack(
                run_id=request.run_id,
                query=request.query,
                status="disabled",
                degraded_reason="MEMORY_RUNTIME_DISABLED",
            )
        if self._workspace_authority_enabled:
            return self._retrieve_workspace_context(request)
        filters = _scope_filters(request)
        if not filters:
            status: Literal["degraded", "error"] = "degraded"
            reason = "MEMORY_RUNTIME_SCOPE_UNAVAILABLE"
            if self.config.profile_name in set(runtime_cfg.strict_fail_closed_profiles):
                status = "error"
                reason = "MEMORY_RUNTIME_FAIL_CLOSED_SCOPE_UNAVAILABLE"
            return empty_context_pack(
                run_id=request.run_id,
                query=request.query,
                status=status,
                degraded_reason=reason,
            )
        allowed_scopes = sorted({item.scope for item in filters}, key=str)
        result = self.authority.retrieve(
            MemoryRetrievalRequest(
                actorIdHash=hash_identity(request.actor_id),
                agentId=request.agent_id,
                requesterRole=request.requester_role,
                query=request.query,
                allowedScopes=allowed_scopes,
                scopeFilters=filters,
                visibilityFilters=_visibility_filters(filters),
                limit=max(1, runtime_cfg.context_top_k),
                includeContent=True,
                purpose="context_injection",
            )
        )
        return context_pack_from_retrieval(
            run_id=request.run_id,
            result=result,
            max_context_chars=runtime_cfg.max_context_chars,
        )

    def propose_post_run_write(
        self,
        *,
        run_id: str,
        actor_id: str,
        role: str,
        user_input: str,
        assistant_output: str,
        scope: str | None = None,
        owner_type: str | None = None,
        owner: str | None = None,
        visibility: str | None = None,
        memory_target: str | None = None,
        expected_state_version: int | None = None,
        agent_id: str | None = None,
    ) -> MemoryWriteResult:
        if self.config.memory.runtime.policy_enforcement_enabled:
            from imperaos.memory.runtime_policy import AgentMemoryPolicyGateway

            return AgentMemoryPolicyGateway(
                config=self.config,
                bridge=self,
                workspace_authority=self.workspace_authority,
                evidence_root=Path(self.evidence_root).parent / "memory-runtime-policy",
            ).propose_post_run_write(
                run_id=run_id,
                actor_id=actor_id,
                role=role,
                user_input=user_input,
                assistant_output=assistant_output,
                scope=scope,
                owner_type=owner_type,
                owner=owner,
                visibility=visibility,
                memory_target=memory_target,
                expected_state_version=expected_state_version,
                agent_id=agent_id,
            )
        return self._propose_post_run_write_unenforced(
            run_id=run_id,
            actor_id=actor_id,
            role=role,
            user_input=user_input,
            assistant_output=assistant_output,
            scope=scope,
            owner_type=owner_type,
            owner=owner,
            visibility=visibility,
            memory_target=memory_target,
            expected_state_version=expected_state_version,
            agent_id=agent_id,
        )

    def _propose_post_run_write_unenforced(
        self,
        *,
        run_id: str,
        actor_id: str,
        role: str,
        user_input: str,
        assistant_output: str,
        scope: str | None = None,
        owner_type: str | None = None,
        owner: str | None = None,
        visibility: str | None = None,
        memory_target: str | None = None,
        expected_state_version: int | None = None,
        agent_id: str | None = None,
    ) -> MemoryWriteResult:
        if not self.enabled or not self.config.memory.runtime.post_run_write_enabled:
            return _disabled_write_result(run_id=run_id, reason="MEMORY_RUNTIME_WRITE_DISABLED")
        if self._workspace_authority_enabled:
            return self._workspace_post_run_write(
                run_id=run_id,
                actor_id=actor_id,
                role=role,
                user_input=user_input,
                assistant_output=assistant_output,
                scope=scope,
                owner=owner,
                memory_target=memory_target,
                expected_state_version=expected_state_version,
                agent_id=agent_id,
            )
        resolved_scope = scope or self.config.memory.runtime.post_run_default_scope
        resolved_owner_type = owner_type or _owner_type_for_scope(resolved_scope)
        resolved_visibility = visibility or _visibility_for_scope(resolved_scope)
        proposal = MemoryWriteCandidateBuilder.build(
            MemoryWriteCandidateInput(
                actor=actor_id,
                role=role,
                run_id=run_id,
                user_input=user_input,
                assistant_output=assistant_output,
                scope=resolved_scope,
                owner_type=resolved_owner_type,
                owner=owner or actor_id,
                visibility=resolved_visibility,
                memory_target=memory_target,
                expected_state_version=expected_state_version,
                agent_id=agent_id,
            )
        )
        if proposal is None:
            return _disabled_write_result(run_id=run_id, reason="MEMORY_RUNTIME_WRITE_EMPTY")
        return self.authority.propose_write(proposal)

    @property
    def _workspace_authority_enabled(self) -> bool:
        return bool(
            self.workspace_authority is not None
            and self.config.memory.workspace_authority.enabled
        )

    def _retrieve_workspace_context(self, request: RuntimeMemoryRequest) -> MemoryContextPack:
        assert self.workspace_authority is not None
        runtime_cfg = self.config.memory.runtime
        workspace_id = _workspace_id(self.config, request)
        principal_id = _principal_id(self.config, request)
        if (
            self.config.memory.semantic.enabled
            and self.config.memory.semantic.runtime_injection_enabled
        ):
            from imperaos.memory.semantic.models import MemorySearchRequest

            requested_scopes = tuple(
                f"{scope_type}:{scope_id}"
                for scope_type, scope_id in _workspace_scope_queries(request, principal_id)
            )
            semantic_result = self.workspace_authority.semantic_search(
                MemorySearchRequest(
                    query=request.query,
                    principalId=principal_id,
                    workspaceId=workspace_id,
                    requestedScopes=requested_scopes,
                    limit=max(1, runtime_cfg.context_top_k),
                    allowStaleIndex=False,
                )
            )
            hits = [
                MemoryContextHit(
                    memoryId=hit.memory_id,
                    scope=hit.scope_type,
                    visibility=hit.scope_type,
                    redactedSummary=hit.redacted_summary,
                    contentHash=hit.content_hash,
                    score=hit.score_breakdown.final,
                    createdAt=hit.created_at_utc,
                    policyTags=[],
                )
                for hit in semantic_result.hits
            ]
            status: Literal["pass", "empty", "denied"] = "pass" if hits else "empty"
            if semantic_result.status == "blocked":
                status = "denied"
            return MemoryContextPack(
                packId=stable_id(
                    "mem_ctx",
                    request.run_id,
                    request.query,
                    workspace_id,
                    principal_id,
                    "semantic",
                ),
                runId=request.run_id,
                queryHash=hash_identity(request.query),
                status=status,
                hits=hits,
                evidenceRef=semantic_result.evidence_ref,
                deniedScopes=[],
                rawContentIncluded=False,
                truncated=False,
                degradedReason="MEMORY_SEMANTIC_RETRIEVAL_BLOCKED"
                if semantic_result.status == "blocked"
                else None,
            )
        hits: list[MemoryContextHit] = []
        denied_scopes: list[str] = []
        evidence_ref: str | None = None
        for scope_type, scope_id in _workspace_scope_queries(request, principal_id):
            result = self.workspace_authority.query(
                WorkspaceMemoryQueryRequest(
                    workspaceId=workspace_id,
                    principalId=principal_id,
                    scopeType=scope_type,
                    scopeId=scope_id,
                    query=request.query,
                    limit=max(1, runtime_cfg.context_top_k),
                )
            )
            evidence_ref = evidence_ref or result.evidence_ref
            if result.status == "denied":
                denied_scopes.append(f"{scope_type}:{scope_id}")
                continue
            for record in result.records:
                hits.append(
                    MemoryContextHit(
                        memoryId=record.memory_id,
                        scope=record.scope_type,
                        visibility=record.scope_type,
                        redactedSummary=record.redacted_preview or record.summary,
                        contentHash=record.content_hash,
                        score=record.salience,
                        createdAt=record.created_at_utc,
                        policyTags=list(record.policy_tags),
                    )
                )
                if len(hits) >= max(1, runtime_cfg.context_top_k):
                    break
            if len(hits) >= max(1, runtime_cfg.context_top_k):
                break
        status: Literal["pass", "empty", "denied"] = "pass" if hits else "empty"
        if not hits and denied_scopes:
            status = "denied"
        return MemoryContextPack(
            packId=stable_id("mem_ctx", request.run_id, request.query, workspace_id, principal_id),
            runId=request.run_id,
            queryHash=hash_identity(request.query),
            status=status,
            hits=hits,
            evidenceRef=evidence_ref,
            deniedScopes=denied_scopes,
            rawContentIncluded=False,
            truncated=False,
            degradedReason="MEMORY_RETRIEVAL_DENIED" if status == "denied" else None,
        )

    def _workspace_post_run_write(
        self,
        *,
        run_id: str,
        actor_id: str,
        role: str,
        user_input: str,
        assistant_output: str,
        scope: str | None,
        owner: str | None,
        memory_target: str | None,
        expected_state_version: int | None,
        agent_id: str | None,
    ) -> MemoryWriteResult:
        assert self.workspace_authority is not None
        _ = role
        resolved_scope = scope or self.config.memory.runtime.post_run_default_scope
        workspace_id = self.config.memory.workspace_authority.default_workspace_id
        principal_id = actor_id or self.config.memory.workspace_authority.default_principal_id
        scope_id = _workspace_scope_id(
            scope=resolved_scope,
            owner=owner,
            actor_id=actor_id,
            agent_id=agent_id,
        )
        decision = self.workspace_authority.propose_or_write(
            WorkspaceMemoryWriteRequest(
                workspaceId=workspace_id,
                principalId=principal_id,
                scopeType=resolved_scope,
                scopeId=scope_id,
                summary=f"User: {user_input}\nAssistant: {assistant_output}",
                memoryTarget=memory_target,
                expectedStateVersion=expected_state_version,
                sourceAgentId=agent_id,
                sourceRunId=run_id,
                reason="runtime post-run write",
            )
        )
        status_map = {
            "committed": "written",
            "proposal_only": "proposal_only",
            "requires_approval": "approval_required",
            "denied": "denied",
            "conflict": "conflict",
        }
        return MemoryWriteResult(
            status=status_map[decision.status],
            proposalId=decision.proposal_id or stable_id("wm_prop", run_id, decision.status),
            memoryId=decision.memory_id,
            policyDecision=_workspace_policy_decision(decision.decision),
            evidenceRef=decision.evidence_ref,
            contentHash=decision.content_hash,
            stateVersion=decision.state_version,
            conflictDetected=decision.status == "conflict",
            blockingReasons=decision.blocking_reasons,
            rawContentIncluded=False,
        )


def build_memory_runtime_bridge(
    config: RuntimeConfig,
    *,
    evidence_root: str | Path = "artifacts/memory-runtime",
) -> MemoryRuntimeBridge:
    return MemoryRuntimeBridge(
        config=config,
        authority=build_memory_authority(config, evidence_root=evidence_root),
        workspace_authority=build_workspace_memory_authority(
            config,
            evidence_root=Path(evidence_root) / "workspace",
        ),
        evidence_root=evidence_root,
    )


def _scope_filters(request: RuntimeMemoryRequest) -> list[MemoryScopeFilter]:
    filters = [
        MemoryScopeFilter(
            scope=MemoryScope.PERSONAL,
            ownerType="user",
            ownerIdHash=hash_identity(request.actor_id),
            namespace=request.namespace,
        )
    ]
    if request.agent_id:
        filters.append(
            MemoryScopeFilter(
                scope=MemoryScope.AGENT,
                ownerType="agent",
                ownerIdHash=hash_identity(request.agent_id),
                namespace=request.namespace,
            )
        )
    if request.team_id:
        filters.append(
            MemoryScopeFilter(
                scope=MemoryScope.TEAM,
                ownerType="team",
                ownerIdHash=hash_identity(request.team_id),
                namespace=request.namespace,
            )
        )
    if request.case_id:
        filters.append(
            MemoryScopeFilter(
                scope=MemoryScope.CASE,
                ownerType="case",
                ownerIdHash=hash_identity(request.case_id),
                namespace=request.namespace,
            )
        )
    if request.project_id:
        filters.append(
            MemoryScopeFilter(
                scope=MemoryScope.PROJECT,
                ownerType="project",
                ownerIdHash=hash_identity(request.project_id),
                namespace=request.namespace,
            )
        )
    return filters


def _visibility_filters(filters: list[MemoryScopeFilter]) -> list[MemoryVisibility]:
    values: set[MemoryVisibility] = {MemoryVisibility.PRIVATE}
    for item in filters:
        if item.scope == MemoryScope.AGENT:
            values.add(MemoryVisibility.AGENT)
        elif item.scope == MemoryScope.TEAM:
            values.add(MemoryVisibility.TEAM)
        elif item.scope == MemoryScope.PROJECT:
            values.add(MemoryVisibility.PROJECT)
    return sorted(values, key=str)


def _owner_type_for_scope(scope: str) -> str:
    return {
        "agent": "agent",
        "team": "team",
        "case": "case",
        "project": "project",
        "organization": "org",
    }.get(scope, "user")


def _visibility_for_scope(scope: str) -> str:
    return {
        "agent": "agent",
        "team": "team",
        "case": "team",
        "project": "project",
        "organization": "organization",
    }.get(scope, "private")


def _workspace_id(config: RuntimeConfig, request: RuntimeMemoryRequest) -> str:
    return request.workspace_id or config.memory.workspace_authority.default_workspace_id


def _principal_id(config: RuntimeConfig, request: RuntimeMemoryRequest) -> str:
    return (
        request.principal_id
        or request.actor_id
        or config.memory.workspace_authority.default_principal_id
    )


def _workspace_scope_queries(
    request: RuntimeMemoryRequest,
    principal_id: str,
) -> list[tuple[str, str]]:
    queries: list[tuple[str, str]] = [("personal", principal_id)]
    if request.agent_id:
        queries.append(("agent", request.agent_id))
    if request.team_id:
        queries.append(("team", request.team_id))
    if request.case_id:
        queries.append(("case", request.case_id))
    if request.project_id:
        queries.append(("project", request.project_id))
    return queries


def _workspace_scope_id(
    *,
    scope: str,
    owner: str | None,
    actor_id: str,
    agent_id: str | None,
) -> str:
    if owner:
        return owner
    if scope == "agent" and agent_id:
        return agent_id
    return actor_id


def _workspace_policy_decision(decision: MemoryAccessDecision) -> MemoryPolicyDecision:
    action_value = decision.action
    return MemoryPolicyDecision(
        decision={
            "allow": MemoryPolicyAction.ALLOW,
            "deny": MemoryPolicyAction.DENY,
            "proposal_only": MemoryPolicyAction.PROPOSAL_ONLY,
            "requires_approval": MemoryPolicyAction.REQUIRE_APPROVAL,
        }[action_value],
        reasonCode=decision.reason_code,
        redactionRequired=decision.redaction_required,
        indexWriteAllowed=action_value == "allow",
        blockingReasons=[] if action_value == "allow" else [decision.reason_code],
    )


def _disabled_write_result(*, run_id: str, reason: str) -> MemoryWriteResult:
    return MemoryWriteResult(
        status="error",
        proposalId=stable_id("mem_prop", run_id, reason),
        policyDecision=MemoryPolicyDecision(
            decision=MemoryPolicyAction.DENY,
            reasonCode=reason,
            blockingReasons=[reason],
        ),
        blockingReasons=[reason],
        rawContentIncluded=False,
    )
