from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from imperaos.artifacts.errors import ArtifactDomainError, ArtifactErrorCode
from imperaos.artifacts.models import OperationContext, canonical_json
from imperaos.governance.approval_store import ApprovalStore
from imperaos.governance.models import ApprovalTicket

_POLICY_HASH = hashlib.sha256(b"artifact-mutation-proposal/v1").hexdigest()


class ArtifactProposalApprovalGateway:
    def __init__(self, approval_store: ApprovalStore, *, ttl_seconds: int = 900) -> None:
        self._approval_store = approval_store
        self._ttl_seconds = ttl_seconds

    def request_approval(self, row: Any, context: OperationContext) -> ApprovalTicket:
        self._validate_provenance(row)
        target_ref = self._target_ref(row)
        action_hash = self.action_hash(row)
        idempotency_key = f"artifact-proposal:{row['workspace_id']}:{row['proposal_id']}"
        existing = self._approval_store.get_by_idempotency_key(
            idempotency_key, workspace_id=row["workspace_id"]
        )
        if existing is not None:
            if (
                existing.target_kind != "artifact_mutation_proposal"
                or existing.target_ref != target_ref
                or existing.action_hash != action_hash
                or existing.snapshot.get("executorPrincipalId") != row["proposed_by_id"]
            ):
                raise ArtifactDomainError(
                    ArtifactErrorCode.ARTIFACT_POLICY_UNAVAILABLE,
                    "stored proposal approval binding is inconsistent",
                )
            return existing
        snapshot = {
            "workspaceId": row["workspace_id"],
            "artifactId": row["artifact_id"],
            "proposalId": row["proposal_id"],
            "baseRevisionNumber": row["base_revision_number"],
            "mutationType": row["mutation_type"],
            "contentSha256": row["content_sha256"],
            "requestSha256": row["request_sha256"],
            "contextSha256": row["context_sha256"],
            "selectionSha256": row["selection_sha256"],
            "contextRevisionId": row["context_revision_id"],
            "contextPurpose": row["context_purpose"],
            "targetScope": json.loads(row["target_scope_json"]),
            "sourceSessionId": row["source_session_id"],
            "sourceTurnId": row["source_turn_id"],
            "traceId": row["trace_id"],
            "executorPrincipalId": row["proposed_by_id"],
            "targetKind": "artifact_mutation_proposal",
            "targetRef": target_ref,
            "actionHash": action_hash,
        }
        return self._approval_store.create_ticket(
            workspace_id=row["workspace_id"],
            run_id=context.request_id,
            target_kind="artifact_mutation_proposal",
            target_ref=target_ref,
            action_hash=action_hash,
            policy_hash=_POLICY_HASH,
            request_hash=_sha256(
                {
                    "proposalId": row["proposal_id"],
                    "idempotencyKey": row["idempotency_key"],
                }
            ),
            snapshot_hash=_sha256(snapshot),
            snapshot=snapshot,
            ttl_seconds=self._ttl_seconds,
            idempotency_key=idempotency_key,
        )

    def claim(self, row: Any, context: OperationContext, approval_id: str) -> ApprovalTicket:
        claim_id = self._claim_id(row)
        result = self._approval_store.claim_approved_action(
            approval_id=approval_id,
            workspace_id=row["workspace_id"],
            claim_id=claim_id,
            target_kind="artifact_mutation_proposal",
            target_ref=self._target_ref(row),
            action_hash=self.action_hash(row),
            executor_principal_id=context.principal_id,
        )
        if result.error_code is not None or result.ticket is None:
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_PERMISSION_DENIED,
                "artifact proposal approval is not valid for this action",
                details={"reasonCode": result.error_code or "APPROVAL_NOT_FOUND"},
            )
        return result.ticket

    def complete(self, row: Any, approval_id: str) -> None:
        result = self._approval_store.complete_claimed_action(
            approval_id=approval_id,
            workspace_id=row["workspace_id"],
            claim_id=self._claim_id(row),
        )
        if result.error_code is not None:
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_POLICY_UNAVAILABLE,
                "artifact proposal approval could not be consumed",
                details={"reasonCode": result.error_code},
            )

    @staticmethod
    def action_hash(row: Any) -> str:
        return _sha256(
            {
                "workspaceId": row["workspace_id"],
                "artifactId": row["artifact_id"],
                "proposalId": row["proposal_id"],
                "baseRevisionNumber": row["base_revision_number"],
                "mutationType": row["mutation_type"],
                "contentSha256": row["content_sha256"],
                "requestSha256": row["request_sha256"],
                "contextSha256": row["context_sha256"],
                "selectionSha256": row["selection_sha256"],
                "contextRevisionId": row["context_revision_id"],
                "contextPurpose": row["context_purpose"],
                "targetScope": json.loads(row["target_scope_json"]),
                "sourceSessionId": row["source_session_id"],
                "sourceTurnId": row["source_turn_id"],
                "traceId": row["trace_id"],
            }
        )

    @staticmethod
    def _validate_provenance(row: Any) -> None:
        for field in (
            "content_sha256",
            "request_sha256",
            "context_sha256",
            "selection_sha256",
        ):
            value = row[field]
            if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
                raise ArtifactDomainError(
                    ArtifactErrorCode.ARTIFACT_POLICY_UNAVAILABLE,
                    "artifact proposal provenance is incomplete",
                    details={"reasonCode": "ARTIFACT_PROPOSAL_PROVENANCE_INVALID"},
                )
        if (
            not row["context_revision_id"]
            or row["context_purpose"] not in {"edit", "transform"}
            or not row["target_scope_json"]
        ):
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_POLICY_UNAVAILABLE,
                "artifact proposal scope provenance is incomplete",
                details={"reasonCode": "ARTIFACT_PROPOSAL_PROVENANCE_INVALID"},
            )

    @staticmethod
    def _target_ref(row: Any) -> str:
        return f"{row['workspace_id']}:{row['artifact_id']}:{row['proposal_id']}"

    @staticmethod
    def _claim_id(row: Any) -> str:
        return f"artifact-proposal:{row['workspace_id']}:{row['proposal_id']}"


def _sha256(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
