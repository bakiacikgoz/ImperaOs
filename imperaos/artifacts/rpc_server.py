from __future__ import annotations

import hashlib
from collections import OrderedDict
from dataclasses import fields, is_dataclass
from datetime import datetime
from enum import Enum
from time import perf_counter
from typing import Any, BinaryIO

from pydantic import BaseModel, ValidationError

from imperaos.artifacts.commands import (
    ApplyArtifactProposalCommand,
    ArchiveArtifactCommand,
    ArtifactHistoryQuery,
    BeginArtifactExportCommand,
    CancelArtifactExportCommand,
    CommitArtifactExportCommand,
    CreateArtifactCommand,
    DuplicateArtifactCommand,
    GetArtifactAssetQuery,
    GetArtifactQuery,
    ImportArtifactAssetCommand,
    ImportEvidenceArtifactCommand,
    ListArtifactsQuery,
    MutateArtifactCommand,
    PatchArtifactSlideCommand,
    PatchSpreadsheetCellsCommand,
    PreflightArtifactExportCommand,
    ProposeArtifactMutationCommand,
    RestoreArtifactCommand,
    SubmitArtifactFormCommand,
)
from imperaos.artifacts.diagnostics import verify_artifact_integrity
from imperaos.artifacts.errors import ArtifactDomainError, ArtifactErrorCode
from imperaos.artifacts.models import OperationContext, canonical_json
from imperaos.artifacts.rpc_protocol import (
    ARTIFACT_RPC_CONTRACT_VERSION,
    ArtifactRpcMethod,
    RpcError,
    RpcFrameDecoder,
    RpcHandshake,
    RpcRequest,
    RpcResponse,
    encode_frame,
    parse_request_payload,
)
from imperaos.artifacts.runtime import build_runtime_artifact_capability_snapshot
from imperaos.artifacts.service import ArtifactService
from imperaos.artifacts.store import StorageReconciliationReport

_READ_CHUNK_BYTES = 64 * 1024
_MAX_DEDUP_RESPONSES = 1024
_MUTATION_METHODS_WITH_KEYS = {
    ArtifactRpcMethod.ARTIFACT_CREATE,
    ArtifactRpcMethod.ARTIFACT_MUTATE,
    ArtifactRpcMethod.ARTIFACT_SPREADSHEET_PATCH,
    ArtifactRpcMethod.ARTIFACT_SLIDES_PATCH,
    ArtifactRpcMethod.ARTIFACT_PROPOSE_MUTATION,
    ArtifactRpcMethod.ARTIFACT_RESTORE,
    ArtifactRpcMethod.ARTIFACT_DUPLICATE,
    ArtifactRpcMethod.ARTIFACT_ASSET_IMPORT,
    ArtifactRpcMethod.ARTIFACT_IMPORT_EVIDENCE,
    ArtifactRpcMethod.ARTIFACT_FORM_SUBMIT,
    ArtifactRpcMethod.ARTIFACT_EXPORT_BEGIN,
    ArtifactRpcMethod.ARTIFACT_EXPORT_PREFLIGHT,
    ArtifactRpcMethod.ARTIFACT_EXPORT_COMMIT,
    ArtifactRpcMethod.ARTIFACT_EXPORT_CANCEL,
}


class ArtifactRpcServer:
    """Single-process, protocol-only stdio adapter over the canonical service."""

    def __init__(self, service: ArtifactService) -> None:
        self.service = service
        self._server_sequence = 0
        self._shutdown_requested = False
        self._responses: OrderedDict[str, tuple[str, RpcResponse]] = OrderedDict()
        self._startup_reconciled = False
        self._startup_recovery_report: StorageReconciliationReport | None = None

    @property
    def shutdown_requested(self) -> bool:
        return self._shutdown_requested

    def handle_request(self, request: RpcRequest) -> RpcResponse:
        started = perf_counter()
        try:
            return self._handle_request(request)
        finally:
            self.service.operations.add(
                "imperaos_artifact_rpc_request_latency_ms",
                (perf_counter() - started) * 1_000,
                labels={"method": request.method.value},
            )

    def _handle_request(self, request: RpcRequest) -> RpcResponse:
        request_hash = hashlib.sha256(canonical_json(request).encode("utf-8")).hexdigest()
        try:
            self._ensure_startup_reconciled()
        except ArtifactDomainError as exc:
            response = self._error_response(
                request.request_id,
                exc.code,
                exc.message,
                retryable=exc.retryable,
                details=exc.details,
            )
            self._remember(request.request_id, request_hash, response)
            return response
        cached = self._responses.get(request.request_id)
        if cached is not None:
            cached_hash, cached_response = cached
            if cached_hash == request_hash:
                self._responses.move_to_end(request.request_id)
                return cached_response
            return self._error_response(
                request.request_id,
                ArtifactErrorCode.ARTIFACT_RPC_PROTOCOL_MISMATCH,
                "request ID was reused with a different payload",
            )

        if self._shutdown_requested and request.method is not ArtifactRpcMethod.RPC_SHUTDOWN:
            return self._error_response(
                request.request_id,
                ArtifactErrorCode.ARTIFACT_RPC_UNAVAILABLE,
                "artifact RPC server is shutting down",
                retryable=True,
            )
        try:
            result = self._dispatch(request)
            response = self._success_response(request.request_id, result)
        except ArtifactDomainError as exc:
            response = self._error_response(
                request.request_id,
                exc.code,
                exc.message,
                retryable=exc.retryable,
                details=exc.details,
            )
        except (ValidationError, ValueError, TypeError):
            response = self._error_response(
                request.request_id,
                ArtifactErrorCode.ARTIFACT_SCHEMA_INVALID,
                "RPC params do not match the method contract",
            )
        self._remember(request.request_id, request_hash, response)
        return response

    def serve(self, stdin: BinaryIO, stdout: BinaryIO, stderr: BinaryIO) -> int:
        decoder = RpcFrameDecoder()
        read_chunk = getattr(stdin, "read1", stdin.read)
        try:
            self._ensure_startup_reconciled()
            while not self._shutdown_requested:
                chunk = read_chunk(_READ_CHUNK_BYTES)
                if not chunk:
                    if decoder.buffered_bytes:
                        raise ArtifactDomainError(
                            ArtifactErrorCode.ARTIFACT_RPC_PROTOCOL_MISMATCH,
                            "RPC input ended with an incomplete frame",
                        )
                    return 0
                for payload in decoder.feed(chunk):
                    request = parse_request_payload(payload)
                    response = self.handle_request(request)
                    stdout.write(encode_frame(response))
                    stdout.flush()
                    if self._shutdown_requested:
                        break
            return 0
        except ArtifactDomainError as exc:
            stderr.write(f"{exc.code.value}\n".encode("ascii"))
            stderr.flush()
            return 1
        except (OSError, ValueError, TypeError):
            stderr.write(b"ARTIFACT_RPC_UNAVAILABLE\n")
            stderr.flush()
            return 1

    def _ensure_startup_reconciled(self) -> StorageReconciliationReport:
        if not self._startup_reconciled:
            report = self.service.store.reconcile_storage()
            self._startup_recovery_report = report
            self._startup_reconciled = True
        if self._startup_recovery_report is None:
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_STORAGE_CORRUPT,
                "artifact startup recovery did not produce a report",
            )
        return self._startup_recovery_report

    def shutdown(self) -> None:
        self._shutdown_requested = True

    def _dispatch(self, request: RpcRequest) -> dict[str, Any]:
        if request.method is ArtifactRpcMethod.RPC_HANDSHAKE:
            license_capabilities = self.service.license_capabilities()
            return RpcHandshake.default(
                license_capabilities,
                capability_snapshot=build_runtime_artifact_capability_snapshot(
                    self.service.feature_flags(),
                    license_capabilities={
                        capability.kind: capability.enabled
                        for capability in license_capabilities
                    },
                ),
            ).model_dump(mode="json", by_alias=True)
        if request.method is ArtifactRpcMethod.RPC_HEALTH:
            recovery = self._ensure_startup_reconciled()
            integrity = verify_artifact_integrity(self.service)
            recovered = any(
                (
                    recovery.pending_journals,
                    recovery.recovered_commits,
                    recovery.quarantined_files,
                    recovery.removed_temp_files,
                )
            )
            return {
                "status": (
                    "ready"
                    if integrity["status"] == "pass" and not recovered
                    else "degraded"
                ),
                "contractVersion": ARTIFACT_RPC_CONTRACT_VERSION,
                "accepting": not self._shutdown_requested,
                "integrity": integrity,
                "recovery": {
                    "pendingJournals": recovery.pending_journals,
                    "recoveredCommits": recovery.recovered_commits,
                    "quarantinedFiles": recovery.quarantined_files,
                    "removedTempFiles": recovery.removed_temp_files,
                },
            }
        if request.method is ArtifactRpcMethod.RPC_SHUTDOWN:
            self.shutdown()
            return {"drained": True}

        self._validate_idempotency_binding(request)
        context = OperationContext(
            workspace_id=request.workspace_id,
            principal_type=request.principal.principal_type,
            principal_id=request.principal.principal_id,
            roles=request.principal.roles,
            request_id=request.request_id,
        )
        handlers: dict[ArtifactRpcMethod, tuple[type[BaseModel], Any]] = {
            ArtifactRpcMethod.ARTIFACT_LIST: (ListArtifactsQuery, self.service.list),
            ArtifactRpcMethod.ARTIFACT_GET: (GetArtifactQuery, self.service.get),
            ArtifactRpcMethod.ARTIFACT_CREATE: (CreateArtifactCommand, self.service.create),
            ArtifactRpcMethod.ARTIFACT_MUTATE: (MutateArtifactCommand, self.service.mutate),
            ArtifactRpcMethod.ARTIFACT_SPREADSHEET_PATCH: (
                PatchSpreadsheetCellsCommand,
                self.service.patch_spreadsheet_cells,
            ),
            ArtifactRpcMethod.ARTIFACT_SLIDES_PATCH: (
                PatchArtifactSlideCommand,
                self.service.patch_artifact_slide,
            ),
            ArtifactRpcMethod.ARTIFACT_PROPOSE_MUTATION: (
                ProposeArtifactMutationCommand,
                self.service.propose_mutation,
            ),
            ArtifactRpcMethod.ARTIFACT_APPLY_PROPOSAL: (
                ApplyArtifactProposalCommand,
                self.service.apply_proposal,
            ),
            ArtifactRpcMethod.ARTIFACT_HISTORY: (
                ArtifactHistoryQuery,
                self.service.history,
            ),
            ArtifactRpcMethod.ARTIFACT_RESTORE: (
                RestoreArtifactCommand,
                self.service.restore,
            ),
            ArtifactRpcMethod.ARTIFACT_ARCHIVE: (
                ArchiveArtifactCommand,
                self.service.archive,
            ),
            ArtifactRpcMethod.ARTIFACT_DUPLICATE: (
                DuplicateArtifactCommand,
                self.service.duplicate,
            ),
            ArtifactRpcMethod.ARTIFACT_ASSET_IMPORT: (
                ImportArtifactAssetCommand,
                self.service.import_asset,
            ),
            ArtifactRpcMethod.ARTIFACT_ASSET_GET: (
                GetArtifactAssetQuery,
                self.service.get_asset,
            ),
            ArtifactRpcMethod.ARTIFACT_IMPORT_EVIDENCE: (
                ImportEvidenceArtifactCommand,
                self.service.import_evidence,
            ),
            ArtifactRpcMethod.ARTIFACT_FORM_SUBMIT: (
                SubmitArtifactFormCommand,
                self.service.submit_form,
            ),
            ArtifactRpcMethod.ARTIFACT_EXPORT_BEGIN: (
                BeginArtifactExportCommand,
                self.service.begin_export,
            ),
            ArtifactRpcMethod.ARTIFACT_EXPORT_PREFLIGHT: (
                PreflightArtifactExportCommand,
                self.service.preflight_export,
            ),
            ArtifactRpcMethod.ARTIFACT_EXPORT_COMMIT: (
                CommitArtifactExportCommand,
                self.service.commit_export,
            ),
            ArtifactRpcMethod.ARTIFACT_EXPORT_CANCEL: (
                CancelArtifactExportCommand,
                self.service.cancel_export,
            ),
        }
        route = handlers.get(request.method)
        if route is None:
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_RPC_UNAVAILABLE,
                "RPC method is not enabled in this server build",
            )
        model, handler = route
        command = model.model_validate(request.params)
        return _json_mapping(handler(command, context))

    @staticmethod
    def _validate_idempotency_binding(request: RpcRequest) -> None:
        if request.method not in _MUTATION_METHODS_WITH_KEYS:
            return
        params_key = request.params.get("idempotencyKey")
        if (
            request.idempotency_key is None
            or not isinstance(params_key, str)
            or params_key != request.idempotency_key
        ):
            raise ArtifactDomainError(
                ArtifactErrorCode.ARTIFACT_RPC_PROTOCOL_MISMATCH,
                "mutation idempotency key is missing or not envelope-bound",
            )

    def _success_response(self, request_id: str, result: dict[str, Any]) -> RpcResponse:
        return RpcResponse(
            contract_version=ARTIFACT_RPC_CONTRACT_VERSION,
            request_id=request_id,
            ok=True,
            result=result,
            server_sequence=self._next_sequence(),
        )

    def _error_response(
        self,
        request_id: str,
        code: ArtifactErrorCode,
        message: str,
        *,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> RpcResponse:
        return RpcResponse(
            contract_version=ARTIFACT_RPC_CONTRACT_VERSION,
            request_id=request_id,
            ok=False,
            error=RpcError(
                code=code.value,
                message=message,
                retryable=retryable,
                details=_json_mapping(details or {}),
            ),
            server_sequence=self._next_sequence(),
        )

    def _next_sequence(self) -> int:
        self._server_sequence += 1
        return self._server_sequence

    def _remember(self, request_id: str, request_hash: str, response: RpcResponse) -> None:
        self._responses[request_id] = (request_hash, response)
        self._responses.move_to_end(request_id)
        while len(self._responses) > _MAX_DEDUP_RESPONSES:
            self._responses.popitem(last=False)


def _json_mapping(value: object) -> dict[str, Any]:
    converted = _json_value(value)
    if not isinstance(converted, dict):
        raise TypeError("RPC result must serialize to an object")
    return converted


def _json_value(value: object) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", by_alias=True)
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _json_value(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError("RPC result contains a non-JSON value")
