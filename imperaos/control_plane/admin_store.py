from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from imperaos.control_plane.storage import (
    ControlPlaneStore,
    canonical_json_hash,
)
from imperaos.enterprise.signing import write_signed_json
from imperaos.governance.approval_store import ApprovalStore
from imperaos.governance.models import ApprovalStatus
from imperaos.runtime.config import RuntimeConfig

AdminChangeKind = Literal["user", "role", "policy_pack"]
AdminOperation = Literal["create", "update", "deactivate", "stage", "promote", "rollback"]


class IdentityAssertion(BaseModel):
    model_config = ConfigDict(extra="ignore")

    actor_id: str = "enterprise-admin"
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)


class AdminChangeProposal(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    version: str = "control-plane.admin-change-proposal/v1"
    proposal_id: str = Field(alias="proposalId")
    kind: AdminChangeKind
    operation: AdminOperation
    actor: str
    permission_required: str = Field(alias="permissionRequired")
    before_hash: str | None = Field(default=None, alias="beforeHash")
    after_hash: str = Field(alias="afterHash")
    policy_decision: Literal["allow", "deny", "require_approval"] = Field(
        alias="policyDecision"
    )
    approval_id: str | None = Field(default=None, alias="approvalId")
    status: Literal[
        "proposed",
        "dry_run_passed",
        "approval_required",
        "approved",
        "applied",
        "signed_audited",
        "denied",
        "expired",
        "failed",
    ] = "proposed"
    audit_envelope_path: str | None = Field(default=None, alias="auditEnvelopePath")
    diff_summary: dict[str, Any] = Field(default_factory=dict, alias="diffSummary")
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")
    generated_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        alias="generatedAtUtc",
    )


class AdminChangeApplyResult(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    version: str = "control-plane.admin-change-apply/v1"
    status: Literal["applied", "blocked"]
    proposal_id: str = Field(alias="proposalId")
    audit_envelope_path: str | None = Field(default=None, alias="auditEnvelopePath")
    signature_status: Literal["valid", "missing"] = Field(alias="signatureStatus")
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")


def propose_admin_change(
    *,
    store_root: Path,
    actor: IdentityAssertion,
    kind: AdminChangeKind,
    operation: AdminOperation,
    payload: dict[str, Any],
    dry_run: bool,
    config: RuntimeConfig | None = None,
) -> AdminChangeProposal:
    store = ControlPlaneStore(store_root)
    permission = _permission_for(kind, operation)
    allowed = permission in set(actor.permissions) or "platform_admin" in set(actor.roles)
    before = store.read_json(f"admin/state/{kind}.json", default={})
    before_hash = canonical_json_hash(before) if before else None
    after = _apply_payload_preview(before if isinstance(before, dict) else {}, payload)
    after_hash = canonical_json_hash(after)
    proposal_id = f"admin-{kind}-{operation}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S%f')}"
    blocking = [] if allowed else ["RBAC_PERMISSION_DENIED"]
    policy_decision: Literal["allow", "deny", "require_approval"] = (
        "deny" if blocking else "require_approval"
    )
    approval_id = None
    status = "denied" if blocking else "approval_required"
    if not blocking:
        approval_id = ApprovalStore(store_root / "approvals.sqlite3").create_ticket(
            workspace_id="default",
            run_id=proposal_id,
            target_kind=f"admin:{kind}",
            target_ref=operation,
            action_hash=after_hash,
            policy_hash="sha256:admin-governance-v1",
            request_hash=canonical_json_hash(payload),
            snapshot_hash=canonical_json_hash({"before": before, "after": after}),
            snapshot={
                "kind": kind,
                "operation": operation,
                "actor": actor.model_dump(mode="json"),
                "before": before,
                "after": after,
            },
            ttl_seconds=86400,
            idempotency_key=proposal_id,
        ).approval_id
    if dry_run and not blocking:
        status = "approval_required"
    proposal = AdminChangeProposal(
        proposalId=proposal_id,
        kind=kind,
        operation=operation,
        actor=actor.actor_id,
        permissionRequired=permission,
        beforeHash=before_hash,
        afterHash=after_hash,
        policyDecision=policy_decision,
        approvalId=approval_id,
        status=status,
        diffSummary={"changed": before_hash != after_hash, "keys": sorted(payload)},
        blockingReasons=blocking,
    )
    store.write_json_atomic(
        f"admin/proposals/{proposal_id}.json",
        proposal.model_dump(mode="json", by_alias=True),
    )
    return proposal


def apply_admin_change(
    *,
    store_root: Path,
    proposal_id: str,
    approval_id: str,
    actor: IdentityAssertion,
    config: RuntimeConfig | None = None,
) -> AdminChangeApplyResult:
    store = ControlPlaneStore(store_root)
    proposal_payload = store.read_json(f"admin/proposals/{proposal_id}.json", default=None)
    if not isinstance(proposal_payload, dict):
        return _blocked(proposal_id, "missing", ["PROPOSAL_NOT_FOUND"])
    proposal = AdminChangeProposal.model_validate(proposal_payload)
    if approval_id != proposal.approval_id:
        return _blocked(proposal_id, "missing", ["APPROVAL_ID_MISMATCH"])
    ticket = ApprovalStore(store_root / "approvals.sqlite3").get(
        approval_id, workspace_id="default"
    )
    if ticket is None or ticket.status != ApprovalStatus.APPROVED:
        return _blocked(proposal_id, "missing", ["APPROVAL_NOT_APPROVED"])

    snapshot = ticket.snapshot
    after = snapshot.get("after") if isinstance(snapshot, dict) else None
    if not isinstance(after, dict):
        return _blocked(proposal_id, "missing", ["PROPOSAL_SNAPSHOT_INVALID"])
    current = store.read_json(f"admin/state/{proposal.kind}.json", default={})
    if proposal.before_hash and canonical_json_hash(current) != proposal.before_hash:
        return _blocked(proposal_id, "missing", ["ADMIN_STATE_STALE"])
    store.write_json_atomic(f"admin/state/{proposal.kind}.json", after)
    audit_path = f"admin/audit/{proposal_id}.json"
    write_signed_json(
        path=store.path(audit_path),
        artifact="admin_change_audit",
        data={
            "proposal": proposal.model_dump(mode="json", by_alias=True),
            "applied_by": actor.actor_id,
            "applied_at": datetime.now(UTC).isoformat(),
            "state_hash": canonical_json_hash(after),
        },
        config=config,
        purpose="admin-change-audit",
    )
    ApprovalStore(store_root / "approvals.sqlite3").mark_executed(
        approval_id=approval_id,
        workspace_id="default",
        executed_by=actor.actor_id,
    )
    proposal = proposal.model_copy(
        update={"status": "signed_audited", "audit_envelope_path": audit_path}
    )
    store.write_json_atomic(
        f"admin/proposals/{proposal_id}.json",
        proposal.model_dump(mode="json", by_alias=True),
    )
    return AdminChangeApplyResult(
        status="applied",
        proposalId=proposal_id,
        auditEnvelopePath=audit_path,
        signatureStatus="valid" if config is not None else "missing",
    )


def build_governance_admin_report(
    *,
    store_root: Path,
    output_path: Path,
) -> dict[str, Any]:
    store = ControlPlaneStore(store_root)
    proposals_root = store.path("admin/proposals")
    proposals = []
    if proposals_root.exists():
        for path in sorted(proposals_root.glob("*.json")):
            proposals.append(json.loads(path.read_text(encoding="utf-8")))
    report = {
        "version": "control-plane.governance-admin-report/v1",
        "generatedAtUtc": datetime.now(UTC).isoformat(),
        "status": "pass",
        "proposalCount": len(proposals),
        "appliedCount": sum(1 for item in proposals if item.get("status") == "signed_audited"),
        "pendingApprovalCount": sum(
            1 for item in proposals if item.get("status") == "approval_required"
        ),
        "proposals": proposals,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def _blocked(
    proposal_id: str,
    signature_status: Literal["valid", "missing"],
    reasons: list[str],
) -> AdminChangeApplyResult:
    return AdminChangeApplyResult(
        status="blocked",
        proposalId=proposal_id,
        auditEnvelopePath=None,
        signatureStatus=signature_status,
        blockingReasons=reasons,
    )


def _permission_for(kind: AdminChangeKind, operation: AdminOperation) -> str:
    if kind == "policy_pack" or operation in {"stage", "promote", "rollback"}:
        return "policy.promote"
    return "config.write"


def _apply_payload_preview(before: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    updated = dict(before)
    record_id = str(
        payload.get("id") or payload.get("user_id") or payload.get("role_id") or "default"
    )
    previous = updated.get(record_id) if isinstance(updated.get(record_id), dict) else {}
    updated[record_id] = {**previous, **payload}
    return updated
