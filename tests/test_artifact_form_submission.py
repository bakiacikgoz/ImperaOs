from __future__ import annotations

import json
from pathlib import Path

import pytest

from imperaos.artifacts.commands import CreateArtifactCommand, SubmitArtifactFormCommand
from imperaos.artifacts.errors import ArtifactDomainError, ArtifactErrorCode
from imperaos.artifacts.form_continuation import ArtifactFormContinuationGateway
from imperaos.artifacts.models import OperationContext, PrincipalType
from imperaos.artifacts.rpc_protocol import ArtifactRpcMethod, RpcPrincipal, RpcRequest
from imperaos.artifacts.rpc_server import ArtifactRpcServer
from imperaos.artifacts.service import ArtifactService
from imperaos.governance.approval_store import ApprovalStore


def _context(*, assistant: bool = False) -> OperationContext:
    return OperationContext(
        workspace_id="workspace-1",
        principal_type=PrincipalType.ASSISTANT if assistant else PrincipalType.USER,
        principal_id="assistant-1" if assistant else "user-1",
        roles=("artifact_admin",),
        request_id="request-form-submit",
    )


def _form_content(*, continuation: str = "deny") -> dict[str, object]:
    return {
        "kind": "form",
        "schemaVersion": 1,
        "schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "minLength": 2, "maxLength": 100},
                "count": {"type": "integer", "minimum": 1, "maximum": 10},
            },
            "required": ["name"],
            "additionalProperties": False,
        },
        "uiSchema": {"name": {"ui:widget": "text"}},
        "behavior": {
            "submitMode": "explicit",
            "externalContinuation": continuation,
        },
        "sensitivePaths": ["/name"],
    }


def _create_form(
    service: ArtifactService,
    *,
    continuation: str = "deny",
) -> tuple[str, str]:
    result = service.create(
        CreateArtifactCommand(
            artifact_id="artifact-form-1",
            kind="form",
            title="Governed form",
            data_class="internal",
            content=_form_content(continuation=continuation),
            idempotency_key="create-form-1",
        ),
        _context(),
    )
    return result.artifact.artifact_id, result.revision.revision_id


def _submit(artifact_id: str, revision_id: str, **updates: object) -> SubmitArtifactFormCommand:
    payload: dict[str, object] = {
        "artifact_id": artifact_id,
        "schema_revision_id": revision_id,
        "response": {"name": "Ada", "count": 2},
        "persistence_policy": "none",
        "idempotency_key": "submit-form-1",
        **updates,
    }
    return SubmitArtifactFormCommand.model_validate(payload)


def test_form_submit_revalidates_exact_revision_and_persists_hash_only(tmp_path: Path) -> None:
    service = ArtifactService(tmp_path / "artifacts")
    artifact_id, revision_id = _create_form(service)
    private_value = "private-response-canary"

    result = service.submit_form(
        _submit(artifact_id, revision_id, response={"name": private_value, "count": 2}),
        _context(),
    )

    assert result.status == "accepted"
    assert result.continuation_action == "none"
    assert result.disposition == "created"
    with service.store._connect() as connection:
        row = connection.execute(
            "SELECT * FROM form_submissions WHERE submission_id = ?",
            (result.submission_id,),
        ).fetchone()
    assert row is not None
    assert row["schema_revision_id"] == revision_id
    assert row["persistence_policy"] == "none"
    assert row["redacted_summary_json"] == "{}"
    assert private_value not in json.dumps(dict(row))


def test_invalid_form_response_is_bounded_and_does_not_echo_values(tmp_path: Path) -> None:
    service = ArtifactService(tmp_path / "artifacts")
    artifact_id, revision_id = _create_form(service)
    private_value = "private-invalid-response-canary"

    with pytest.raises(ArtifactDomainError) as caught:
        service.submit_form(
            _submit(artifact_id, revision_id, response={"name": private_value, "count": 999}),
            _context(),
        )

    assert caught.value.code is ArtifactErrorCode.FORM_VALIDATION_FAILED
    assert private_value not in caught.value.message
    assert private_value not in json.dumps(caught.value.details)
    with service.store._connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM form_submissions").fetchone()[0] == 0


def test_form_submit_rejects_non_none_persistence_policy(tmp_path: Path) -> None:
    service = ArtifactService(tmp_path / "artifacts")
    artifact_id, revision_id = _create_form(service)
    with pytest.raises(ArtifactDomainError) as caught:
        service.submit_form(
            _submit(artifact_id, revision_id, persistence_policy="encrypted"),
            _context(),
        )
    assert caught.value.code is ArtifactErrorCode.FORM_SENSITIVE_PERSISTENCE_DENIED


def test_form_submit_idempotency_replays_and_rejects_changed_response(tmp_path: Path) -> None:
    service = ArtifactService(tmp_path / "artifacts")
    artifact_id, revision_id = _create_form(service)
    command = _submit(artifact_id, revision_id)

    first = service.submit_form(command, _context())
    replay = ArtifactService(tmp_path / "artifacts").submit_form(command, _context())
    assert replay.submission_id == first.submission_id
    assert replay.disposition == "idempotent_replay"

    with pytest.raises(ArtifactDomainError) as mismatch:
        service.submit_form(
            _submit(artifact_id, revision_id, response={"name": "Grace", "count": 3}),
            _context(),
        )
    assert mismatch.value.code is ArtifactErrorCode.IDEMPOTENCY_KEY_REUSE_MISMATCH


def test_assistant_cannot_submit_and_continuation_never_executes(tmp_path: Path) -> None:
    approvals = ApprovalStore(tmp_path / "approvals.sqlite3")
    service = ArtifactService(
        tmp_path / "artifacts",
        continuation_gateway=ArtifactFormContinuationGateway(approvals, ttl_seconds=3600),
    )
    artifact_id, revision_id = _create_form(service, continuation="approval_required")

    with pytest.raises(ArtifactDomainError) as denied:
        service.submit_form(_submit(artifact_id, revision_id), _context(assistant=True))
    assert denied.value.code is ArtifactErrorCode.ARTIFACT_PERMISSION_DENIED

    result = service.submit_form(_submit(artifact_id, revision_id), _context())
    assert result.status == "pending_continuation"
    assert result.continuation_action == "require_approval"
    assert result.approval_id is not None
    assert result.reason_code == "FORM_CONTINUATION_APPROVAL_REQUIRED"
    assert result.action_hash is not None
    ticket = approvals.get(result.approval_id, workspace_id="workspace-1")
    assert ticket is not None
    assert ticket.status.value == "pending"
    assert ticket.target_kind == "artifact_form_continuation"
    assert ticket.action_hash == result.action_hash
    assert ticket.snapshot["response_sha256"] == result.response_sha256
    assert "response" not in ticket.snapshot
    with service.store._connect() as connection:
        outbox = connection.execute(
            "SELECT * FROM artifact_form_continuation_outbox WHERE submission_id = ?",
            (result.submission_id,),
        ).fetchone()
    assert outbox is not None
    assert outbox["status"] == "ticketed"
    assert outbox["approval_id"] == result.approval_id
    assert outbox["action_hash"] == result.action_hash

    replay = service.submit_form(_submit(artifact_id, revision_id), _context())
    assert replay.approval_id == result.approval_id
    assert replay.disposition == "idempotent_replay"


def test_default_form_continuation_reuses_injected_approval_store(tmp_path: Path) -> None:
    approvals = ApprovalStore(tmp_path / "custom-approvals.sqlite3")
    service = ArtifactService(tmp_path / "artifacts", approval_store=approvals)
    artifact_id, revision_id = _create_form(service, continuation="approval_required")

    result = service.submit_form(_submit(artifact_id, revision_id), _context())

    assert result.approval_id is not None
    ticket = approvals.get(result.approval_id, workspace_id="workspace-1")
    assert ticket is not None
    assert ticket.target_kind == "artifact_form_continuation"


def test_form_continuation_never_creates_ticket_before_submission_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    approvals = ApprovalStore(tmp_path / "approvals.sqlite3")
    service = ArtifactService(
        tmp_path / "artifacts",
        continuation_gateway=ArtifactFormContinuationGateway(approvals),
    )
    artifact_id, revision_id = _create_form(service, continuation="approval_required")

    def fail_submission(**_kwargs: object) -> bool:
        raise ArtifactDomainError(
            ArtifactErrorCode.ARTIFACT_STORAGE_LOCKED,
            "controlled storage failure",
        )

    monkeypatch.setattr(service.store, "create_form_submission", fail_submission)
    with pytest.raises(ArtifactDomainError) as caught:
        service.submit_form(_submit(artifact_id, revision_id), _context())
    assert caught.value.code is ArtifactErrorCode.ARTIFACT_STORAGE_LOCKED
    assert approvals.list_pending(workspace_id="workspace-1") == []


def test_form_continuation_gateway_failure_replays_from_durable_outbox(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    approvals = ApprovalStore(tmp_path / "approvals.sqlite3")
    gateway = ArtifactFormContinuationGateway(approvals)
    service = ArtifactService(tmp_path / "artifacts", continuation_gateway=gateway)
    artifact_id, revision_id = _create_form(service, continuation="approval_required")
    original = gateway.request_approval
    attempts = 0

    def fail_once(**kwargs: object):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("controlled approval outage")
        return original(**kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(gateway, "request_approval", fail_once)
    with pytest.raises(ArtifactDomainError) as caught:
        service.submit_form(_submit(artifact_id, revision_id), _context())
    assert caught.value.code is ArtifactErrorCode.ARTIFACT_POLICY_UNAVAILABLE
    with service.store._connect() as connection:
        failed = connection.execute(
            "SELECT * FROM artifact_form_continuation_outbox"
        ).fetchone()
        assert connection.execute("SELECT COUNT(*) FROM form_submissions").fetchone()[0] == 1
    assert failed is not None
    assert failed["status"] == "failed"
    assert failed["attempt_count"] == 1
    assert approvals.list_pending(workspace_id="workspace-1") == []

    replay = service.submit_form(_submit(artifact_id, revision_id), _context())
    assert replay.disposition == "idempotent_replay"
    assert replay.approval_id is not None
    with service.store._connect() as connection:
        healed = connection.execute(
            "SELECT * FROM artifact_form_continuation_outbox"
        ).fetchone()
    assert healed is not None
    assert healed["status"] == "ticketed"
    assert healed["attempt_count"] == 2


def test_form_continuation_replay_heals_ticket_created_before_outbox_mark(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    approvals = ApprovalStore(tmp_path / "approvals.sqlite3")
    gateway = ArtifactFormContinuationGateway(approvals)
    service = ArtifactService(tmp_path / "artifacts", continuation_gateway=gateway)
    artifact_id, revision_id = _create_form(service, continuation="approval_required")
    original = service.store.mark_form_continuation_ticketed
    attempts = 0

    def fail_mark_once(**kwargs: object) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_STORAGE_LOCKED,
                "controlled ticket mark failure",
            )
        original(**kwargs)

    monkeypatch.setattr(service.store, "mark_form_continuation_ticketed", fail_mark_once)
    with pytest.raises(ArtifactDomainError) as caught:
        service.submit_form(_submit(artifact_id, revision_id), _context())
    assert caught.value.code is ArtifactErrorCode.ARTIFACT_STORAGE_LOCKED
    pending = approvals.list_pending(workspace_id="workspace-1")
    assert len(pending) == 1
    approval_id = pending[0].approval_id

    replay = service.submit_form(_submit(artifact_id, revision_id), _context())
    assert replay.disposition == "idempotent_replay"
    assert replay.approval_id == approval_id
    assert len(approvals.list_pending(workspace_id="workspace-1")) == 1
    with service.store._connect() as connection:
        healed = connection.execute(
            "SELECT * FROM artifact_form_continuation_outbox"
        ).fetchone()
    assert healed is not None
    assert healed["status"] == "ticketed"
    assert healed["approval_id"] == approval_id


@pytest.mark.parametrize(
    ("format_name", "invalid_value"),
    [
        ("date", "2026-99-99"),
        ("date-time", "2026-07-16 10:00:00"),
        ("hostname", "invalid_host_name"),
        ("ipv4", "999.1.1.1"),
        ("ipv6", "not-ipv6"),
        ("uri-reference", "bad uri with spaces"),
    ],
)
def test_form_submit_rejects_invalid_allowlisted_formats(
    tmp_path: Path,
    format_name: str,
    invalid_value: str,
) -> None:
    service = ArtifactService(tmp_path / "artifacts")
    created = service.create(
        CreateArtifactCommand(
            artifact_id="artifact-form-format",
            kind="form",
            title="Format form",
            data_class="internal",
            content={
                "kind": "form",
                "schemaVersion": 1,
                "schema": {
                    "type": "object",
                    "properties": {"value": {"type": "string", "format": format_name}},
                    "required": ["value"],
                    "additionalProperties": False,
                },
            },
            idempotency_key="create-format-form",
        ),
        _context(),
    )
    with pytest.raises(ArtifactDomainError) as caught:
        service.submit_form(
            _submit(
                created.artifact.artifact_id,
                created.revision.revision_id,
                response={"value": invalid_value},
            ),
            _context(),
        )
    assert caught.value.code is ArtifactErrorCode.FORM_VALIDATION_FAILED


def test_form_submit_rpc_dispatches_and_requires_bound_idempotency(tmp_path: Path) -> None:
    service = ArtifactService(tmp_path / "artifacts")
    artifact_id, revision_id = _create_form(service)
    server = ArtifactRpcServer(service)
    params = _submit(artifact_id, revision_id).model_dump(mode="json", by_alias=True)
    request = RpcRequest(
        contract_version="1.0",
        request_id="rpc-form-submit-1",
        method=ArtifactRpcMethod.ARTIFACT_FORM_SUBMIT,
        workspace_id="workspace-1",
        principal=RpcPrincipal(
            principal_id="user-1",
            principal_type=PrincipalType.USER,
            roles=("artifact_admin",),
        ),
        idempotency_key="submit-form-1",
        params=params,
    )

    response = server.handle_request(request)
    assert response.ok is True
    assert response.result is not None
    assert response.result["status"] == "accepted"
    assert response.result["disposition"] == "created"

    unbound = server.handle_request(
        request.model_copy(
            update={"request_id": "rpc-form-submit-unbound", "idempotency_key": None}
        )
    )
    assert unbound.ok is False
    assert unbound.error is not None
    assert unbound.error.code == "ARTIFACT_RPC_PROTOCOL_MISMATCH"
