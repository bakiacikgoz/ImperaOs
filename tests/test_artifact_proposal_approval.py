from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import typer

from imperaos.artifacts.errors import ArtifactDomainError, ArtifactErrorCode
from imperaos.artifacts.models import OperationContext, PrincipalType
from imperaos.artifacts.proposal_approval import ArtifactProposalApprovalGateway
from imperaos.cli import (
    _require_approval_workspace,
    approval_decide,
    approval_pending,
    approval_show,
)
from imperaos.governance.approval_store import ApprovalStore


def test_artifact_approval_decision_is_bound_to_the_trusted_workspace() -> None:
    ticket = SimpleNamespace(
        target_kind="artifact_mutation_proposal",
        target_ref="workspace-1:artifact-1",
        snapshot={"workspace_id": "workspace-1"},
    )

    _require_approval_workspace(ticket, "workspace-1", "approval-1")
    with pytest.raises(typer.Exit):
        _require_approval_workspace(ticket, "workspace-2", "approval-1")
    with pytest.raises(typer.Exit):
        _require_approval_workspace(ticket, None, "approval-1")


def _ticket(approval_id: str, workspace_id: str) -> SimpleNamespace:
    payload = {
        "approval_id": approval_id,
        "workspace_id": workspace_id,
        "target_kind": "artifact_mutation_proposal",
        "target_ref": f"{workspace_id}:artifact-1:proposal-1",
        "snapshot": {"workspaceId": workspace_id},
    }
    return SimpleNamespace(
        **payload,
        status=SimpleNamespace(value="pending"),
        execution_status=SimpleNamespace(value="not_executed"),
        model_dump=lambda mode="json": dict(payload),
    )


def test_artifact_approval_uses_verified_actor_and_requires_workspace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ticket = _ticket("approval-1", "workspace-1")
    captured: dict[str, object] = {}
    runtime = SimpleNamespace(
        approval_store=SimpleNamespace(
            get=lambda _approval_id, *, workspace_id: (
                ticket if workspace_id == "workspace-1" else None
            )
        ),
        decide_approval=lambda **kwargs: (
            captured.update(kwargs)
            or SimpleNamespace(error_code=None, ticket=None)
        ),
    )
    monkeypatch.setattr("imperaos.cli.RuntimeConfig.from_profile", lambda _profile: object())
    monkeypatch.setattr(
        "imperaos.cli._require_permission_or_exit",
        lambda _config, _permission: SimpleNamespace(actor_id="trusted-actor"),
    )
    monkeypatch.setattr("imperaos.cli._build_governance_runtime", lambda _config: runtime)

    approval_decide(
        approval_id="approval-1",
        approve=True,
        reject=False,
        actor="spoofed-actor",
        workspace_id="workspace-1",
        reason=None,
        profile="enterprise",
    )

    assert captured["actor"] == "trusted-actor"


def test_pending_and_show_hide_foreign_artifact_approvals(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    local = _ticket("approval-local", "workspace-1")
    foreign = _ticket("approval-foreign", "workspace-2")
    store = SimpleNamespace(
        list_pending=lambda *, workspace_id: [
            item for item in (local, foreign) if item.workspace_id == workspace_id
        ],
        expire_pending=lambda: None,
        get=lambda approval_id, *, workspace_id: (
            local
            if approval_id == "approval-local" and workspace_id == "workspace-1"
            else None
        ),
    )
    runtime = SimpleNamespace(approval_store=store)
    monkeypatch.setattr("imperaos.cli.RuntimeConfig.from_profile", lambda _profile: object())
    monkeypatch.setattr(
        "imperaos.cli._require_permission_or_exit",
        lambda _config, _permission: SimpleNamespace(actor_id="trusted-actor"),
    )
    monkeypatch.setattr("imperaos.cli._build_governance_runtime", lambda _config: runtime)

    approval_pending(profile="enterprise", json_output=True, workspace_id="workspace-1")
    payload = json.loads(capsys.readouterr().out)
    assert [item["approval_id"] for item in payload["pending"]] == ["approval-local"]

    with pytest.raises(typer.Exit):
        approval_show(
            approval_id="approval-foreign",
            profile="enterprise",
            json_output=True,
            show_raw_snapshot=False,
            workspace_id="workspace-1",
        )


def test_proposal_approval_rejects_missing_provenance_before_creating_ticket(
    tmp_path: Path,
) -> None:
    store = ApprovalStore(tmp_path / "approvals.sqlite3")
    gateway = ArtifactProposalApprovalGateway(store)
    row = {
        "workspace_id": "workspace-1",
        "artifact_id": "artifact-1",
        "proposal_id": "legacy-proposal",
        "base_revision_number": 1,
        "mutation_type": "replace_content",
        "content_sha256": "a" * 64,
        "request_sha256": None,
        "context_sha256": None,
        "selection_sha256": None,
        "source_session_id": None,
        "source_turn_id": None,
        "trace_id": None,
        "proposed_by_id": "assistant-1",
        "idempotency_key": "legacy-key",
    }
    context = OperationContext(
        workspace_id="workspace-1",
        principal_type=PrincipalType.ASSISTANT,
        principal_id="assistant-1",
        roles=("artifact_editor",),
        request_id="request-1",
    )

    with pytest.raises(ArtifactDomainError) as caught:
        gateway.request_approval(row, context)

    assert caught.value.code is ArtifactErrorCode.ARTIFACT_POLICY_UNAVAILABLE
    assert store.list_pending() == []
