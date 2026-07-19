from __future__ import annotations

from dataclasses import dataclass

from imperaos.governance.models import GovernanceAction
from imperaos.governance.runtime import GovernanceRuntime
from imperaos.memory.manager import MemoryManager
from imperaos.memory.prompt_injector import MemoryPromptInjector
from imperaos.memory.runtime_bridge import MemoryRuntimeBridge, RuntimeMemoryRequest


@dataclass(slots=True)
class MemoryScopeDecision:
    allowed: bool
    requires_approval: bool
    reason_code: str
    approval_id: str | None


@dataclass(slots=True)
class MemoryAccessValidation:
    allowed: bool
    reason_code: str


def evaluate_memory_scope_write(
    *,
    governance_runtime: GovernanceRuntime | None,
    run_id: str,
    scope: str,
    producer_role: str,
    visibility: str,
    override_approval_id: str | None = None,
    memory_target: str | None = None,
    expected_state_version: int | None = None,
    execution_contract_hash: str | None = None,
    resume_token_ref: str | None = None,
) -> MemoryScopeDecision:
    if governance_runtime is None:
        return MemoryScopeDecision(
            allowed=True,
            requires_approval=False,
            reason_code="RULE_ROUTE",
            approval_id=None,
        )

    decision, ticket = governance_runtime.evaluate_memory_write(
        run_id=run_id,
        scope=scope,
        producer_role=producer_role,
        visibility=visibility,
        override_approval_id=override_approval_id,
        memory_target=memory_target,
        expected_state_version=expected_state_version,
        execution_contract_hash=execution_contract_hash,
        resume_token_ref=resume_token_ref,
    )

    if decision.action == GovernanceAction.DENY:
        return MemoryScopeDecision(
            allowed=False,
            requires_approval=False,
            reason_code=decision.reason_code,
            approval_id=None,
        )
    if decision.action == GovernanceAction.REQUIRE_APPROVAL:
        return MemoryScopeDecision(
            allowed=False,
            requires_approval=True,
            reason_code=decision.reason_code,
            approval_id=ticket.approval_id if ticket else None,
        )

    return MemoryScopeDecision(
        allowed=True,
        requires_approval=False,
        reason_code=decision.reason_code,
        approval_id=decision.approval_id,
    )


def validate_memory_access(
    *,
    declared_scopes: list[str],
    requested_scope: str,
    requested_visibility: str,
) -> MemoryAccessValidation:
    normalized_scopes = {item.strip().lower() for item in declared_scopes if item.strip()}
    scope = requested_scope.strip().lower()
    visibility = requested_visibility.strip().lower()

    if scope not in normalized_scopes:
        return MemoryAccessValidation(allowed=False, reason_code="AGENT_SCOPE_DENY")
    if scope == "session" and visibility != "private":
        return MemoryAccessValidation(allowed=False, reason_code="AGENT_SCOPE_VISIBILITY_DENY")
    if scope in {"team", "case"} and visibility not in {"team", "private"}:
        return MemoryAccessValidation(allowed=False, reason_code="AGENT_SCOPE_VISIBILITY_DENY")
    return MemoryAccessValidation(allowed=True, reason_code="RULE_ROUTE")


def write_scoped_memory(
    *,
    memory_manager: MemoryManager | None,
    session_id: str,
    task_type: str,
    user_input: str,
    assistant_output: str,
    scope: str,
    team_id: str,
    case_id: str,
    job_id: str,
    producer_agent_id: str,
    producer_role: str,
    visibility: str,
    memory_target: str | None = None,
    expected_state_version: int | None = None,
    memory_runtime_bridge: MemoryRuntimeBridge | None = None,
) -> dict[str, object]:
    if memory_runtime_bridge is not None and memory_runtime_bridge.enabled:
        result = memory_runtime_bridge.propose_post_run_write(
            run_id=session_id,
            actor_id=producer_agent_id,
            role=producer_role,
            user_input=user_input,
            assistant_output=assistant_output,
            scope=scope,
            owner_type=_owner_type(scope),
            owner=_owner_for_scope(
                scope=scope,
                team_id=team_id,
                case_id=case_id,
                job_id=job_id,
                producer_agent_id=producer_agent_id,
            ),
            visibility=visibility,
            memory_target=memory_target,
            expected_state_version=expected_state_version,
            agent_id=producer_agent_id,
        )
        return {
            "written": result.status == "written",
            "reason": result.status,
            "record_id": result.memory_id,
            "salience_score": 0.0,
            "conflict_detected": result.conflict_detected,
            "expected_state_version": expected_state_version,
            "committed_state_version": result.state_version,
            "memory_target": memory_target,
            "proposal_id": result.proposal_id,
            "evidence_ref": result.evidence_ref,
            "blocking_reasons": result.blocking_reasons,
        }
    if memory_manager is None:
        return {
            "written": False,
            "reason": "memory_manager_missing",
            "record_id": None,
            "salience_score": 0.0,
        }

    writer = getattr(memory_manager, "maybe_write_scoped", None)
    if callable(writer):
        result = writer(
            session_id=session_id,
            task_type=task_type,
            user_input=user_input,
            assistant_output=assistant_output,
            scope=scope,
            team_id=team_id,
            case_id=case_id,
            job_id=job_id,
            producer_agent_id=producer_agent_id,
            producer_role=producer_role,
            visibility=visibility,
            memory_target=memory_target,
            expected_state_version=expected_state_version,
            expert_payload=None,
        )
        return {
            "written": result.written,
            "reason": result.reason,
            "record_id": result.record_id,
            "salience_score": result.salience_score,
            "conflict_detected": getattr(result, "conflict_detected", False),
            "expected_state_version": getattr(result, "expected_state_version", None),
            "committed_state_version": getattr(result, "committed_state_version", None),
            "memory_target": getattr(result, "memory_target", memory_target),
        }

    # Backward-compatible fallback for older MemoryManager API.
    result = memory_manager.maybe_write(
        session_id=session_id,
        task_type=task_type,
        user_input=user_input,
        assistant_output=assistant_output,
        expert_payload=None,
    )
    return {
        "written": result.written,
        "reason": result.reason,
        "record_id": result.record_id,
        "salience_score": result.salience_score,
        "conflict_detected": False,
        "expected_state_version": expected_state_version,
        "committed_state_version": None,
        "memory_target": memory_target,
    }


def read_scoped_memory(
    *,
    memory_manager: MemoryManager | None,
    query: str,
    scope: str,
    team_id: str,
    case_id: str,
    job_id: str,
    visibility: str,
    limit: int = 4,
    memory_runtime_bridge: MemoryRuntimeBridge | None = None,
    producer_agent_id: str | None = None,
) -> dict[str, object]:
    if memory_runtime_bridge is not None and memory_runtime_bridge.enabled:
        pack = memory_runtime_bridge.retrieve_context(
            RuntimeMemoryRequest(
                run_id=job_id,
                query=query,
                actor_id=producer_agent_id or team_id or "team-runtime",
                requester_role="team_runtime",
                agent_id=producer_agent_id,
                team_id=team_id,
                case_id=case_id,
            )
        )
        section = MemoryPromptInjector.build_section(
            pack,
            max_chars=memory_runtime_bridge.config.memory.runtime.max_context_chars,
        )
        snippets = [section] if section else []
        return {
            "snippets": snippets,
            "count": len(pack.hits),
            "reason": pack.status,
            "refs": [hit.memory_id for hit in pack.hits],
            "fingerprint": pack.retrieval_fingerprint,
            "records": [
                {
                    "memory_id": hit.memory_id,
                    "content_hash": hit.content_hash,
                    "scope": hit.scope,
                    "visibility": hit.visibility,
                }
                for hit in pack.hits
            ],
            "evidence_ref": pack.evidence_ref,
        }
    if memory_manager is None:
        return {
            "snippets": [],
            "count": 0,
            "reason": "memory_manager_missing",
            "refs": [],
            "fingerprint": None,
        }

    bundle_reader = getattr(memory_manager, "context_bundle_scoped", None)
    effective_job_id = job_id if scope.strip().lower() == "session" else None
    if callable(bundle_reader):
        bundle = bundle_reader(
            query,
            scope=scope,
            team_id=team_id,
            case_id=case_id,
            job_id=effective_job_id,
            visibility=visibility,
            limit=limit,
        )
        snippets = [str(item) for item in bundle.get("snippets", [])]
        refs = [int(item) for item in bundle.get("refs", []) if str(item).strip()]
        return {
            "snippets": snippets,
            "count": len(snippets),
            "reason": "ok" if snippets else "empty",
            "refs": refs,
            "fingerprint": bundle.get("fingerprint"),
            "records": bundle.get("records", []),
        }

    reader = getattr(memory_manager, "context_snippets_scoped", None)
    if callable(reader):
        snippets = reader(
            query,
            scope=scope,
            team_id=team_id,
            case_id=case_id,
            job_id=effective_job_id,
            visibility=visibility,
            limit=limit,
        )
        return {
            "snippets": snippets,
            "count": len(snippets),
            "reason": "ok" if snippets else "empty",
            "refs": [],
            "fingerprint": None,
        }

    fallback = getattr(memory_manager, "context_snippets", None)
    if callable(fallback):
        snippets = fallback(query, limit=limit)
        return {
            "snippets": snippets,
            "count": len(snippets),
            "reason": "fallback" if snippets else "fallback_empty",
            "refs": [],
            "fingerprint": None,
        }

    return {
        "snippets": [],
        "count": 0,
        "reason": "reader_missing",
        "refs": [],
        "fingerprint": None,
    }


def _owner_type(scope: str) -> str:
    return {
        "agent": "agent",
        "team": "team",
        "case": "case",
        "project": "project",
        "organization": "org",
    }.get(scope, "user")


def _owner_for_scope(
    *,
    scope: str,
    team_id: str,
    case_id: str,
    job_id: str,
    producer_agent_id: str,
) -> str:
    return {
        "agent": producer_agent_id,
        "team": team_id,
        "case": case_id,
        "project": job_id,
        "organization": "organization",
    }.get(scope, producer_agent_id)
