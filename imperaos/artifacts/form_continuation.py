from __future__ import annotations

import hashlib

from imperaos.artifacts.models import OperationContext, canonical_json
from imperaos.governance.approval_store import ApprovalStore
from imperaos.governance.models import ApprovalTicket

_POLICY_HASH = hashlib.sha256(b"artifact-form-continuation/v1").hexdigest()


class ArtifactFormContinuationGateway:
    """Creates hash-only tickets in the existing approval lifecycle."""

    def __init__(self, approval_store: ApprovalStore, *, ttl_seconds: int = 86_400) -> None:
        self._approval_store = approval_store
        self._ttl_seconds = ttl_seconds

    def request_approval(
        self,
        *,
        context: OperationContext,
        artifact_id: str,
        schema_revision_id: str,
        submission_id: str,
        response_sha256: str,
        idempotency_key: str,
    ) -> ApprovalTicket:
        target_ref = f"{context.workspace_id}:{artifact_id}:{schema_revision_id}"
        action_payload = {
            "kind": "artifact_form_continuation",
            "workspace_id": context.workspace_id,
            "artifact_id": artifact_id,
            "schema_revision_id": schema_revision_id,
            "submission_id": submission_id,
            "response_sha256": response_sha256,
            "policy_hash": _POLICY_HASH,
        }
        action_hash = _sha256(action_payload)
        snapshot = {
            **action_payload,
            "target_kind": "artifact_form_continuation",
            "target_ref": target_ref,
            "action_hash": action_hash,
        }
        return self._approval_store.create_ticket(
            workspace_id=context.workspace_id,
            run_id=context.request_id,
            target_kind="artifact_form_continuation",
            target_ref=target_ref,
            action_hash=action_hash,
            policy_hash=_POLICY_HASH,
            request_hash=_sha256(
                {
                    "submission_id": submission_id,
                    "response_sha256": response_sha256,
                    "idempotency_key": idempotency_key,
                }
            ),
            snapshot_hash=_sha256(snapshot),
            snapshot=snapshot,
            ttl_seconds=self._ttl_seconds,
            idempotency_key=(
                f"artifact-form:{context.workspace_id}:{artifact_id}:{idempotency_key}"
            ),
        )


def _sha256(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
