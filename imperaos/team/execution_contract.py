from __future__ import annotations

import hashlib
import json
from typing import Any


def canonicalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(payload, sort_keys=True, ensure_ascii=False))


def payload_hash(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_resume_token_ref(
    *,
    source_job_id: str,
    task_run_id: str,
    approval_id: str,
    snapshot_hash: str,
    target_kind: str,
) -> str:
    return payload_hash(
        {
            "source_job_id": source_job_id,
            "task_run_id": task_run_id,
            "approval_id": approval_id,
            "snapshot_hash": snapshot_hash,
            "target_kind": target_kind,
        }
    )


def build_execution_contract_hash(
    *,
    resume_token_ref: str,
    action_hash: str,
    policy_hash: str,
    contract: dict[str, Any],
) -> str:
    return payload_hash(
        {
            "resume_token_ref": resume_token_ref,
            "action_hash": action_hash,
            "policy_hash": policy_hash,
            "contract": canonicalize_payload(contract),
        }
    )


def derive_execution_contract_refs(
    *,
    source_job_id: str,
    approval_id: str,
    snapshot_hash: str,
    target_kind: str,
    policy_hash: str,
    contract: dict[str, Any],
    fallback_action_hash: str | None = None,
) -> tuple[str | None, str | None]:
    contract_task_run_id = str(contract.get("task_run_id") or "").strip()
    effective_target_kind = str(contract.get("target_kind") or target_kind or "").strip()
    effective_action_hash = str(
        contract.get("action_payload_hash") or fallback_action_hash or ""
    ).strip()
    if not (
        source_job_id
        and approval_id
        and snapshot_hash
        and contract_task_run_id
        and effective_target_kind
        and effective_action_hash
    ):
        return None, None
    resume_token_ref = build_resume_token_ref(
        source_job_id=source_job_id,
        task_run_id=contract_task_run_id,
        approval_id=approval_id,
        snapshot_hash=snapshot_hash,
        target_kind=effective_target_kind,
    )
    execution_contract_hash = build_execution_contract_hash(
        resume_token_ref=resume_token_ref,
        action_hash=effective_action_hash,
        policy_hash=policy_hash,
        contract=contract,
    )
    return resume_token_ref, execution_contract_hash


def build_memory_fingerprint(refs: list[dict[str, Any]]) -> str:
    normalized = _normalize_memory_refs(refs)
    return payload_hash(normalized)


def _normalize_memory_refs(refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = [
        {
            "content_hash": item.get("content_hash"),
            "memory_target": item.get("memory_target"),
            "state_version": item.get("state_version"),
            "scope": item.get("scope"),
            "visibility": item.get("visibility"),
        }
        for item in refs
    ]
    return normalized


def build_task_execution_contract(
    *,
    task_run_id: str,
    task_attempt: int,
    task_type: str,
    target_ref: str,
    canonical_task_input: str,
    action_payload_hash: str,
    policy_input_hash: str,
    resolved_memory_refs: list[dict[str, Any]],
    causal_ancestry: list[str],
    branch_id: str,
    branch_parent: str | None,
    root_run_id: str | None = None,
    logical_task_id: str | None = None,
    lineage_hash: str | None = None,
    continuation_index: int | None = None,
    checkpoint_generation: int | None = None,
) -> dict[str, Any]:
    refs = _normalize_memory_refs(
        canonicalize_payload({"refs": resolved_memory_refs}).get("refs", [])
    )
    return {
        "task_run_id": task_run_id,
        "task_attempt": task_attempt,
        "target_kind": "task",
        "target_ref": target_ref,
        "canonical_task_input": canonical_task_input,
        "resolved_memory_refs": refs,
        "resolved_memory_fingerprint": build_memory_fingerprint(refs),
        "action_payload_hash": action_payload_hash,
        "policy_input_hash": policy_input_hash,
        "causal_ancestry": sorted(causal_ancestry),
        "branch_id": branch_id,
        "branch_parent": branch_parent,
        "root_run_id": root_run_id,
        "logical_task_id": logical_task_id,
        "lineage_hash": lineage_hash,
        "continuation_index": continuation_index,
        "checkpoint_generation": checkpoint_generation,
    }


def build_handoff_execution_contract(
    *,
    task_run_id: str,
    task_attempt: int,
    target_ref: str,
    payload_hash_value: str,
    action_payload_hash: str,
    policy_input_hash: str,
    causal_ancestry: list[str],
    branch_id: str,
    branch_parent: str | None,
    root_run_id: str | None = None,
    logical_task_id: str | None = None,
    lineage_hash: str | None = None,
    continuation_index: int | None = None,
    checkpoint_generation: int | None = None,
) -> dict[str, Any]:
    return {
        "task_run_id": task_run_id,
        "task_attempt": task_attempt,
        "target_kind": "handoff",
        "target_ref": target_ref,
        "canonical_task_input": None,
        "resolved_memory_refs": [],
        "resolved_memory_fingerprint": build_memory_fingerprint([]),
        "action_payload_hash": action_payload_hash,
        "payload_hash": payload_hash_value,
        "policy_input_hash": policy_input_hash,
        "causal_ancestry": sorted(causal_ancestry),
        "branch_id": branch_id,
        "branch_parent": branch_parent,
        "root_run_id": root_run_id,
        "logical_task_id": logical_task_id,
        "lineage_hash": lineage_hash,
        "continuation_index": continuation_index,
        "checkpoint_generation": checkpoint_generation,
    }


def build_memory_write_execution_contract(
    *,
    task_run_id: str,
    task_attempt: int,
    target_ref: str,
    canonical_task_input: str,
    action_payload_hash: str,
    policy_input_hash: str,
    resolved_memory_refs: list[dict[str, Any]],
    causal_ancestry: list[str],
    branch_id: str,
    branch_parent: str | None,
    memory_target: str | None,
    expected_state_version: int | None,
    root_run_id: str | None = None,
    logical_task_id: str | None = None,
    lineage_hash: str | None = None,
    continuation_index: int | None = None,
    checkpoint_generation: int | None = None,
) -> dict[str, Any]:
    refs = _normalize_memory_refs(
        canonicalize_payload({"refs": resolved_memory_refs}).get("refs", [])
    )
    return {
        "task_run_id": task_run_id,
        "task_attempt": task_attempt,
        "target_kind": "memory_write",
        "target_ref": target_ref,
        "canonical_task_input": canonical_task_input,
        "resolved_memory_refs": refs,
        "resolved_memory_fingerprint": build_memory_fingerprint(refs),
        "action_payload_hash": action_payload_hash,
        "policy_input_hash": policy_input_hash,
        "causal_ancestry": sorted(causal_ancestry),
        "branch_id": branch_id,
        "branch_parent": branch_parent,
        "memory_target": memory_target,
        "expected_state_version": expected_state_version,
        "root_run_id": root_run_id,
        "logical_task_id": logical_task_id,
        "lineage_hash": lineage_hash,
        "continuation_index": continuation_index,
        "checkpoint_generation": checkpoint_generation,
    }
