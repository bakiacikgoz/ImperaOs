from __future__ import annotations

import struct
from enum import StrEnum
from typing import Literal

from pydantic import Field, JsonValue, model_validator

from imperaos.artifacts.errors import ArtifactDomainError, ArtifactErrorCode
from imperaos.artifacts.licenses import ArtifactLicenseCapability
from imperaos.artifacts.models import (
    ArtifactModel,
    BoundedId,
    PrincipalType,
    canonical_json,
)
from imperaos.artifacts.runtime import (
    ArtifactRuntimeCapabilitySnapshot,
    build_runtime_artifact_capability_snapshot,
)

ARTIFACT_RPC_CONTRACT_VERSION = "1.0"
ARTIFACT_RPC_MAX_FRAME_BYTES = 32 * 1024 * 1024
_FRAME_HEADER_BYTES = 4


class ArtifactRpcMethod(StrEnum):
    RPC_HANDSHAKE = "rpc.handshake"
    RPC_HEALTH = "rpc.health"
    RPC_SHUTDOWN = "rpc.shutdown"
    PROJECT_LIST = "project.list"
    PROJECT_CREATE = "project.create"
    PROJECT_REGISTER = "project.register"
    PROJECT_UPDATE = "project.update"
    PROJECT_ARCHIVE = "project.archive"
    TASK_GET = "task.get"
    TASK_LIST = "task.list"
    TASK_CREATE = "task.create"
    TASK_UPDATE = "task.update"
    TASK_ARCHIVE = "task.archive"
    TASK_MESSAGE_ADD = "task.message.add"
    TASK_MESSAGE_LIST = "task.message.list"
    TASK_LINK_ADD = "task.link.add"
    TASK_LINK_LIST = "task.link.list"
    PREFERENCES_GET = "preferences.get"
    PREFERENCES_SET = "preferences.set"
    ARTIFACT_LIST = "artifact.list"
    ARTIFACT_GET = "artifact.get"
    ARTIFACT_CREATE = "artifact.create"
    ARTIFACT_MUTATE = "artifact.mutate"
    ARTIFACT_SPREADSHEET_PATCH = "artifact.spreadsheet.patch"
    ARTIFACT_SLIDES_PATCH = "artifact.slides.patch"
    ARTIFACT_PROPOSE_MUTATION = "artifact.propose_mutation"
    ARTIFACT_APPLY_PROPOSAL = "artifact.apply_proposal"
    ARTIFACT_HISTORY = "artifact.history"
    ARTIFACT_RESTORE = "artifact.restore"
    ARTIFACT_ARCHIVE = "artifact.archive"
    ARTIFACT_DUPLICATE = "artifact.duplicate"
    ARTIFACT_ASSET_IMPORT = "artifact.asset.import"
    ARTIFACT_ASSET_GET = "artifact.asset.get"
    ARTIFACT_FORM_SUBMIT = "artifact.form.submit"
    ARTIFACT_EXPORT_BEGIN = "artifact.export.begin"
    ARTIFACT_EXPORT_PREFLIGHT = "artifact.export.preflight"
    ARTIFACT_EXPORT_COMMIT = "artifact.export.commit"
    ARTIFACT_EXPORT_CANCEL = "artifact.export.cancel"
    ARTIFACT_IMPORT_EVIDENCE = "artifact.import_evidence"


class RpcPrincipal(ArtifactModel):
    principal_id: BoundedId
    principal_type: PrincipalType = Field(strict=False)
    roles: tuple[BoundedId, ...] = Field(default_factory=tuple, max_length=64)


class RpcRequest(ArtifactModel):
    contract_version: Literal["1.0"]
    request_id: BoundedId
    method: ArtifactRpcMethod = Field(strict=False)
    workspace_id: BoundedId
    principal: RpcPrincipal
    idempotency_key: BoundedId | None = None
    deadline_ms: int | None = Field(default=None, ge=1, le=120_000)
    params: dict[str, JsonValue] = Field(default_factory=dict)


class RpcError(ArtifactModel):
    code: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=500)
    retryable: bool = False
    details: dict[str, JsonValue] = Field(default_factory=dict)


class RpcResponse(ArtifactModel):
    contract_version: Literal["1.0"]
    request_id: BoundedId
    ok: bool
    result: dict[str, JsonValue] | None = None
    error: RpcError | None = None
    server_sequence: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_outcome(self) -> RpcResponse:
        if self.ok and (self.result is None or self.error is not None):
            raise ValueError("successful RPC responses require result only")
        if not self.ok and (self.error is None or self.result is not None):
            raise ValueError("failed RPC responses require error only")
        return self


class RpcHandshake(ArtifactModel):
    contract_version: Literal["1.0"]
    transport: Literal["stdio-length-prefixed-json"]
    max_frame_bytes: int = Field(ge=1024, le=ARTIFACT_RPC_MAX_FRAME_BYTES)
    methods: tuple[ArtifactRpcMethod, ...]
    network_listener: Literal[False]
    stdout_protocol_only: Literal[True]
    graceful_shutdown: Literal[True]
    license_capabilities: tuple[ArtifactLicenseCapability, ...]
    capability_snapshot: ArtifactRuntimeCapabilitySnapshot

    @classmethod
    def default(
        cls,
        license_capabilities: tuple[ArtifactLicenseCapability, ...] | None = None,
        capability_snapshot: dict[str, object] | None = None,
    ) -> RpcHandshake:
        resolved_licenses = license_capabilities or (
            ArtifactLicenseCapability(
                kind="spreadsheet",
                enabled=False,
                reason_code="ARTIFACT_LICENSE_EVIDENCE_MISSING",
            ),
            ArtifactLicenseCapability(
                kind="canvas",
                enabled=False,
                reason_code="ARTIFACT_LICENSE_EVIDENCE_MISSING",
            ),
        )
        return cls(
            contract_version=ARTIFACT_RPC_CONTRACT_VERSION,
            transport="stdio-length-prefixed-json",
            max_frame_bytes=ARTIFACT_RPC_MAX_FRAME_BYTES,
            methods=tuple(ArtifactRpcMethod),
            network_listener=False,
            stdout_protocol_only=True,
            graceful_shutdown=True,
            license_capabilities=resolved_licenses,
            capability_snapshot=capability_snapshot
            or build_runtime_artifact_capability_snapshot(
                None,
                license_capabilities={
                    capability.kind: capability.enabled for capability in resolved_licenses
                },
            ),
        )


def encode_frame(
    message: ArtifactModel | dict[str, JsonValue],
    *,
    max_frame_bytes: int = ARTIFACT_RPC_MAX_FRAME_BYTES,
) -> bytes:
    payload = canonical_json(message).encode("utf-8")
    if not payload or len(payload) > max_frame_bytes:
        _raise_protocol_mismatch("RPC frame size is outside the allowed boundary")
    return struct.pack(">I", len(payload)) + payload


def parse_request_payload(payload: bytes) -> RpcRequest:
    if not payload or len(payload) > ARTIFACT_RPC_MAX_FRAME_BYTES:
        _raise_protocol_mismatch("RPC request frame size is invalid")
    try:
        return RpcRequest.model_validate_json(payload, strict=True)
    except (ValueError, TypeError) as exc:
        raise ArtifactDomainError(
            ArtifactErrorCode.ARTIFACT_RPC_PROTOCOL_MISMATCH,
            "RPC request does not match the versioned protocol",
        ) from exc


class RpcFrameDecoder:
    def __init__(self, *, max_frame_bytes: int = ARTIFACT_RPC_MAX_FRAME_BYTES) -> None:
        if max_frame_bytes < 1024 or max_frame_bytes > ARTIFACT_RPC_MAX_FRAME_BYTES:
            raise ValueError("max_frame_bytes is outside the supported boundary")
        self.max_frame_bytes = max_frame_bytes
        self._buffer = bytearray()

    @property
    def buffered_bytes(self) -> int:
        return len(self._buffer)

    def feed(self, chunk: bytes) -> tuple[bytes, ...]:
        if not isinstance(chunk, bytes):
            raise TypeError("RPC decoder accepts bytes only")
        self._buffer.extend(chunk)
        frames: list[bytes] = []
        while len(self._buffer) >= _FRAME_HEADER_BYTES:
            payload_size = struct.unpack(">I", self._buffer[:_FRAME_HEADER_BYTES])[0]
            if payload_size == 0 or payload_size > self.max_frame_bytes:
                self._buffer.clear()
                _raise_protocol_mismatch("RPC frame length prefix is invalid")
            frame_size = _FRAME_HEADER_BYTES + payload_size
            if len(self._buffer) < frame_size:
                break
            frames.append(bytes(self._buffer[_FRAME_HEADER_BYTES:frame_size]))
            del self._buffer[:frame_size]
        if len(self._buffer) > self.max_frame_bytes + _FRAME_HEADER_BYTES:
            self._buffer.clear()
            _raise_protocol_mismatch("RPC decoder buffer exceeded its boundary")
        return tuple(frames)


def _raise_protocol_mismatch(message: str) -> None:
    raise ArtifactDomainError(
        ArtifactErrorCode.ARTIFACT_RPC_PROTOCOL_MISMATCH,
        message,
    )
