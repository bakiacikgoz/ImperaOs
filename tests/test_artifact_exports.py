from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from imperaos.artifacts.commands import (
    BeginArtifactExportCommand,
    CancelArtifactExportCommand,
    CommitArtifactExportCommand,
    CreateArtifactCommand,
    PreflightArtifactExportCommand,
)
from imperaos.artifacts.errors import ArtifactDomainError, ArtifactErrorCode
from imperaos.artifacts.exports import ALLOWED_EXPORT_FORMATS
from imperaos.artifacts.models import (
    ArtifactDataClass,
    ArtifactKind,
    OperationContext,
    PrincipalType,
)
from imperaos.artifacts.rpc_protocol import ArtifactRpcMethod, RpcPrincipal, RpcRequest
from imperaos.artifacts.rpc_server import ArtifactRpcServer
from imperaos.artifacts.service import ArtifactService


def _context(principal_type: PrincipalType = PrincipalType.USER) -> OperationContext:
    return OperationContext(
        workspace_id="workspace-1",
        principal_type=principal_type,
        principal_id="user-1" if principal_type is PrincipalType.USER else "assistant-1",
        roles=("artifact_admin",),
        request_id="request-export",
    )


def _create_code(service: ArtifactService, *, schema_version: int = 1) -> tuple[str, str]:
    result = service.create(
        CreateArtifactCommand(
            artifact_id="artifact-code-1",
            kind=ArtifactKind.CODE,
            title="Safe source",
            data_class=ArtifactDataClass.INTERNAL,
            content={
                "kind": "code",
                "schemaVersion": schema_version,
                "filename": "main.py",
                "language": "python",
                "text": "print('display only')\n",
                "lineEnding": "lf",
                "executionPolicy": "deny",
            },
            idempotency_key="create-code-1",
        ),
        _context(),
    )
    return result.artifact.artifact_id, result.revision.revision_id


def test_source_export_accepts_the_exact_persisted_code_v2_revision(tmp_path: Path) -> None:
    service = ArtifactService(tmp_path / "artifacts")
    artifact_id, revision_id = _create_code(service, schema_version=2)

    begun = service.begin_export(
        BeginArtifactExportCommand(
            artifact_id=artifact_id,
            revision_id=revision_id,
            format="source",
            idempotency_key="export-code-v2",
        ),
        _context(),
    )

    assert begun.revision_id == revision_id
    assert begun.basename == "main.py"


def test_export_authority_binds_exact_revision_format_actor_and_terminal_state(
    tmp_path: Path,
) -> None:
    service = ArtifactService(tmp_path / "artifacts")
    artifact_id, revision_id = _create_code(service)
    begin_command = BeginArtifactExportCommand(
        artifact_id=artifact_id,
        revision_id=revision_id,
        format="source",
        idempotency_key="export-begin-1",
    )

    begun = service.begin_export(begin_command, _context())
    replay = service.begin_export(begin_command, _context())
    payload = b"print('display only')\n"
    preflight = PreflightArtifactExportCommand(
        export_id=begun.export_id,
        basename=begun.basename,
        sha256=hashlib.sha256(payload).hexdigest(),
        size_bytes=len(payload),
        idempotency_key="export-preflight-1",
    )
    with pytest.raises(ArtifactDomainError) as not_preflighted:
        service.commit_export(
            CommitArtifactExportCommand.model_validate(
                preflight.model_copy(
                    update={"idempotency_key": "export-commit-early"}
                ).model_dump(mode="python")
            ),
            _context(),
        )
    assert not_preflighted.value.code is ArtifactErrorCode.ARTIFACT_EXPORT_FAILED
    authorized = service.preflight_export(preflight, _context())
    committed = service.commit_export(
        CommitArtifactExportCommand(
            export_id=begun.export_id,
            basename=begun.basename,
            sha256=hashlib.sha256(payload).hexdigest(),
            size_bytes=len(payload),
            idempotency_key="export-commit-1",
        ),
        _context(),
    )

    assert begun.basename == "main.py"
    assert begun.format == "source"
    assert replay.model_dump(exclude={"disposition"}) == begun.model_dump(exclude={"disposition"})
    assert replay.disposition == "idempotent_replay"
    assert authorized.status == "pending"
    assert committed.status == "completed"
    assert committed.artifact_id == artifact_id
    assert service.operations.snapshot()["imperaos_artifact_export_bytes"] == len(payload)
    completed_series = next(
        item
        for item in service.operations.series_snapshot()
        if item["name"] == "imperaos_artifact_export_total"
        and item["labels"].get("result") == "success"
    )
    assert completed_series["labels"]["kind"] == "code"
    assert completed_series["labels"]["format"] == "source"
    with pytest.raises(ArtifactDomainError) as terminal:
        service.cancel_export(
            CancelArtifactExportCommand(
                export_id=begun.export_id,
                reason="user_cancelled",
                idempotency_key="export-cancel-after-commit",
            ),
            _context(),
        )
    assert terminal.value.code is ArtifactErrorCode.ARTIFACT_EXPORT_FAILED


def test_export_authority_denies_wrong_format_revision_and_assistant(tmp_path: Path) -> None:
    service = ArtifactService(tmp_path / "artifacts")
    artifact_id, revision_id = _create_code(service)

    for command in (
        BeginArtifactExportCommand(
            artifact_id=artifact_id,
            revision_id=revision_id,
            format="svg",
            idempotency_key="export-wrong-format",
        ),
        BeginArtifactExportCommand(
            artifact_id=artifact_id,
            revision_id="revision-missing",
            format="source",
            idempotency_key="export-wrong-revision",
        ),
    ):
        with pytest.raises(ArtifactDomainError):
            service.begin_export(command, _context())

    with pytest.raises(ArtifactDomainError) as denied:
        service.begin_export(
            BeginArtifactExportCommand(
                artifact_id=artifact_id,
                revision_id=revision_id,
                format="source",
                idempotency_key="export-assistant",
            ),
            _context(PrincipalType.ASSISTANT),
        )
    assert denied.value.code is ArtifactErrorCode.ARTIFACT_PERMISSION_DENIED


def test_preflighted_export_cannot_be_user_cancelled_and_failure_keeps_hash(
    tmp_path: Path,
) -> None:
    service = ArtifactService(tmp_path / "artifacts")
    artifact_id, revision_id = _create_code(service)
    begun = service.begin_export(
        BeginArtifactExportCommand(
            artifact_id=artifact_id,
            revision_id=revision_id,
            format="source",
            idempotency_key="export-preflight-cancel",
        ),
        _context(),
    )
    payload = b"print('display only')\n"
    digest = hashlib.sha256(payload).hexdigest()
    service.preflight_export(
        PreflightArtifactExportCommand(
            export_id=begun.export_id,
            basename=begun.basename,
            sha256=digest,
            size_bytes=len(payload),
            idempotency_key="preflight-cancel",
        ),
        _context(),
    )

    with pytest.raises(ArtifactDomainError) as denied:
        service.cancel_export(
            CancelArtifactExportCommand(
                export_id=begun.export_id,
                reason="user_cancelled",
                idempotency_key="cancel-preflighted",
            ),
            _context(),
        )
    assert denied.value.code is ArtifactErrorCode.ARTIFACT_EXPORT_FAILED

    failed = service.cancel_export(
        CancelArtifactExportCommand(
            export_id=begun.export_id,
            reason="native_write_failed",
            idempotency_key="fail-preflighted",
        ),
        _context(),
    )
    assert failed.status == "failed"
    assert failed.sha256 == digest
    assert failed.size_bytes == len(payload)


def test_export_rpc_dispatches_envelope_bound_begin_commit_cancel(tmp_path: Path) -> None:
    service = ArtifactService(tmp_path / "artifacts")
    artifact_id, revision_id = _create_code(service)
    server = ArtifactRpcServer(service)

    def request(method: ArtifactRpcMethod, params: dict[str, object], key: str) -> RpcRequest:
        return RpcRequest(
            contract_version="1.0",
            request_id=f"request-{key}",
            method=method,
            workspace_id="workspace-1",
            principal=RpcPrincipal(
                principal_id="user-1", principal_type=PrincipalType.USER, roles=("artifact_admin",)
            ),
            idempotency_key=key,
            params={**params, "idempotencyKey": key},
        )

    begun = server.handle_request(request(
        ArtifactRpcMethod.ARTIFACT_EXPORT_BEGIN,
        {"artifactId": artifact_id, "revisionId": revision_id, "format": "source"},
        "rpc-export-begin",
    ))
    assert begun.ok and begun.result is not None
    export_id = begun.result["exportId"]
    cancelled = server.handle_request(request(
        ArtifactRpcMethod.ARTIFACT_EXPORT_CANCEL,
        {"exportId": export_id, "reason": "user_cancelled"},
        "rpc-export-cancel",
    ))
    assert cancelled.ok and cancelled.result is not None
    assert cancelled.result["status"] == "cancelled"

    unbound = request(
        ArtifactRpcMethod.ARTIFACT_EXPORT_BEGIN,
        {"artifactId": artifact_id, "revisionId": revision_id, "format": "source"},
        "rpc-export-unbound",
    ).model_copy(update={"idempotency_key": None})
    denied = server.handle_request(unbound)
    assert denied.ok is False
    assert denied.error is not None
    assert denied.error.code == "ARTIFACT_RPC_PROTOCOL_MISMATCH"
def test_export_format_matrix_covers_every_artifact_kind() -> None:
    expected = {
        ArtifactKind.DOCUMENT: frozenset({"json", "markdown", "html"}),
        ArtifactKind.FORM: frozenset({"json", "submission-json", "csv"}),
        ArtifactKind.CODE: frozenset({"source", "txt"}),
        ArtifactKind.FLOW: frozenset({"json", "svg", "png"}),
        ArtifactKind.SPREADSHEET: frozenset({"csv", "xlsx"}),
        ArtifactKind.CANVAS: frozenset({"json", "svg", "png"}),
        ArtifactKind.SLIDES: frozenset({"pptx", "json"}),
    }
    assert expected == ALLOWED_EXPORT_FORMATS
