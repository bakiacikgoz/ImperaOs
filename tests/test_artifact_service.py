from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest
from pydantic import ValidationError

from imperaos.artifacts.commands import (
    ApplyArtifactProposalCommand,
    ArchiveArtifactCommand,
    ArtifactHistoryQuery,
    CreateArtifactCommand,
    DuplicateArtifactCommand,
    GetArtifactQuery,
    ListArtifactsQuery,
    MutateArtifactCommand,
    ProposeArtifactMutationCommand,
    RestoreArtifactCommand,
)
from imperaos.artifacts.context import ArtifactContextRequest, get_artifact_context
from imperaos.artifacts.errors import ArtifactDomainError, ArtifactErrorCode
from imperaos.artifacts.models import (
    ArtifactDataClass,
    ArtifactKind,
    ArtifactMutationType,
    ArtifactStatus,
    OperationContext,
    PrincipalType,
)
from imperaos.artifacts.service import ArtifactService
from imperaos.governance.approval_store import ApprovalStore
from imperaos.runtime.paths import state_path


def document(text: str) -> dict[str, object]:
    return {
        "kind": "document",
        "schemaVersion": 1,
        "language": "tr",
        "pageMode": "document",
        "blocks": [
            {
                "id": "block-1",
                "type": "paragraph",
                "content": [{"type": "text", "text": text}],
            }
        ],
    }


def user_context(*roles: str) -> OperationContext:
    return OperationContext(
        workspace_id="workspace-1",
        principal_type=PrincipalType.USER,
        principal_id="user-1",
        roles=roles or ("artifact_editor",),
        request_id="request-1",
    )


def assistant_context() -> OperationContext:
    return OperationContext(
        workspace_id="workspace-1",
        principal_type=PrincipalType.ASSISTANT,
        principal_id="assistant-1",
        roles=("artifact_editor",),
        request_id="request-ai-1",
    )


def create_command(*, key: str = "create-1") -> CreateArtifactCommand:
    return CreateArtifactCommand(
        artifact_id="artifact-1",
        kind=ArtifactKind.DOCUMENT,
        title="Operations plan",
        data_class=ArtifactDataClass.INTERNAL,
        content=document("v1"),
        idempotency_key=key,
    )


def proposal_command(
    service: ArtifactService,
    **values: object,
) -> ProposeArtifactMutationCommand:
    values.pop("context_sha256", None)
    values.pop("selection_sha256", None)
    revision = next(
        item
        for item in service.store.list_revisions("workspace-1", str(values["artifact_id"]))
        if item.revision_number == values["base_revision_number"]
    )
    request = ArtifactContextRequest.model_validate(
        {
            "artifactId": values["artifact_id"],
            "revisionId": revision.revision_id,
            "purpose": "edit",
            "selection": {"kind": "document", "blockIds": ["block-1"]},
        }
    )
    pack = get_artifact_context(service, request, assistant_context())
    return ProposeArtifactMutationCommand(
        **values,
        context_sha256=pack.projection_sha256,
        selection_sha256=pack.selection_sha256,
        context_revision_id=pack.revision_id,
        context_purpose="edit",
        target_selection=pack.selection.model_dump(mode="json", by_alias=True),
    )


def test_document_service_create_get_list_and_create_idempotency(tmp_path: Path) -> None:
    service = ArtifactService(tmp_path / "artifact-root")
    context = user_context()

    created = service.create(create_command(), context)
    replay = service.create(create_command(), context)
    loaded = service.get(GetArtifactQuery(artifact_id="artifact-1"), context)
    listed = service.list(ListArtifactsQuery(limit=20), context)

    assert created.created is True
    assert replay.created is False
    assert replay.disposition == "idempotent_replay"
    assert loaded.artifact == created.artifact
    assert loaded.content.model_dump(mode="json", by_alias=True) == document("v1")
    assert listed.items == (created.artifact,)


def test_document_service_mutate_history_conflict_and_restore(tmp_path: Path) -> None:
    service = ArtifactService(tmp_path / "artifact-root")
    context = user_context()
    created = service.create(create_command(), context)
    mutated = service.mutate(
        MutateArtifactCommand(
            artifact_id="artifact-1",
            expected_revision_number=1,
            mutation_type=ArtifactMutationType.REPLACE_CONTENT,
            content=document("v2"),
            idempotency_key="mutate-2",
        ),
        context,
    )

    with pytest.raises(ArtifactDomainError) as stale:
        service.mutate(
            MutateArtifactCommand(
                artifact_id="artifact-1",
                expected_revision_number=1,
                mutation_type=ArtifactMutationType.REPLACE_CONTENT,
                content=document("stale-secret-marker"),
                idempotency_key="mutate-stale",
            ),
            context,
        )

    restored = service.restore(
        RestoreArtifactCommand(
            artifact_id="artifact-1",
            source_revision_id=created.revision.revision_id,
            expected_revision_number=2,
            idempotency_key="restore-3",
        ),
        context,
    )
    history = service.history(ArtifactHistoryQuery(artifact_id="artifact-1"), context)
    first_page = service.history(ArtifactHistoryQuery(artifact_id="artifact-1", limit=2), context)
    second_page = service.history(
        ArtifactHistoryQuery(artifact_id="artifact-1", cursor=first_page.next_cursor, limit=2),
        context,
    )

    assert mutated.artifact.current_revision_number == 2
    assert stale.value.code is ArtifactErrorCode.ARTIFACT_REVISION_CONFLICT
    assert "stale-secret-marker" not in str(stale.value)
    assert restored.artifact.current_revision_number == 3
    assert [item.revision_number for item in history.items] == [3, 2, 1]
    assert [item.revision_number for item in first_page.items] == [3, 2]
    assert [item.revision_number for item in second_page.items] == [1]


def test_mutation_replays_after_response_loss_and_rejects_changed_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "artifact-root"
    service = ArtifactService(root)
    context = user_context()
    service.create(create_command(), context)
    command = MutateArtifactCommand(
        artifact_id="artifact-1",
        expected_revision_number=1,
        mutation_type=ArtifactMutationType.REPLACE_CONTENT,
        content=document("v2-after-response-loss"),
        change_summary="Original mutation",
        idempotency_key="mutate-response-loss",
    )

    append_revision = service.store.append_revision

    def lose_response(*args: object, **kwargs: object) -> object:
        append_revision(*args, **kwargs)
        raise RuntimeError("simulated response loss")

    monkeypatch.setattr(service.store, "append_revision", lose_response)
    with pytest.raises(RuntimeError, match="simulated response loss"):
        service.mutate(command, context)

    restarted = ArtifactService(root)
    with pytest.raises(ArtifactDomainError) as mismatch:
        restarted.mutate(
            command.model_copy(update={"change_summary": "Changed request"}),
            context,
        )
    assert mismatch.value.code is ArtifactErrorCode.IDEMPOTENCY_KEY_REUSE_MISMATCH
    replay = restarted.mutate(command, context)
    assert replay.disposition == "idempotent_replay"
    assert [
        revision.revision_number
        for revision in restarted.history(
            ArtifactHistoryQuery(artifact_id="artifact-1"),
            context,
        ).items
    ] == [2, 1]


def test_restore_replay_rejects_changed_request_after_response_loss(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "artifact-root"
    service = ArtifactService(root)
    context = user_context()
    created = service.create(create_command(), context)
    service.mutate(
        MutateArtifactCommand(
            artifact_id="artifact-1",
            expected_revision_number=1,
            mutation_type=ArtifactMutationType.REPLACE_CONTENT,
            content=document("v2"),
            idempotency_key="mutate-before-restore",
        ),
        context,
    )
    command = RestoreArtifactCommand(
        artifact_id="artifact-1",
        source_revision_id=created.revision.revision_id,
        expected_revision_number=2,
        change_summary="Original restore",
        idempotency_key="restore-replay",
    )
    restore_revision = service.store.restore_revision

    def lose_response(*args: object, **kwargs: object) -> object:
        restore_revision(*args, **kwargs)
        raise RuntimeError("simulated response loss")

    monkeypatch.setattr(service.store, "restore_revision", lose_response)
    with pytest.raises(RuntimeError, match="simulated response loss"):
        service.restore(command, context)

    restarted = ArtifactService(root)
    with pytest.raises(ArtifactDomainError) as mismatch:
        restarted.restore(
            command.model_copy(update={"change_summary": "Changed restore"}),
            context,
        )
    assert mismatch.value.code is ArtifactErrorCode.IDEMPOTENCY_KEY_REUSE_MISMATCH
    replay = restarted.restore(command, context)
    assert replay.disposition == "idempotent_replay"


def test_document_service_ai_proposal_is_approval_bound_and_applies_new_revision(
    tmp_path: Path,
) -> None:
    approval_store = ApprovalStore(tmp_path / "approvals.sqlite3")
    service = ArtifactService(tmp_path / "artifact-root", approval_store=approval_store)
    service.create(create_command(), user_context())
    assistant = assistant_context()
    proposal = service.propose_mutation(
        proposal_command(service,
            proposal_id="proposal-1",
            artifact_id="artifact-1",
            base_revision_number=1,
            mutation_type=ArtifactMutationType.REPLACE_CONTENT,
            content=document("AI proposal"),
            idempotency_key="proposal-key-1",
            summary="Update opening paragraph",
            context_sha256="1" * 64,
            selection_sha256="2" * 64,
            source_session_id="session-1",
            source_turn_id="turn-1",
        ),
        assistant,
    )

    with pytest.raises(ValidationError):
        ApplyArtifactProposalCommand.model_validate(
            {
                "proposalId": "proposal-1",
                "expectedRevisionNumber": 1,
                "approvalGranted": True,
            }
        )
    approval_store.decide(
        approval_id=proposal.approval_id,
        workspace_id="workspace-1",
        approve=True,
        actor="user-1",
        reason="Reviewed exact proposal",
    )
    applied = service.apply_proposal(
        ApplyArtifactProposalCommand(
            proposal_id="proposal-1",
            expected_revision_number=1,
            approval_id=proposal.approval_id,
        ),
        assistant,
    )
    replay = service.apply_proposal(
        ApplyArtifactProposalCommand(
            proposal_id="proposal-1",
            expected_revision_number=1,
            approval_id=proposal.approval_id,
        ),
        assistant,
    )

    assert proposal.status == "pending"
    assert proposal.approval_id
    assert len(proposal.action_hash) == 64
    assert applied.artifact.current_revision_number == 2
    assert replay.disposition == "idempotent_replay"
    with service.store._connect() as connection:
        stored = connection.execute(
            "SELECT * FROM artifact_mutation_proposals WHERE proposal_id = 'proposal-1'"
        ).fetchone()
    assert stored["request_sha256"]
    assert len(stored["context_sha256"]) == 64
    assert len(stored["selection_sha256"]) == 64
    assert stored["context_revision_id"]
    assert stored["context_purpose"] == "edit"
    assert stored["target_scope_json"] == '{"blockIds":["block-1"],"kind":"document"}'
    assert stored["source_session_id"] == "session-1"
    assert stored["source_turn_id"] == "turn-1"
    assert stored["trace_id"] is None
    assert stored["approval_id"] == proposal.approval_id
    assert stored["action_hash"] == proposal.action_hash
    assert stored["approved_by_id"] == "user-1"
    assert stored["applied_by_id"] == "assistant-1"

    with pytest.raises(ArtifactDomainError) as replay_mismatch:
        service.propose_mutation(
            proposal_command(service,
                proposal_id="proposal-1",
                artifact_id="artifact-1",
                base_revision_number=1,
                mutation_type=ArtifactMutationType.REPLACE_CONTENT,
                content=document("AI proposal"),
                idempotency_key="proposal-key-1",
                summary="Changed summary",
                context_sha256="1" * 64,
                selection_sha256="2" * 64,
                source_session_id="session-1",
                source_turn_id="turn-1",
            ),
            assistant,
        )
    assert replay_mismatch.value.code is ArtifactErrorCode.IDEMPOTENCY_KEY_REUSE_MISMATCH


def test_default_artifact_proposal_uses_the_operator_governance_approval_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    service = ArtifactService(tmp_path / "artifact-root")
    service.create(create_command(), user_context())
    proposal = service.propose_mutation(
        proposal_command(service,
            proposal_id="proposal-default-store",
            artifact_id="artifact-1",
            base_revision_number=1,
            mutation_type=ArtifactMutationType.REPLACE_CONTENT,
            content=document("approved through operator store"),
            idempotency_key="proposal-default-key",
            context_sha256="1" * 64,
            selection_sha256="2" * 64,
        ),
        assistant_context(),
    )
    operator_store = ApprovalStore(Path(state_path("governance", "approvals.sqlite3")))
    decision = operator_store.decide(
        approval_id=proposal.approval_id,
        workspace_id="workspace-1",
        approve=True,
        actor="user-1",
        reason="operator reviewed exact proposal",
    )

    assert decision.error_code is None
    applied = service.apply_proposal(
        ApplyArtifactProposalCommand(
            proposal_id=proposal.proposal_id,
            expected_revision_number=1,
            approval_id=proposal.approval_id,
        ),
        assistant_context(),
    )
    assert applied.artifact.current_revision_number == 2


def test_artifact_proposal_rejects_changes_outside_trusted_selection(tmp_path: Path) -> None:
    service = ArtifactService(tmp_path / "artifact-root")
    base = document("selected")
    base["blocks"].append(
        {"id": "block-2", "type": "paragraph", "content": [{"type": "text", "text": "fixed"}]}
    )
    service.create(
        create_command().model_copy(update={"content": base}),
        user_context(),
    )
    proposed = document("selected update")
    proposed["blocks"].append(
        {"id": "block-2", "type": "paragraph", "content": [{"type": "text", "text": "escaped"}]}
    )

    with pytest.raises(ArtifactDomainError) as denied:
        service.propose_mutation(
            proposal_command(
                service,
                proposal_id="proposal-scope-escape",
                artifact_id="artifact-1",
                base_revision_number=1,
                mutation_type=ArtifactMutationType.REPLACE_CONTENT,
                content=proposed,
                idempotency_key="proposal-scope-escape-key",
            ),
            assistant_context(),
        )

    assert denied.value.code is ArtifactErrorCode.ARTIFACT_PERMISSION_DENIED
    with service.store._connect() as connection:
        count = connection.execute(
            "SELECT count(*) FROM artifact_mutation_proposals"
        ).fetchone()[0]
    assert count == 0


def test_artifact_proposal_revalidates_content_hash_and_scope_before_claim(
    tmp_path: Path,
) -> None:
    approval_store = ApprovalStore(tmp_path / "approvals.sqlite3")
    service = ArtifactService(tmp_path / "artifact-root", approval_store=approval_store)
    service.create(create_command(), user_context())
    proposal = service.propose_mutation(
        proposal_command(
            service,
            proposal_id="proposal-tamper",
            artifact_id="artifact-1",
            base_revision_number=1,
            mutation_type=ArtifactMutationType.REPLACE_CONTENT,
            content=document("approved content"),
            idempotency_key="proposal-tamper-key",
        ),
        assistant_context(),
    )
    approval_store.decide(
        approval_id=proposal.approval_id,
        workspace_id="workspace-1",
        approve=True,
        actor="user-1",
        reason="Reviewed exact proposal",
    )
    with service.store._connect() as connection:
        connection.execute(
            "UPDATE artifact_mutation_proposals SET content_json = ? WHERE proposal_id = ?",
            (
                '{"blocks":[],"kind":"document","language":"tr",'
                '"pageMode":"document","schemaVersion":1}',
                "proposal-tamper",
            ),
        )
        connection.commit()

    with pytest.raises(ArtifactDomainError) as denied:
        service.apply_proposal(
            ApplyArtifactProposalCommand(
                proposal_id="proposal-tamper",
                expected_revision_number=1,
                approval_id=proposal.approval_id,
            ),
            assistant_context(),
        )

    assert denied.value.code is ArtifactErrorCode.ARTIFACT_POLICY_UNAVAILABLE
    assert service.get(
        GetArtifactQuery(artifact_id="artifact-1"), user_context()
    ).artifact.current_revision_number == 1
    assert approval_store.get(
        proposal.approval_id, workspace_id="workspace-1"
    ).status.value == "approved"


def test_artifact_proposal_revalidates_complete_request_hash_before_claim(
    tmp_path: Path,
) -> None:
    approval_store = ApprovalStore(tmp_path / "approvals.sqlite3")
    service = ArtifactService(tmp_path / "artifact-root", approval_store=approval_store)
    service.create(create_command(), user_context())
    proposal = service.propose_mutation(
        proposal_command(
            service,
            proposal_id="proposal-request-tamper",
            artifact_id="artifact-1",
            base_revision_number=1,
            mutation_type=ArtifactMutationType.REPLACE_CONTENT,
            content=document("approved content"),
            idempotency_key="proposal-request-tamper-key",
        ),
        assistant_context(),
    )
    approval_store.decide(
        approval_id=proposal.approval_id,
        workspace_id="workspace-1",
        approve=True,
        actor="user-1",
        reason="Reviewed exact proposal",
    )
    with service.store._connect() as connection:
        connection.execute(
            "UPDATE artifact_mutation_proposals SET summary = ? WHERE proposal_id = ?",
            ("tampered summary", "proposal-request-tamper"),
        )
        connection.commit()

    with pytest.raises(ArtifactDomainError) as denied:
        service.apply_proposal(
            ApplyArtifactProposalCommand(
                proposal_id="proposal-request-tamper",
                expected_revision_number=1,
                approval_id=proposal.approval_id,
            ),
            assistant_context(),
        )
    assert denied.value.details["reasonCode"] == "ARTIFACT_PROPOSAL_INTEGRITY_INVALID"
    assert service.get(
        GetArtifactQuery(artifact_id="artifact-1"), user_context()
    ).artifact.current_revision_number == 1


def test_applied_proposal_replay_does_not_depend_on_mutable_payload(tmp_path: Path) -> None:
    approval_store = ApprovalStore(tmp_path / "approvals.sqlite3")
    service = ArtifactService(tmp_path / "artifact-root", approval_store=approval_store)
    service.create(create_command(), user_context())
    proposal = service.propose_mutation(
        proposal_command(
            service,
            proposal_id="proposal-replay",
            artifact_id="artifact-1",
            base_revision_number=1,
            mutation_type=ArtifactMutationType.REPLACE_CONTENT,
            content=document("approved content"),
            idempotency_key="proposal-replay-key",
        ),
        assistant_context(),
    )
    approval_store.decide(
        approval_id=proposal.approval_id,
        workspace_id="workspace-1",
        approve=True,
        actor="user-1",
        reason="Reviewed exact proposal",
    )
    command = ApplyArtifactProposalCommand(
        proposal_id="proposal-replay",
        expected_revision_number=1,
        approval_id=proposal.approval_id,
    )
    applied = service.apply_proposal(command, assistant_context())
    with service.store._connect() as connection:
        connection.execute(
            "UPDATE artifact_mutation_proposals SET content_json = ? WHERE proposal_id = ?",
            ("{}", "proposal-replay"),
        )
        connection.commit()
    replay = service.apply_proposal(command, assistant_context())
    assert replay.disposition == "idempotent_replay"
    assert replay.revision.revision_id == applied.revision.revision_id


def test_artifact_proposal_stale_base_does_not_claim_approval_or_write_revision(
    tmp_path: Path,
) -> None:
    approval_store = ApprovalStore(tmp_path / "approvals.sqlite3")
    service = ArtifactService(tmp_path / "artifact-root", approval_store=approval_store)
    service.create(create_command(), user_context())
    assistant = assistant_context()
    proposal = service.propose_mutation(
        proposal_command(service,
            proposal_id="proposal-stale",
            artifact_id="artifact-1",
            base_revision_number=1,
            mutation_type=ArtifactMutationType.REPLACE_CONTENT,
            content=document("stale AI proposal"),
            idempotency_key="proposal-stale-key",
            context_sha256="1" * 64,
            selection_sha256="2" * 64,
        ),
        assistant,
    )
    approval_store.decide(
        approval_id=proposal.approval_id,
        workspace_id="workspace-1",
        approve=True,
        actor="user-1",
        reason="Reviewed exact proposal",
    )
    service.mutate(
        MutateArtifactCommand(
            artifact_id="artifact-1",
            expected_revision_number=1,
            mutation_type=ArtifactMutationType.REPLACE_CONTENT,
            content=document("independent r2"),
            idempotency_key="independent-r2",
        ),
        user_context(),
    )

    with pytest.raises(ArtifactDomainError) as stale:
        service.apply_proposal(
            ApplyArtifactProposalCommand(
                proposal_id="proposal-stale",
                expected_revision_number=2,
                approval_id=proposal.approval_id,
            ),
            assistant,
        )

    assert stale.value.code is ArtifactErrorCode.ARTIFACT_REVISION_CONFLICT
    assert service.get(
        GetArtifactQuery(artifact_id="artifact-1"), user_context()
    ).artifact.current_revision_number == 2
    ticket = approval_store.get(proposal.approval_id, workspace_id="workspace-1")
    assert ticket is not None
    assert ticket.status.value == "approved"
    with service.store._connect() as connection:
        row = connection.execute(
            "SELECT status FROM artifact_mutation_proposals WHERE proposal_id = ?",
            ("proposal-stale",),
        ).fetchone()
    assert row["status"] == "stale"


def test_artifact_proposal_rejects_wrong_action_or_executor_approval(tmp_path: Path) -> None:
    approval_store = ApprovalStore(tmp_path / "approvals.sqlite3")
    service = ArtifactService(tmp_path / "artifact-root", approval_store=approval_store)
    service.create(create_command(), user_context())
    proposal = service.propose_mutation(
        proposal_command(service,
            proposal_id="proposal-1",
            artifact_id="artifact-1",
            base_revision_number=1,
            mutation_type=ArtifactMutationType.REPLACE_CONTENT,
            content=document("AI proposal"),
            idempotency_key="proposal-key-1",
            context_sha256="1" * 64,
            selection_sha256="2" * 64,
        ),
        assistant_context(),
    )
    rogue = approval_store.create_ticket(
        workspace_id="workspace-1",
        run_id="rogue-request",
        target_kind="artifact_mutation_proposal",
        target_ref="workspace-1:artifact-1:proposal-1",
        action_hash="f" * 64,
        policy_hash="e" * 64,
        request_hash="d" * 64,
        snapshot_hash="c" * 64,
        snapshot={"executorPrincipalId": "assistant-1"},
        ttl_seconds=300,
        idempotency_key="rogue-approval",
    )
    approval_store.decide(
        approval_id=rogue.approval_id,
        workspace_id="workspace-1",
        approve=True,
        actor="user-1",
        reason="wrong payload",
    )

    with pytest.raises(ArtifactDomainError) as wrong_action:
        service.apply_proposal(
            ApplyArtifactProposalCommand(
                proposal_id="proposal-1",
                expected_revision_number=1,
                approval_id=rogue.approval_id,
            ),
            assistant_context(),
        )

    approval_store.decide(
        approval_id=proposal.approval_id,
        workspace_id="workspace-1",
        approve=True,
        actor="user-1",
        reason="right payload",
    )
    other_assistant = assistant_context().model_copy(update={"principal_id": "assistant-2"})
    with pytest.raises(ArtifactDomainError) as wrong_executor:
        service.apply_proposal(
            ApplyArtifactProposalCommand(
                proposal_id="proposal-1",
                expected_revision_number=1,
                approval_id=proposal.approval_id,
            ),
            other_assistant,
        )

    assert wrong_action.value.code is ArtifactErrorCode.ARTIFACT_PERMISSION_DENIED
    assert wrong_executor.value.code is ArtifactErrorCode.ARTIFACT_PERMISSION_DENIED


def test_artifact_proposal_cross_workspace_lookup_is_indistinguishable(tmp_path: Path) -> None:
    service = ArtifactService(
        tmp_path / "artifact-root",
        approval_store=ApprovalStore(tmp_path / "approvals.sqlite3"),
    )
    service.create(create_command(), user_context("artifact_admin"))
    proposal = service.propose_mutation(
        proposal_command(service,
            proposal_id="proposal-private",
            artifact_id="artifact-1",
            base_revision_number=1,
            mutation_type=ArtifactMutationType.REPLACE_CONTENT,
            content=document("Private proposal"),
            idempotency_key="proposal-private-key",
            summary="Private proposal",
            context_sha256="1" * 64,
            selection_sha256="2" * 64,
        ),
        assistant_context(),
    )
    foreign_context = assistant_context().model_copy(update={"workspace_id": "workspace-2"})

    errors: list[ArtifactDomainError] = []
    for proposal_id in (proposal.proposal_id, "proposal-missing"):
        with pytest.raises(ArtifactDomainError) as caught:
            service.apply_proposal(
                ApplyArtifactProposalCommand(
                    proposal_id=proposal_id,
                    expected_revision_number=1,
                    approval_id=proposal.approval_id,
                ),
                foreign_context,
            )
        errors.append(caught.value)

    assert [(error.code, error.message) for error in errors] == [
        (ArtifactErrorCode.ARTIFACT_NOT_FOUND, "artifact mutation proposal does not exist"),
        (ArtifactErrorCode.ARTIFACT_NOT_FOUND, "artifact mutation proposal does not exist"),
    ]


def test_document_service_duplicate_and_archive_are_workspace_scoped(tmp_path: Path) -> None:
    service = ArtifactService(tmp_path / "artifact-root")
    admin = user_context("artifact_admin")
    created = service.create(create_command(), admin)
    duplicated = service.duplicate(
        DuplicateArtifactCommand(
            source_artifact_id="artifact-1",
            source_revision_id=created.revision.revision_id,
            artifact_id="artifact-2",
            title="Operations plan copy",
            idempotency_key="duplicate-1",
        ),
        admin,
    )
    archived = service.archive(
        ArchiveArtifactCommand(
            artifact_id="artifact-1",
            expected_revision_number=1,
        ),
        admin,
    )
    with pytest.raises(ArtifactDomainError) as archived_restore:
        service.restore(
            RestoreArtifactCommand(
                artifact_id="artifact-1",
                source_revision_id=archived.revision.revision_id,
                expected_revision_number=1,
                idempotency_key="restore-archived",
            ),
            admin,
        )
    with pytest.raises(ArtifactDomainError) as archived_mutation:
        service.mutate(
            MutateArtifactCommand(
                artifact_id="artifact-1",
                expected_revision_number=1,
                mutation_type=ArtifactMutationType.REPLACE_CONTENT,
                content=document("must remain archived"),
                idempotency_key="mutate-archived",
            ),
            admin,
        )

    assert duplicated.artifact.artifact_id == "artifact-2"
    assert duplicated.artifact.current_revision_number == 1
    assert archived.artifact.status is ArtifactStatus.ARCHIVED
    assert archived_restore.value.code is ArtifactErrorCode.ARTIFACT_PERMISSION_DENIED
    assert archived_mutation.value.code is ArtifactErrorCode.ARTIFACT_PERMISSION_DENIED
    assert service.get(GetArtifactQuery(artifact_id="artifact-2"), admin).content is not None


def test_duplicate_can_fork_validated_local_content_with_backend_owned_provenance(
    tmp_path: Path,
) -> None:
    service = ArtifactService(tmp_path / "artifact-root")
    admin = user_context("artifact_admin")
    created = service.create(create_command(), admin)
    local_draft = document("preserved local conflict draft")

    forked = service.duplicate(
        DuplicateArtifactCommand(
            source_artifact_id="artifact-1",
            source_revision_id=created.revision.revision_id,
            artifact_id="artifact-fork",
            title="Operations plan (local draft)",
            content_override=local_draft,
            idempotency_key="duplicate-local-draft-1",
        ),
        admin,
    )
    readback = service.get(GetArtifactQuery(artifact_id="artifact-fork"), admin)

    assert readback.content.model_dump(mode="json", by_alias=True) == local_draft
    assert forked.artifact.data_class == created.artifact.data_class
    assert forked.revision.mutation_type is ArtifactMutationType.DUPLICATE
    assert forked.revision.base_revision_id == created.revision.revision_id
    assert forked.artifact.metadata["forkedFromArtifactId"] == "artifact-1"
    assert forked.artifact.metadata["forkedFromRevisionId"] == created.revision.revision_id
    with service.store._connect() as connection:
        source_link = connection.execute(
            "SELECT link_type, target_id FROM artifact_links WHERE artifact_id = ?",
            (forked.artifact.artifact_id,),
        ).fetchone()
    assert source_link is not None
    assert source_link["link_type"] == "source"
    assert source_link["target_id"] == created.artifact.artifact_id


def test_duplicate_requires_an_explicit_source_revision_anchor() -> None:
    with pytest.raises(ValidationError):
        DuplicateArtifactCommand(
            source_artifact_id="artifact-1",
            title="Unanchored copy",
            idempotency_key="duplicate-unanchored",
        )


def test_duplicate_rejects_an_empty_local_content_override(tmp_path: Path) -> None:
    service = ArtifactService(tmp_path / "artifact-root")
    admin = user_context("artifact_admin")
    created = service.create(create_command(), admin)

    with pytest.raises(ArtifactDomainError) as caught:
        service.duplicate(
            DuplicateArtifactCommand(
                source_artifact_id=created.artifact.artifact_id,
                source_revision_id=created.revision.revision_id,
                artifact_id="artifact-empty-override",
                title="Invalid empty draft",
                content_override={},
                idempotency_key="duplicate-empty-override",
            ),
            admin,
        )

    assert caught.value.code is ArtifactErrorCode.ARTIFACT_SCHEMA_INVALID
    with pytest.raises(ArtifactDomainError) as missing:
        service.get(GetArtifactQuery(artifact_id="artifact-empty-override"), admin)
    assert missing.value.code is ArtifactErrorCode.ARTIFACT_NOT_FOUND


def test_duplicate_idempotency_rejects_concurrent_different_payloads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = ArtifactService(tmp_path / "artifact-root")
    admin = user_context("artifact_admin")
    created = service.create(create_command(), admin)
    barrier = Barrier(2)
    load_replay = service._load_operation_replay

    def synchronized_load(*args: object) -> object:
        replay = load_replay(*args)
        barrier.wait(timeout=5)
        return replay

    monkeypatch.setattr(service, "_load_operation_replay", synchronized_load)
    commands = [
        DuplicateArtifactCommand(
            source_artifact_id=created.artifact.artifact_id,
            source_revision_id=created.revision.revision_id,
            artifact_id=f"artifact-concurrent-{suffix}",
            title=f"Concurrent {suffix}",
            content_override=document(f"payload-{suffix}"),
            idempotency_key="duplicate-concurrent-different",
        )
        for suffix in ("a", "b")
    ]

    def duplicate(command: DuplicateArtifactCommand) -> object:
        try:
            return service.duplicate(command, admin)
        except ArtifactDomainError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(duplicate, commands))

    successful = [outcome for outcome in outcomes if not isinstance(outcome, Exception)]
    rejected = [outcome for outcome in outcomes if isinstance(outcome, ArtifactDomainError)]
    assert len(successful) == 1
    assert len(rejected) == 1
    assert rejected[0].code is ArtifactErrorCode.IDEMPOTENCY_KEY_REUSE_MISMATCH
    with service.store._connect() as connection:
        targets = connection.execute(
            "SELECT artifact_id FROM artifacts WHERE artifact_id LIKE 'artifact-concurrent-%'"
        ).fetchall()
        dedup_count = connection.execute(
            "SELECT COUNT(*) FROM artifact_operation_dedup WHERE idempotency_key = ?",
            ("duplicate-concurrent-different",),
        ).fetchone()[0]
    assert len(targets) == 1
    assert dedup_count == 1


def test_duplicate_idempotency_replays_concurrent_identical_payloads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = ArtifactService(tmp_path / "artifact-root")
    admin = user_context("artifact_admin")
    created = service.create(create_command(), admin)
    barrier = Barrier(2)
    load_replay = service._load_operation_replay

    def synchronized_load(*args: object) -> object:
        replay = load_replay(*args)
        barrier.wait(timeout=5)
        return replay

    monkeypatch.setattr(service, "_load_operation_replay", synchronized_load)
    command = DuplicateArtifactCommand(
        source_artifact_id=created.artifact.artifact_id,
        source_revision_id=created.revision.revision_id,
        artifact_id="artifact-concurrent-same",
        title="Concurrent same",
        content_override=document("same-payload"),
        idempotency_key="duplicate-concurrent-same",
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda _: service.duplicate(command, admin), range(2)))

    assert sorted(outcome.disposition for outcome in outcomes) == [
        "created",
        "idempotent_replay",
    ]
    assert {outcome.artifact.artifact_id for outcome in outcomes} == {
        "artifact-concurrent-same"
    }


def test_duplicate_records_replay_atomically_before_a_lost_response(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "artifact-root"
    service = ArtifactService(root)
    admin = user_context("artifact_admin")
    created = service.create(create_command(), admin)
    command = DuplicateArtifactCommand(
        source_artifact_id=created.artifact.artifact_id,
        source_revision_id=created.revision.revision_id,
        artifact_id="artifact-lost-response",
        title="Lost response",
        content_override=document("committed-before-response-loss"),
        idempotency_key="duplicate-lost-response",
    )
    create_duplicate = service.store.create_duplicate_artifact

    def lose_response(*args: object, **kwargs: object) -> object:
        create_duplicate(*args, **kwargs)
        raise RuntimeError("simulated response loss")

    monkeypatch.setattr(service.store, "create_duplicate_artifact", lose_response)
    with pytest.raises(RuntimeError, match="simulated response loss"):
        service.duplicate(command, admin)

    with service.store._connect() as connection:
        dedup_count = connection.execute(
            "SELECT COUNT(*) FROM artifact_operation_dedup WHERE idempotency_key = ?",
            (command.idempotency_key,),
        ).fetchone()[0]
    assert dedup_count == 1

    replay = ArtifactService(root).duplicate(command, admin)
    assert replay.disposition == "idempotent_replay"
    assert replay.artifact.artifact_id == "artifact-lost-response"


def test_operation_dedup_rejects_create_and_duplicate_with_the_same_global_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = ArtifactService(tmp_path / "artifact-root")
    admin = user_context("artifact_admin")
    source = service.create(create_command(key="source-create"), admin)
    shared_key = "cross-operation-key"
    create = CreateArtifactCommand(
        artifact_id="target-create",
        kind=ArtifactKind.DOCUMENT,
        title="Create target",
        data_class=ArtifactDataClass.INTERNAL,
        content=document("created payload"),
        idempotency_key=shared_key,
    )
    duplicate = DuplicateArtifactCommand(
        source_artifact_id=source.artifact.artifact_id,
        source_revision_id=source.revision.revision_id,
        artifact_id="target-duplicate",
        title="Duplicate target",
        content_override=document("duplicated payload"),
        idempotency_key=shared_key,
    )
    barrier = Barrier(2)
    load_replay = service._load_operation_replay

    def synchronized_load(*args: object) -> object:
        replay = load_replay(*args)
        barrier.wait(timeout=5)
        return replay

    monkeypatch.setattr(service, "_load_operation_replay", synchronized_load)

    def call_create() -> object:
        try:
            return service.create(create, admin)
        except ArtifactDomainError as exc:
            return exc

    def call_duplicate() -> object:
        try:
            return service.duplicate(duplicate, admin)
        except ArtifactDomainError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(lambda call: call(), (call_create, call_duplicate)))

    successful = [outcome for outcome in outcomes if not isinstance(outcome, Exception)]
    rejected = [outcome for outcome in outcomes if isinstance(outcome, ArtifactDomainError)]
    assert len(successful) == 1
    assert len(rejected) == 1
    assert rejected[0].code is ArtifactErrorCode.IDEMPOTENCY_KEY_REUSE_MISMATCH
    with service.store._connect() as connection:
        targets = connection.execute(
            "SELECT artifact_id FROM artifacts WHERE artifact_id LIKE 'target-%'"
        ).fetchall()
        dedup_count = connection.execute(
            "SELECT COUNT(*) FROM artifact_operation_dedup WHERE idempotency_key = ?",
            (shared_key,),
        ).fetchone()[0]
    assert len(targets) == 1
    assert dedup_count == 1


def test_document_service_revalidates_schema_without_leaking_raw_content_in_error(
    tmp_path: Path,
) -> None:
    service = ArtifactService(tmp_path / "artifact-root")
    command = create_command()
    invalid = command.model_copy(
        update={"content": {"kind": "document", "secret": "raw-secret-marker"}}
    )

    with pytest.raises(ArtifactDomainError) as caught:
        service.create(invalid, user_context())

    assert caught.value.code is ArtifactErrorCode.ARTIFACT_SCHEMA_INVALID
    assert "raw-secret-marker" not in str(caught.value)
