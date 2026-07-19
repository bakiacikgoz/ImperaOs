from __future__ import annotations

import struct

import pytest
from pydantic import ValidationError

from imperaos.artifacts.errors import ArtifactDomainError, ArtifactErrorCode
from imperaos.artifacts.models import PrincipalType
from imperaos.artifacts.rpc_protocol import (
    ARTIFACT_RPC_CONTRACT_VERSION,
    ARTIFACT_RPC_MAX_FRAME_BYTES,
    ArtifactRpcMethod,
    RpcError,
    RpcFrameDecoder,
    RpcHandshake,
    RpcPrincipal,
    RpcRequest,
    RpcResponse,
    encode_frame,
    parse_request_payload,
)


def _request(**updates: object) -> RpcRequest:
    values: dict[str, object] = {
        "contract_version": ARTIFACT_RPC_CONTRACT_VERSION,
        "request_id": "request-1",
        "method": ArtifactRpcMethod.ARTIFACT_GET,
        "workspace_id": "workspace-1",
        "principal": RpcPrincipal(
            principal_id="user-1",
            principal_type=PrincipalType.USER,
            roles=("artifact_editor",),
        ),
        "params": {"artifactId": "artifact-1"},
    }
    values.update(updates)
    return RpcRequest.model_validate(values)


def test_rpc_envelopes_are_strict_versioned_and_response_is_exclusive() -> None:
    request = _request()

    assert request.contract_version == "1.0"
    assert request.method is ArtifactRpcMethod.ARTIFACT_GET
    with pytest.raises(ValidationError):
        RpcRequest.model_validate(
            {**request.model_dump(mode="python"), "untrustedPath": "C:/secret"}
        )
    with pytest.raises(ValidationError):
        _request(contract_version="2.0")
    with pytest.raises(ValidationError):
        RpcResponse(
            contract_version="1.0",
            request_id="request-1",
            ok=True,
            result={"value": 1},
            error=RpcError(code="BAD", message="must be exclusive"),
            server_sequence=1,
        )


def test_length_prefixed_decoder_handles_fragmented_and_coalesced_frames() -> None:
    first = encode_frame(_request(request_id="request-1"))
    second = encode_frame(_request(request_id="request-2"))
    decoder = RpcFrameDecoder()

    assert decoder.feed(first[:2]) == ()
    assert decoder.feed(first[2:9]) == ()
    decoded = decoder.feed(first[9:] + second)

    assert [parse_request_payload(payload).request_id for payload in decoded] == [
        "request-1",
        "request-2",
    ]
    assert decoder.buffered_bytes == 0


def test_oversized_and_malformed_frames_fail_closed_without_raw_payload() -> None:
    decoder = RpcFrameDecoder()
    with pytest.raises(ArtifactDomainError) as oversized:
        decoder.feed(struct.pack(">I", ARTIFACT_RPC_MAX_FRAME_BYTES + 1))
    assert oversized.value.code is ArtifactErrorCode.ARTIFACT_RPC_PROTOCOL_MISMATCH

    marker = b"raw-secret-frame-marker"
    with pytest.raises(ArtifactDomainError) as malformed:
        parse_request_payload(b'{"broken":"' + marker)
    assert malformed.value.code is ArtifactErrorCode.ARTIFACT_RPC_PROTOCOL_MISMATCH
    assert marker.decode() not in str(malformed.value)


def test_handshake_publishes_bounded_protocol_and_control_capabilities() -> None:
    handshake = RpcHandshake.default()

    assert handshake.contract_version == ARTIFACT_RPC_CONTRACT_VERSION
    assert handshake.max_frame_bytes == ARTIFACT_RPC_MAX_FRAME_BYTES
    assert ArtifactRpcMethod.RPC_HANDSHAKE in handshake.methods
    assert ArtifactRpcMethod.RPC_HEALTH in handshake.methods
    assert ArtifactRpcMethod.RPC_SHUTDOWN in handshake.methods
    assert handshake.transport == "stdio-length-prefixed-json"
    assert handshake.network_listener is False
