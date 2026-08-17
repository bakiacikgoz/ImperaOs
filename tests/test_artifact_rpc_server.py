from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

import pytest
from artifact_store_support import make_artifact_pair

from imperaos.artifacts.errors import ArtifactDomainError
from imperaos.artifacts.models import PrincipalType
from imperaos.artifacts.rpc_protocol import (
    ArtifactRpcMethod,
    RpcFrameDecoder,
    RpcPrincipal,
    RpcRequest,
    RpcResponse,
    encode_frame,
)
from imperaos.artifacts.rpc_server import ArtifactRpcServer
from imperaos.artifacts.service import ArtifactService


def _document(text: str) -> dict[str, object]:
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


def _request(
    request_id: str,
    method: ArtifactRpcMethod,
    params: dict[str, object] | None = None,
    *,
    idempotency_key: str | None = None,
) -> RpcRequest:
    return RpcRequest(
        contract_version="1.0",
        request_id=request_id,
        method=method,
        workspace_id="workspace-1",
        principal=RpcPrincipal(
            principal_id="user-1",
            principal_type=PrincipalType.USER,
            roles=("artifact_admin",),
        ),
        idempotency_key=idempotency_key,
        params=params or {},
    )


def _decode_responses(payload: bytes) -> list[RpcResponse]:
    decoder = RpcFrameDecoder()
    return [RpcResponse.model_validate_json(frame) for frame in decoder.feed(payload)]


def test_slides_patch_requires_envelope_bound_idempotency_key() -> None:
    valid = _request(
        "slides-patch-valid",
        ArtifactRpcMethod.ARTIFACT_SLIDES_PATCH,
        {"idempotencyKey": "slides-patch-1"},
        idempotency_key="slides-patch-1",
    )
    ArtifactRpcServer._validate_idempotency_binding(valid)

    with pytest.raises(ArtifactDomainError):
        ArtifactRpcServer._validate_idempotency_binding(
            _request(
                "slides-patch-mismatch",
                ArtifactRpcMethod.ARTIFACT_SLIDES_PATCH,
                {"idempotencyKey": "params-key"},
                idempotency_key="envelope-key",
            )
        )


def test_handshake_exposes_only_redacted_backend_license_capabilities(tmp_path: Path) -> None:
    response = ArtifactRpcServer(ArtifactService(tmp_path / "artifacts")).handle_request(
        _request("license-handshake", ArtifactRpcMethod.RPC_HANDSHAKE)
    )
    assert response.ok and response.result is not None
    assert response.result["licenseCapabilities"] == [
        {
            "contractVersion": "artifact-license-capability/v1", "kind": "spreadsheet",
            "enabled": False, "reasonCode": "ARTIFACT_LICENSE_EVIDENCE_MISSING",
        },
        {
            "contractVersion": "artifact-license-capability/v1", "kind": "canvas",
            "enabled": False, "reasonCode": "ARTIFACT_LICENSE_EVIDENCE_MISSING",
        },
    ]
    assert response.result["capabilitySnapshot"] == {
        "contractVersion": "artifact-runtime-capability-snapshot/v1",
        "rolloutStage": "disabled",
        "globalEnabled": False,
        "enabledArtifactKinds": [],
        "features": {
            "artifact_workspace.enabled": False,
            "artifact_workspace.document.enabled": False,
            "artifact_workspace.form.enabled": False,
            "artifact_workspace.code.enabled": False,
            "artifact_workspace.flow.enabled": False,
            "artifact_workspace.spreadsheet.enabled": False,
            "artifact_workspace.canvas.enabled": False,
            "artifact_workspace.slides.enabled": False,
            "artifact_workspace.export.enabled": False,
            "assistant_ui_runtime.enabled": False,
            "ai_sdk_tauri_transport.enabled": False,
        },
        "licenses": {"spreadsheet": False, "canvas": False},
        "kindCapabilities": {
            kind: {
                "enabled": False,
                "editable": False,
                "exportable": False,
                "reasonCode": "ARTIFACT_WORKSPACE_FEATURE_DISABLED",
                "requiresLicense": False,
                "adapter": (
                    "bundled_fallback"
                    if kind in {"spreadsheet", "canvas"}
                    else "built_in"
                ),
            }
            for kind in (
                "document",
                "form",
                "code",
                "flow",
                "spreadsheet",
                "canvas",
                "slides",
            )
        },
    }
    serialized = json.dumps(response.result)
    assert "secret" not in serialized.lower()
    assert "signature" not in serialized.lower()


def test_server_dispatches_service_calls_and_deduplicates_request_ids(tmp_path: Path) -> None:
    service = ArtifactService(tmp_path / "artifacts")
    server = ArtifactRpcServer(service)
    create = _request(
        "request-create",
        ArtifactRpcMethod.ARTIFACT_CREATE,
        {
            "artifactId": "artifact-1",
            "kind": "document",
            "title": "RPC document",
            "dataClass": "internal",
            "content": _document("rpc-v1"),
            "idempotencyKey": "create-1",
        },
        idempotency_key="create-1",
    )

    first = server.handle_request(create)
    replay = server.handle_request(create)
    mismatch = server.handle_request(
        create.model_copy(update={"params": {**create.params, "title": "Changed"}})
    )
    loaded = server.handle_request(
        _request(
            "request-get",
            ArtifactRpcMethod.ARTIFACT_GET,
            {"artifactId": "artifact-1"},
        )
    )
    assert first.result is not None
    source_revision_id = first.result["revision"]["revisionId"]
    duplicated = server.handle_request(
        _request(
            "request-duplicate",
            ArtifactRpcMethod.ARTIFACT_DUPLICATE,
            {
                "sourceArtifactId": "artifact-1",
                "sourceRevisionId": source_revision_id,
                "artifactId": "artifact-fork",
                "title": "RPC local draft",
                "contentOverride": _document("rpc-local-fork"),
                "idempotencyKey": "duplicate-1",
            },
            idempotency_key="duplicate-1",
        )
    )
    forked = server.handle_request(
        _request(
            "request-get-fork",
            ArtifactRpcMethod.ARTIFACT_GET,
            {"artifactId": "artifact-fork"},
        )
    )

    assert first.ok is True
    assert replay == first
    assert mismatch.ok is False
    assert mismatch.error is not None
    assert mismatch.error.code == "ARTIFACT_RPC_PROTOCOL_MISMATCH"
    assert loaded.ok is True
    assert loaded.result is not None
    assert loaded.result["artifact"]["artifactId"] == "artifact-1"
    assert duplicated.ok is True
    assert duplicated.result is not None
    assert duplicated.result["revision"]["mutationType"] == "duplicate"
    assert duplicated.result["revision"]["baseRevisionId"] == source_revision_id
    assert duplicated.result["artifact"]["metadata"] == {
        "forkedFromArtifactId": "artifact-1",
        "forkedFromRevisionId": source_revision_id,
    }
    assert forked.ok is True
    assert forked.result is not None
    assert forked.result["content"] == _document("rpc-local-fork")
    assert service.store.get_artifact("workspace-1", "artifact-1").current_revision_number == 1


def test_cross_workspace_and_unknown_artifacts_are_indistinguishable(tmp_path: Path) -> None:
    server = ArtifactRpcServer(ArtifactService(tmp_path / "artifacts"))
    created = server.handle_request(
        _request(
            "create-private-artifact",
            ArtifactRpcMethod.ARTIFACT_CREATE,
            {
                "artifactId": "private-artifact",
                "kind": "document",
                "title": "Private artifact",
                "dataClass": "internal",
                "content": _document("private"),
                "idempotencyKey": "create-private",
            },
            idempotency_key="create-private",
        )
    )
    assert created.ok is True

    foreign = _request(
        "foreign-read",
        ArtifactRpcMethod.ARTIFACT_GET,
        {"artifactId": "private-artifact"},
    ).model_copy(update={"workspace_id": "workspace-2"})
    missing = _request(
        "missing-read",
        ArtifactRpcMethod.ARTIFACT_GET,
        {"artifactId": "missing-artifact"},
    ).model_copy(update={"workspace_id": "workspace-2"})

    foreign_response = server.handle_request(foreign)
    missing_response = server.handle_request(missing)

    assert foreign_response.ok is False and missing_response.ok is False
    assert foreign_response.error is not None and missing_response.error is not None
    assert foreign_response.error.model_dump(exclude={"request_id"}) == (
        missing_response.error.model_dump(exclude={"request_id"})
    )


def test_server_stdio_is_framed_protocol_only_and_shutdown_stops_admission(
    tmp_path: Path,
) -> None:
    server = ArtifactRpcServer(ArtifactService(tmp_path / "artifacts"))
    stdin = BytesIO(
        encode_frame(_request("hello", ArtifactRpcMethod.RPC_HANDSHAKE))
        + encode_frame(_request("health", ArtifactRpcMethod.RPC_HEALTH))
        + encode_frame(_request("shutdown", ArtifactRpcMethod.RPC_SHUTDOWN))
        + encode_frame(_request("ignored", ArtifactRpcMethod.RPC_HEALTH))
    )
    stdout = BytesIO()
    stderr = BytesIO()

    exit_code = server.serve(stdin, stdout, stderr)
    responses = _decode_responses(stdout.getvalue())

    assert exit_code == 0
    assert [response.request_id for response in responses] == [
        "hello",
        "health",
        "shutdown",
    ]
    assert responses[0].result is not None
    assert responses[0].result["networkListener"] is False
    assert responses[1].result is not None
    assert responses[1].result["status"] == "ready"
    assert responses[1].result["integrity"]["status"] == "pass"
    assert responses[1].result["recovery"] == {
        "pendingJournals": 0,
        "quarantinedFiles": 0,
        "recoveredCommits": 0,
        "removedTempFiles": 0,
    }
    assert responses[2].result == {"drained": True}
    assert stderr.getvalue() == b""


def test_server_malformed_input_fails_closed_without_stdout_or_raw_diagnostic(
    tmp_path: Path,
) -> None:
    server = ArtifactRpcServer(ArtifactService(tmp_path / "artifacts"))
    stdout = BytesIO()
    stderr = BytesIO()

    exit_code = server.serve(
        BytesIO(b"\x00\x00\x00\x10raw-secret-frame"),
        stdout,
        stderr,
    )

    assert exit_code == 1
    assert stdout.getvalue() == b""
    assert b"raw-secret-frame" not in stderr.getvalue()
    assert b"ARTIFACT_RPC_PROTOCOL_MISMATCH" in stderr.getvalue()


def test_startup_reconciliation_finishes_before_first_rpc_read(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "artifacts"
    crashed = ArtifactService(root)
    artifact, revision = make_artifact_pair(b"orphan-before-admission")

    def simulate_crash(*args: object, **kwargs: object) -> None:
        raise RuntimeError("simulated process crash")

    monkeypatch.setattr(crashed.store, "_commit_create", simulate_crash)
    with pytest.raises(RuntimeError, match="simulated process crash"):
        crashed.store.create_artifact(artifact, revision, b"orphan-before-admission")
    (crashed.store.filesystem.tmp_root / "stale.tmp").write_bytes(b"stale")

    service = ArtifactService(root)

    class ObservedInput(BytesIO):
        observed = False

        def read(self, size: int = -1) -> bytes:
            raise AssertionError("buffered pipe reads must use read1")

        def read1(self, size: int = -1) -> bytes:
            if not self.observed:
                self.observed = True
                with service.store._connect() as connection:
                    state = connection.execute(
                        "SELECT state FROM artifact_write_journal WHERE revision_id = ?",
                        (revision.revision_id,),
                    ).fetchone()[0]
                assert state == "quarantined"
                assert not any(service.store.filesystem.tmp_root.rglob("*"))
            return super().read1(size)

    server = ArtifactRpcServer(service)
    stdin = ObservedInput(
        encode_frame(_request("hello", ArtifactRpcMethod.RPC_HANDSHAKE))
        + encode_frame(_request("shutdown", ArtifactRpcMethod.RPC_SHUTDOWN))
    )
    stdout = BytesIO()
    stderr = BytesIO()

    assert server.serve(stdin, stdout, stderr) == 0
    assert stdin.observed is True
    assert stderr.getvalue() == b""
