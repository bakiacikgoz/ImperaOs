from __future__ import annotations

from pathlib import Path

from imperaos.memory.access_evaluator import MemoryAccessEvaluator
from imperaos.memory.evidence import MemoryEvidenceWriter
from imperaos.memory.models import MemoryPolicyAction, MemoryPolicyDecision, sha256_text, stable_id
from imperaos.memory.redaction import MemoryRedactor
from imperaos.memory.workspace_models import (
    MemoryAccessDecision,
    MemoryAccessRequest,
    WorkspaceMemoryAuthorityHealth,
    WorkspaceMemoryQueryRequest,
    WorkspaceMemoryQueryResult,
    WorkspaceMemoryRecord,
    WorkspaceMemoryTombstoneRequest,
    WorkspaceMemoryTombstoneResult,
    WorkspaceMemoryWriteDecision,
    WorkspaceMemoryWriteRequest,
    make_memory_id,
)
from imperaos.memory.workspace_store import WorkspaceMemoryStore
from imperaos.runtime.config import RuntimeConfig


class WorkspaceMemoryAuthority:
    def __init__(
        self,
        *,
        config: RuntimeConfig,
        store: WorkspaceMemoryStore,
        evidence_writer: MemoryEvidenceWriter,
        redactor: MemoryRedactor | None = None,
    ) -> None:
        self.config = config
        self.store = store
        self.evidence_writer = evidence_writer
        self.redactor = redactor or MemoryRedactor()
        self.evaluator = MemoryAccessEvaluator(store=store)

    @property
    def enabled(self) -> bool:
        return bool(self.config.memory.workspace_authority.enabled)

    def query(self, request: WorkspaceMemoryQueryRequest) -> WorkspaceMemoryQueryResult:
        query_hash = sha256_text(request.query)
        decision = self.evaluator.evaluate(
            MemoryAccessRequest(
                workspaceId=request.workspace_id,
                principalId=request.principal_id,
                action="read",
                scopeType=request.scope_type,
                scopeId=request.scope_id,
                permission=f"memory.read.{request.scope_type}",
                purpose=request.purpose,
                classification=request.classification,
            )
        )
        _, evidence_ref = self._write_evidence(
            event_type="workspace_memory_query",
            decision=decision,
            actor_id=request.principal_id,
            content_hash=query_hash,
            scope=request.scope_type,
        )
        decision = decision.model_copy(update={"evidence_ref": evidence_ref})
        if decision.action != "allow":
            return WorkspaceMemoryQueryResult(
                status="denied",
                decision=decision,
                records=[],
                queryHash=query_hash,
                evidenceRef=evidence_ref,
            )
        records = self.store.query_records(
            workspace_id=request.workspace_id,
            scope_type=request.scope_type,
            scope_id=request.scope_id,
            query=request.query,
            limit=request.limit,
            include_secret_like=False,
        )
        return WorkspaceMemoryQueryResult(
            status="pass" if records else "empty",
            decision=decision,
            records=records,
            queryHash=query_hash,
            evidenceRef=evidence_ref,
        )

    def propose_or_write(
        self,
        request: WorkspaceMemoryWriteRequest,
    ) -> WorkspaceMemoryWriteDecision:
        redaction = self.redactor.redact_candidate(candidate_text=request.summary)
        classification = "secret_like" if redaction.secret_detected else request.classification
        decision = self.evaluator.evaluate(
            MemoryAccessRequest(
                workspaceId=request.workspace_id,
                principalId=request.principal_id,
                action="write",
                scopeType=request.scope_type,
                scopeId=request.scope_id,
                permission=f"memory.write.{request.scope_type}",
                purpose=request.reason,
                classification=classification,
            )
        )
        if redaction.secret_detected and decision.action != "deny":
            decision = MemoryAccessDecision(
                action="deny",
                reasonCode="MEMORY_CLASSIFICATION_SECRET_LIKE_DENIED",
                matchedRules=decision.matched_rules,
            )
        memory_id = make_memory_id(
            request.workspace_id,
            request.scope_type,
            request.scope_id,
            request.memory_target or redaction.content_hash,
        )
        _, evidence_ref = self._write_evidence(
            event_type="workspace_memory_write",
            decision=decision,
            actor_id=request.principal_id,
            memory_id=memory_id,
            content_hash=redaction.content_hash,
            scope=request.scope_type,
        )
        decision = decision.model_copy(update={"evidence_ref": evidence_ref})
        if decision.action == "deny":
            return WorkspaceMemoryWriteDecision(
                status="denied",
                decision=decision,
                contentHash=redaction.content_hash,
                evidenceRef=evidence_ref,
                blockingReasons=[decision.reason_code],
            )

        record = WorkspaceMemoryRecord(
            memoryId=memory_id,
            workspaceId=request.workspace_id,
            scopeType=request.scope_type,
            scopeId=request.scope_id,
            ownerPrincipalId=request.principal_id,
            sourceAgentId=request.source_agent_id,
            sourceRunId=request.source_run_id,
            memoryTarget=request.memory_target,
            contentHash=redaction.content_hash,
            summary=redaction.redacted_summary,
            redactedPreview=redaction.redacted_summary[:500],
            classification=classification if classification != "secret_like" else "restricted",
            policyTags=tuple(redaction.policy_tags),
        )
        if decision.action in {"proposal_only", "requires_approval"}:
            proposal_id = stable_id(
                "wm_prop",
                request.workspace_id,
                request.principal_id,
                request.scope_type,
                request.scope_id,
                redaction.content_hash,
            )
            self.store.record_proposal(
                proposal_id=proposal_id,
                workspace_id=request.workspace_id,
                principal_id=request.principal_id,
                payload={
                    "schemaVersion": "workspace-memory-proposal/v1",
                    "proposalId": proposal_id,
                    "workspaceId": request.workspace_id,
                    "principalId": request.principal_id,
                    "scopeType": request.scope_type,
                    "scopeId": request.scope_id,
                    "memoryTarget": request.memory_target,
                    "contentHash": redaction.content_hash,
                    "summaryHash": sha256_text(redaction.redacted_summary),
                    "decision": decision.model_dump(mode="json", by_alias=True),
                    "rawContentIncluded": False,
                },
            )
            return WorkspaceMemoryWriteDecision(
                status=decision.action,
                decision=decision,
                proposalId=proposal_id,
                contentHash=redaction.content_hash,
                evidenceRef=evidence_ref,
                blockingReasons=[decision.reason_code] if decision.requires_approval else [],
            )

        commit = self.store.write_record(
            record,
            expected_state_version=request.expected_state_version,
            changed_by_principal_id=request.principal_id,
            change_reason=request.reason,
        )
        if commit.status == "conflict" and commit.conflict is not None:
            return WorkspaceMemoryWriteDecision(
                status="conflict",
                decision=decision,
                conflictId=commit.conflict.conflict_id,
                contentHash=redaction.content_hash,
                evidenceRef=evidence_ref,
                blockingReasons=["MEMORY_WRITE_CONFLICT"],
            )
        return WorkspaceMemoryWriteDecision(
            status="committed",
            decision=decision,
            memoryId=commit.memory_id,
            stateVersion=commit.state_version,
            contentHash=redaction.content_hash,
            evidenceRef=evidence_ref,
        )

    def tombstone(self, request: WorkspaceMemoryTombstoneRequest) -> WorkspaceMemoryTombstoneResult:
        decision = self.evaluator.evaluate(
            MemoryAccessRequest(
                workspaceId=request.workspace_id,
                principalId=request.principal_id,
                action="admin",
                scopeType="personal",
                scopeId=request.principal_id,
                permission="memory.admin.retention",
                purpose=request.reason,
            )
        )
        _, evidence_ref = self._write_evidence(
            event_type="workspace_memory_tombstone",
            decision=decision,
            actor_id=request.principal_id,
            memory_id=request.memory_id,
            scope="retention",
        )
        if decision.action != "allow":
            return WorkspaceMemoryTombstoneResult(
                status="denied",
                memoryId=request.memory_id,
                evidenceRef=evidence_ref,
            )
        result = self.store.tombstone_record(request)
        return result.model_copy(update={"evidence_ref": evidence_ref})

    def health(self, workspace_id: str | None = None) -> WorkspaceMemoryAuthorityHealth:
        if not self.enabled:
            return WorkspaceMemoryAuthorityHealth(status="disabled")
        stats = self.store.stats(workspace_id)
        blocking_reasons: list[str] = []
        status = "available"
        if stats["workspaceCount"] == 0 or stats["principalCount"] == 0:
            status = "setup_required"
            blocking_reasons.append("MEMORY_WORKSPACE_AUTHORITY_SETUP_REQUIRED")
        return WorkspaceMemoryAuthorityHealth(
            status=status,
            workspaceCount=stats["workspaceCount"],
            principalCount=stats["principalCount"],
            activeScopeCount=stats["activeScopeCount"],
            pendingProposalCount=stats["pendingProposalCount"],
            pendingConflictCount=stats["pendingConflictCount"],
            networkListenerEnabled=False,
            rawContentExposed=False,
            blockingReasons=blocking_reasons,
        )

    def semantic_search(self, request: object) -> object:
        from imperaos.memory.semantic.service import SemanticMemoryService

        return SemanticMemoryService(
            config=self.config,
            authority=self,
        ).search(request)

    def _write_evidence(
        self,
        *,
        event_type: str,
        decision: MemoryAccessDecision,
        actor_id: str,
        memory_id: str | None = None,
        content_hash: str | None = None,
        scope: str | None = None,
    ) -> tuple[object, str]:
        return self.evidence_writer.write_event(
            event_type=event_type,
            policy_decision=_policy_decision(decision),
            memory_id=memory_id,
            actor_hash=sha256_text(actor_id),
            content_hash=content_hash,
            scope=scope,
            visibility=_evidence_visibility(scope),
        )


def build_workspace_memory_authority(
    config: RuntimeConfig,
    *,
    evidence_root: str | Path = "artifacts/memory-authority",
) -> WorkspaceMemoryAuthority:
    workspace_config = config.memory.workspace_authority
    return WorkspaceMemoryAuthority(
        config=config,
        store=WorkspaceMemoryStore(workspace_config.db_path),
        evidence_writer=MemoryEvidenceWriter(evidence_root),
    )


def _policy_decision(decision: MemoryAccessDecision) -> MemoryPolicyDecision:
    action = {
        "allow": MemoryPolicyAction.ALLOW,
        "deny": MemoryPolicyAction.DENY,
        "proposal_only": MemoryPolicyAction.PROPOSAL_ONLY,
        "requires_approval": MemoryPolicyAction.REQUIRE_APPROVAL,
    }[decision.action]
    return MemoryPolicyDecision(
        decision=action,
        reasonCode=decision.reason_code,
        matchedRulePath=",".join(decision.matched_rules) or None,
        redactionRequired=decision.redaction_required,
        indexWriteAllowed=decision.action == "allow",
        blockingReasons=[] if decision.action == "allow" else [decision.reason_code],
    )


def _evidence_visibility(scope: str | None) -> str | None:
    return {
        "personal": "private",
        "agent": "agent",
        "team": "team",
        "case": "team",
        "project": "project",
        "organization": "organization",
    }.get(scope or "")
