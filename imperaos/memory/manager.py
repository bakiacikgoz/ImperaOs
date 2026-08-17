from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from uuid import uuid4

from imperaos.memory.persistent_store import MemoryRecord, PersistentMemoryStore
from imperaos.memory.retrieval_ranker import rank_records
from imperaos.memory.salience_gate import SalienceDecision, SalienceGate


@dataclass(slots=True)
class MemoryWriteResult:
    written: bool
    salience_score: float
    reason: str
    record_id: int | None
    conflict_detected: bool = False
    expected_state_version: int | None = None
    committed_state_version: int | None = None
    memory_target: str | None = None


class MemoryManager:
    """Coordinates salience gating and persistent memory writes."""

    def __init__(
        self,
        *,
        enabled: bool,
        store: PersistentMemoryStore | None,
        gate: SalienceGate,
        max_rows: int = 5000,
        ttl_days: int = 30,
        rank_salience_weight: float = 0.7,
        rank_recency_weight: float = 0.3,
    ):
        self.enabled = enabled
        self.store = store
        self.gate = gate
        self.max_rows = max_rows
        self.ttl_days = ttl_days
        self.rank_salience_weight = rank_salience_weight
        self.rank_recency_weight = rank_recency_weight
        self._write_attempts = 0
        self._writes_accepted = 0
        self._dedup_hits = 0
        self._retrieval_queries = 0
        self._retrieval_hits = 0
        self._retrieval_useful = 0

    def maybe_write(
        self,
        *,
        session_id: str,
        task_type: str,
        user_input: str,
        assistant_output: str,
        expert_payload: dict[str, object] | None = None,
    ) -> MemoryWriteResult:
        self._write_attempts += 1
        if not self.enabled:
            return MemoryWriteResult(
                written=False,
                salience_score=0.0,
                reason="memory_disabled",
                record_id=None,
            )
        if self.store is None:
            return MemoryWriteResult(
                written=False,
                salience_score=0.0,
                reason="memory_store_missing",
                record_id=None,
            )

        decision: SalienceDecision = self.gate.evaluate(
            task_type=task_type,
            user_input=user_input,
            assistant_output=assistant_output,
            expert_payload=expert_payload,
        )
        if not decision.should_write:
            return MemoryWriteResult(
                written=False,
                salience_score=decision.salience_score,
                reason=decision.reason,
                record_id=None,
            )

        content = f"User: {user_input}\nAssistant: {assistant_output}"
        status = self.store.write_with_status(
            session_id=session_id,
            task_type=task_type,
            content=content,
            salience=decision.salience_score,
            metadata={"event_id": str(uuid4())},
            ttl_days=self.ttl_days,
        )
        record_id = status.record_id
        if record_id is not None:
            self._writes_accepted += 1
        if status.dedup_hit:
            self._dedup_hits += 1
        self.store.prune_to_limit(self.max_rows)
        return MemoryWriteResult(
            written=record_id is not None and not status.conflict_detected,
            salience_score=decision.salience_score,
            reason=("memory_conflict" if status.conflict_detected else decision.reason),
            record_id=record_id,
            conflict_detected=status.conflict_detected,
            expected_state_version=status.expected_state_version,
            committed_state_version=status.committed_state_version,
            memory_target=status.memory_target,
        )

    def maybe_write_scoped(
        self,
        *,
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
        expert_payload: dict[str, object] | None = None,
    ) -> MemoryWriteResult:
        self._write_attempts += 1
        if not self.enabled:
            return MemoryWriteResult(
                written=False,
                salience_score=0.0,
                reason="memory_disabled",
                record_id=None,
                expected_state_version=expected_state_version,
                memory_target=memory_target,
            )
        if self.store is None:
            return MemoryWriteResult(
                written=False,
                salience_score=0.0,
                reason="memory_store_missing",
                record_id=None,
                expected_state_version=expected_state_version,
                memory_target=memory_target,
            )

        decision: SalienceDecision = self.gate.evaluate(
            task_type=task_type,
            user_input=user_input,
            assistant_output=assistant_output,
            expert_payload=expert_payload,
        )
        if not decision.should_write:
            return MemoryWriteResult(
                written=False,
                salience_score=decision.salience_score,
                reason=decision.reason,
                record_id=None,
                expected_state_version=expected_state_version,
                memory_target=memory_target,
            )

        content = f"User: {user_input}\nAssistant: {assistant_output}"
        status = self.store.write_with_status(
            session_id=session_id,
            task_type=task_type,
            content=content,
            salience=decision.salience_score,
            metadata={"event_id": str(uuid4())},
            ttl_days=self.ttl_days,
            scope=scope,
            team_id=team_id,
            case_id=case_id,
            job_id=job_id,
            producer_agent_id=producer_agent_id,
            producer_role=producer_role,
            visibility=visibility,
            memory_target=memory_target,
            expected_state_version=expected_state_version,
        )
        record_id = status.record_id
        if record_id is not None and not status.conflict_detected:
            self._writes_accepted += 1
        if status.dedup_hit:
            self._dedup_hits += 1
        self.store.prune_to_limit(self.max_rows)
        return MemoryWriteResult(
            written=record_id is not None and not status.conflict_detected,
            salience_score=decision.salience_score,
            reason=("memory_conflict" if status.conflict_detected else decision.reason),
            record_id=record_id,
            conflict_detected=status.conflict_detected,
            expected_state_version=status.expected_state_version,
            committed_state_version=status.committed_state_version,
            memory_target=status.memory_target,
        )

    def context_snippets(self, query: str, limit: int = 4) -> list[str]:
        bundle = self.context_bundle(query, limit=limit)
        return bundle["snippets"]

    def context_bundle(self, query: str, limit: int = 4) -> dict[str, object]:
        if not self.enabled or self.store is None:
            return {"snippets": [], "records": [], "refs": [], "fingerprint": None}
        self._retrieval_queries += 1
        records = self.store.search(keyword=query, limit=max(limit * 2, limit))
        if records:
            self._retrieval_hits += 1
        ranked = rank_records(
            records,
            salience_weight=self.rank_salience_weight,
            recency_weight=self.rank_recency_weight,
        )
        selected = ranked[:limit]
        snippets = [record.content for record in selected]
        if snippets:
            self._retrieval_useful += 1
        return _bundle_from_records(selected, snippets)

    def context_snippets_scoped(
        self,
        query: str,
        *,
        scope: str,
        team_id: str,
        case_id: str,
        job_id: str | None = None,
        visibility: str | None = None,
        limit: int = 4,
    ) -> list[str]:
        bundle = self.context_bundle_scoped(
            query,
            scope=scope,
            team_id=team_id,
            case_id=case_id,
            job_id=job_id,
            visibility=visibility,
            limit=limit,
        )
        return bundle["snippets"]

    def context_bundle_scoped(
        self,
        query: str,
        *,
        scope: str,
        team_id: str,
        case_id: str,
        job_id: str | None = None,
        visibility: str | None = None,
        limit: int = 4,
    ) -> dict[str, object]:
        if not self.enabled or self.store is None:
            return {"snippets": [], "records": [], "refs": [], "fingerprint": None}
        self._retrieval_queries += 1
        records = self.store.search(
            keyword=query,
            limit=max(limit * 2, limit),
            scope=scope,
            team_id=team_id,
            case_id=case_id,
            job_id=job_id,
            visibility=visibility,
        )
        if records:
            self._retrieval_hits += 1
        ranked = rank_records(
            records,
            salience_weight=self.rank_salience_weight,
            recency_weight=self.rank_recency_weight,
        )
        selected = ranked[:limit]
        snippets = [record.content for record in selected]
        if snippets:
            self._retrieval_useful += 1
        return _bundle_from_records(selected, snippets)

    def target_version(
        self,
        *,
        scope: str,
        team_id: str,
        case_id: str,
        visibility: str,
        memory_target: str,
    ) -> int:
        if not self.enabled or self.store is None:
            return 0
        return self.store.get_target_version(
            scope=scope,
            team_id=team_id,
            case_id=case_id,
            visibility=visibility,
            memory_target=memory_target,
        )

    def stats(self) -> dict[str, int | bool | float]:
        total_records = self.store.count() if self.store is not None else 0
        write_rate = (
            round(self._writes_accepted / max(self._write_attempts, 1), 4)
            if self._write_attempts
            else 0.0
        )
        dedup_hit_rate = (
            round(self._dedup_hits / max(self._writes_accepted, 1), 4)
            if self._writes_accepted
            else 0.0
        )
        retrieval_hit_rate = (
            round(self._retrieval_hits / max(self._retrieval_queries, 1), 4)
            if self._retrieval_queries
            else 0.0
        )
        retrieval_usefulness_rate = (
            round(self._retrieval_useful / max(self._retrieval_queries, 1), 4)
            if self._retrieval_queries
            else 0.0
        )
        stale_ratio = (
            round(1.0 - retrieval_usefulness_rate, 4) if self._retrieval_queries else 0.0
        )
        return {
            "enabled": self.enabled,
            "total_records": total_records,
            "write_rate": write_rate,
            "memory_write_rate": write_rate,
            "dedup_hit_rate": dedup_hit_rate,
            "retrieval_hit_rate": retrieval_hit_rate,
            "retrieval_usefulness_rate": retrieval_usefulness_rate,
            "stale_ratio": stale_ratio,
            "stale_retrieval_ratio": stale_ratio,
        }


def _bundle_from_records(records: list[MemoryRecord], snippets: list[str]) -> dict[str, object]:
    refs = [record.id for record in records]
    fingerprint = _records_fingerprint(records)
    return {
        "snippets": snippets,
        "records": [
            {
                "id": record.id,
                "content_hash": record.content_hash,
                "created_at": record.created_at,
                "scope": record.scope,
                "visibility": record.visibility,
            }
            for record in records
        ],
        "refs": refs,
        "fingerprint": fingerprint,
    }


def _records_fingerprint(records: list[MemoryRecord]) -> str | None:
    if not records:
        return None
    raw = json.dumps(
        [
            {
                "content_hash": record.content_hash,
                "memory_target": None,
                "state_version": None,
                "scope": record.scope,
                "visibility": record.visibility,
            }
            for record in records
        ],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
