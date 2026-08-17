from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

from imperaos.memory.evidence import MemoryEvidenceWriter
from imperaos.memory.indexes.base import SemanticMemoryIndex
from imperaos.memory.indexes.sqlite_text import SqliteTextMemoryIndex
from imperaos.memory.models import (
    MemoryAuthorityRecordsSummary,
    MemoryAuthoritySnapshot,
    MemoryEvidenceSummary,
    MemoryIndexRecord,
    MemoryPolicyAction,
    MemoryPrivacySummary,
    MemoryRecordV3,
    MemoryRetrievalRequest,
    MemoryRetrievalResult,
    MemoryScopeSummary,
    MemoryTombstoneRequest,
    MemoryWriteProposal,
    MemoryWriteResult,
    RetentionClass,
    hash_identity,
    sha256_text,
    stable_id,
    utc_now,
)
from imperaos.memory.policy import (
    MemoryPolicyEvaluator,
    MemoryRetrievalPolicyContext,
    MemoryWritePolicyContext,
)
from imperaos.memory.redaction import MemoryRedactor
from imperaos.memory.store_v3 import MemoryStoreV3
from imperaos.runtime.config import RuntimeConfig


class MemoryAuthority:
    def __init__(
        self,
        *,
        config: RuntimeConfig,
        store: MemoryStoreV3,
        policy: MemoryPolicyEvaluator,
        redactor: MemoryRedactor,
        index: SemanticMemoryIndex,
        evidence: MemoryEvidenceWriter,
    ) -> None:
        self.config = config
        self.store = store
        self.policy = policy
        self.redactor = redactor
        self.index = index
        self.evidence = evidence

    def propose_write(self, proposal: MemoryWriteProposal) -> MemoryWriteResult:
        redaction = self.redactor.redact_candidate(
            candidate_text=proposal.candidate_summary or proposal.candidate_text,
            source_metadata={"proposal_id": proposal.proposal_id},
            privacy_mode=self.config.privacy_mode,
        )
        decision = self.policy.evaluate_write(
            MemoryWritePolicyContext(proposal=proposal, redaction=redaction, config=self.config)
        )
        decision_action = str(decision.decision)
        if decision_action == MemoryPolicyAction.DENY.value:
            _event, evidence_ref = self.evidence.write_event(
                event_type="memory.write.denied",
                policy_decision=decision,
                proposal_id=proposal.proposal_id,
                actor_hash=proposal.actor_id_hash,
                content_hash=redaction.content_hash,
                scope=proposal.scope,
                visibility=proposal.visibility,
            )
            self.store.record_event(
                event_id=_event.event_id,
                event_type=_event.event_type,
                memory_id=None,
                proposal_id=proposal.proposal_id,
                actor_id_hash=proposal.actor_id_hash,
                agent_id=proposal.agent_id,
                policy_decision=decision.model_dump(mode="json", by_alias=True),
                event_hash=_event.event_hash,
                evidence_ref=evidence_ref,
            )
            return MemoryWriteResult(
                status="denied",
                proposalId=proposal.proposal_id,
                policyDecision=decision,
                evidenceRef=evidence_ref,
                contentHash=redaction.content_hash,
                blockingReasons=decision.blocking_reasons,
            )
        if decision_action in {
            MemoryPolicyAction.REQUIRE_APPROVAL.value,
            MemoryPolicyAction.PROPOSAL_ONLY.value,
        }:
            event_type = (
                "memory.write.approval_required"
                if decision_action == MemoryPolicyAction.REQUIRE_APPROVAL.value
                else "memory.write.proposal_only"
            )
            _event, evidence_ref = self.evidence.write_event(
                event_type=event_type,
                policy_decision=decision,
                proposal_id=proposal.proposal_id,
                actor_hash=proposal.actor_id_hash,
                content_hash=redaction.content_hash,
                scope=proposal.scope,
                visibility=proposal.visibility,
            )
            self.store.record_event(
                event_id=_event.event_id,
                event_type=_event.event_type,
                memory_id=None,
                proposal_id=proposal.proposal_id,
                actor_id_hash=proposal.actor_id_hash,
                agent_id=proposal.agent_id,
                policy_decision=decision.model_dump(mode="json", by_alias=True),
                event_hash=_event.event_hash,
                evidence_ref=evidence_ref,
            )
            return MemoryWriteResult(
                status="approval_required"
                if decision_action == MemoryPolicyAction.REQUIRE_APPROVAL.value
                else "proposal_only",
                proposalId=proposal.proposal_id,
                policyDecision=decision,
                evidenceRef=evidence_ref,
                contentHash=redaction.content_hash,
            )

        memory_id = stable_id(
            "mem",
            proposal.idempotency_key,
            proposal.scope,
            proposal.owner_id_hash,
            redaction.content_hash,
        )
        now = utc_now()
        ttl_days = int(getattr(self.config, "memory_ttl_days", 30) or 30)
        expires_at = now + timedelta(days=ttl_days)
        record = MemoryRecordV3(
            memoryId=memory_id,
            scope=proposal.scope,
            ownerType=proposal.owner_type,
            ownerIdHash=proposal.owner_id_hash,
            visibility=proposal.visibility,
            namespace=proposal.namespace,
            memoryTarget=proposal.memory_target,
            stateVersion=max(1, (proposal.expected_state_version or 0) + 1),
            contentSummary=redaction.redacted_summary,
            contentHash=redaction.content_hash,
            salience=0.72,
            confidence=0.76,
            sourceType="run",
            sourceRunId=proposal.source_run_id,
            sourceAgentId=proposal.agent_id,
            sourceUserHash=proposal.actor_id_hash,
            policyTags=redaction.policy_tags,
            retentionClass=decision.retention_override or RetentionClass.STANDARD,
            ttlDays=ttl_days,
            expiresAt=expires_at,
            provenance={
                "proposalId": proposal.proposal_id,
                "reasonHash": sha256_text(proposal.reason),
                "rawContentIncluded": False,
            },
            createdAt=now,
            updatedAt=now,
        )
        write = self.store.write_record(
            record,
            idempotency_key=proposal.idempotency_key,
            expected_state_version=proposal.expected_state_version,
        )
        if write.conflict_detected:
            _event, evidence_ref = self.evidence.write_event(
                event_type="memory.write.conflict",
                policy_decision=decision,
                proposal_id=proposal.proposal_id,
                actor_hash=proposal.actor_id_hash,
                content_hash=redaction.content_hash,
                scope=proposal.scope,
                visibility=proposal.visibility,
            )
            self.store.record_event(
                event_id=_event.event_id,
                event_type=_event.event_type,
                memory_id=None,
                proposal_id=proposal.proposal_id,
                actor_id_hash=proposal.actor_id_hash,
                agent_id=proposal.agent_id,
                policy_decision=decision.model_dump(mode="json", by_alias=True),
                event_hash=_event.event_hash,
                evidence_ref=evidence_ref,
            )
            return MemoryWriteResult(
                status="conflict",
                proposalId=proposal.proposal_id,
                policyDecision=decision,
                evidenceRef=evidence_ref,
                contentHash=redaction.content_hash,
                conflictDetected=True,
                blockingReasons=write.blocking_reasons or ["MEMORY_CONFLICT"],
            )

        record_for_index = MemoryIndexRecord(
            memoryId=write.memory_id or record.memory_id,
            scope=record.scope,
            ownerType=record.owner_type,
            ownerIdHash=record.owner_id_hash,
            visibility=record.visibility,
            namespace=record.namespace,
            text=record.content_summary,
            contentHash=record.content_hash,
        )
        if decision.index_write_allowed:
            self.index.add([record_for_index])
        _event, evidence_ref = self.evidence.write_event(
            event_type="memory.write.allowed",
            policy_decision=decision,
            memory_id=write.memory_id or record.memory_id,
            proposal_id=proposal.proposal_id,
            actor_hash=proposal.actor_id_hash,
            content_hash=redaction.content_hash,
            scope=proposal.scope,
            visibility=proposal.visibility,
        )
        self.store.record_event(
            event_id=_event.event_id,
            event_type=_event.event_type,
            memory_id=write.memory_id or record.memory_id,
            proposal_id=proposal.proposal_id,
            actor_id_hash=proposal.actor_id_hash,
            agent_id=proposal.agent_id,
            policy_decision=decision.model_dump(mode="json", by_alias=True),
            event_hash=_event.event_hash,
            evidence_ref=evidence_ref,
        )
        return MemoryWriteResult(
            status="written",
            proposalId=proposal.proposal_id,
            memoryId=write.memory_id or record.memory_id,
            policyDecision=decision,
            evidenceRef=evidence_ref,
            contentHash=redaction.content_hash,
            stateVersion=write.committed_state_version,
        )

    def retrieve(self, request: MemoryRetrievalRequest) -> MemoryRetrievalResult:
        decision = self.policy.evaluate_retrieval(
            MemoryRetrievalPolicyContext(request=request, config=self.config)
        )
        if str(decision.decision) == MemoryPolicyAction.DENY.value:
            _event, evidence_ref = self.evidence.write_event(
                event_type="memory.retrieve.denied",
                policy_decision=decision,
                actor_hash=request.actor_id_hash,
                content_hash=sha256_text(request.query),
            )
            return MemoryRetrievalResult(
                status="denied",
                queryHash=sha256_text(request.query),
                hits=[],
                deniedScopes=decision.blocking_reasons,
                policyDecision=decision,
                retrievalFingerprint=None,
                evidenceRef=evidence_ref,
                indexBackend=self.index.backend_name,
                rawContentIncluded=False,
            )
        hits = self.index.search(
            query=request.query,
            scope_filters=request.scope_filters,
            visibility_filters=request.visibility_filters,
            limit=request.limit,
        )
        if not request.include_content:
            hits = [hit.model_copy(update={"content_summary": None}) for hit in hits]
        fingerprint = sha256_text(
            json.dumps([hit.memory_id for hit in hits], sort_keys=True)
        )
        _event, evidence_ref = self.evidence.write_event(
            event_type="memory.retrieve.allowed",
            policy_decision=decision,
            actor_hash=request.actor_id_hash,
            content_hash=sha256_text(request.query),
        )
        return MemoryRetrievalResult(
            status="pass" if hits else "empty",
            queryHash=sha256_text(request.query),
            hits=hits,
            policyDecision=decision,
            retrievalFingerprint=fingerprint,
            evidenceRef=evidence_ref,
            indexBackend=self.index.backend_name,
            rawContentIncluded=False,
        )

    def tombstone(self, request: MemoryTombstoneRequest):
        decision = self.policy.evaluate_retrieval(
            MemoryRetrievalPolicyContext(
                request=MemoryRetrievalRequest(
                    actorIdHash=request.actor_id_hash,
                    requesterRole="operator",
                    query=request.memory_id,
                    allowedScopes=["personal", "agent", "team", "case", "project", "organization"],
                    scopeFilters=[],
                    visibilityFilters=[],
                    purpose="audit",
                ),
                config=self.config,
            )
        )
        ok = self.store.tombstone(
            memory_id=request.memory_id,
            actor_id_hash=request.actor_id_hash,
            reason=request.reason,
        )
        event, evidence_ref = self.evidence.write_event(
            event_type="memory.lifecycle.tombstoned",
            policy_decision=decision,
            memory_id=request.memory_id,
            actor_hash=request.actor_id_hash,
        )
        self.store.record_event(
            event_id=event.event_id,
            event_type=event.event_type,
            memory_id=request.memory_id,
            proposal_id=None,
            actor_id_hash=request.actor_id_hash,
            agent_id=None,
            policy_decision=decision.model_dump(mode="json", by_alias=True),
            event_hash=event.event_hash,
            evidence_ref=evidence_ref,
        )
        return {"status": "tombstoned" if ok else "missing", "evidenceRef": evidence_ref}

    def stats(self) -> dict[str, object]:
        return {
            "status": "pass",
            **self.store.stats(),
            "index": self.index.status().model_dump(mode="json", by_alias=True),
        }

    def snapshot(self) -> MemoryAuthoritySnapshot:
        stats = self.store.stats()
        records = stats["records"]
        index_status = self.index.status()
        return MemoryAuthoritySnapshot(
            enabled=bool(getattr(self.config.memory, "v3_enabled", False)),
            authorityStatus=(
                "pass" if str(index_status.status) in {"pass", "disabled"} else "degraded"
            ),
            records=MemoryAuthorityRecordsSummary(**records),
            scopes=[MemoryScopeSummary(**item) for item in stats["scopes"]],
            index=index_status,
            privacy=MemoryPrivacySummary(
                rawPromptPersistence=False,
                rawResponsePersistence=False,
                primaryUiRawContent=False,
            ),
            evidence=MemoryEvidenceSummary(
                lastArtifactRef="artifacts/memory-governance/latest.json"
            ),
            warnings=(
                [] if getattr(self.config.memory, "v3_enabled", False) else ["MEMORY_V3_DISABLED"]
            ),
        )


def build_memory_authority(
    config: RuntimeConfig,
    *,
    evidence_root: str | Path = "artifacts/memory-governance",
) -> MemoryAuthority:
    store = MemoryStoreV3(config.memory.db_path)
    index = SqliteTextMemoryIndex(store=store)
    return MemoryAuthority(
        config=config,
        store=store,
        policy=MemoryPolicyEvaluator(config=config),
        redactor=MemoryRedactor(),
        index=index,
        evidence=MemoryEvidenceWriter(evidence_root),
    )


def proposal_from_cli(
    *,
    actor: str,
    scope: str,
    owner_type: str,
    owner: str,
    visibility: str,
    text: str,
    role: str,
    reason: str,
    memory_target: str | None = None,
    expected_state_version: int | None = None,
    agent_id: str | None = None,
    source_run_id: str | None = None,
) -> MemoryWriteProposal:
    owner_hash = hash_identity(owner)
    actor_hash = hash_identity(actor)
    return MemoryWriteProposal(
        proposalId=stable_id("mem_prop", actor_hash, scope, owner_hash, text),
        actorIdHash=actor_hash,
        agentId=agent_id,
        producerRole=role,
        scope=scope,
        ownerType=owner_type,
        ownerIdHash=owner_hash,
        visibility=visibility,
        memoryTarget=memory_target,
        expectedStateVersion=expected_state_version,
        candidateText=text,
        sourceRunId=source_run_id,
        reason=reason,
        idempotencyKey=stable_id("mem_idem", actor_hash, scope, owner_hash, text),
    )
