from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from imperaos.control_plane.agent_enrollment import (
    AgentEnrollmentRequest,
    AgentEnrollmentToken,
    EnrolledAgent,
    generate_raw_enrollment_token,
    hash_enrollment_token,
)

NOW = datetime(2026, 6, 19, tzinfo=UTC)
HASH = "b" * 64


def test_agent_enrollment_token_is_hash_only_and_single_use() -> None:
    token = AgentEnrollmentToken(
        tokenId="enrtok-test",
        tokenHash=HASH,
        organizationId="local-org",
        workspaceId="pilot-workspace",
        intendedAgentId="ops-agent",
        intendedDeviceLabel="ops-host-01",
        allowedPrincipalType="external_agent",
        allowedCapabilities=("read", "external_write", "read"),
        policyProfile="enterprise",
        memoryScopes=({"scope": "workspace", "mode": "read"},),
        createdByPrincipalId="principal-admin",
        createdAtUtc=NOW,
        expiresAtUtc=NOW + timedelta(minutes=15),
    )

    payload = token.model_dump(mode="json", by_alias=True)

    assert token.max_uses == 1
    assert token.approval_required is True
    assert token.allowed_capabilities == ("external_write", "read")
    assert "rawToken" not in payload
    assert "raw_token" not in payload


def test_agent_enrollment_token_rejects_invalid_hash_and_max_uses() -> None:
    with pytest.raises(ValidationError):
        AgentEnrollmentToken(
            tokenId="enrtok-test",
            tokenHash="not-a-hash",
            organizationId="local-org",
            workspaceId="pilot-workspace",
            intendedDeviceLabel="ops-host-01",
            allowedPrincipalType="external_agent",
            allowedCapabilities=("read",),
            policyProfile="enterprise",
            memoryScopes=(),
            createdByPrincipalId="principal-admin",
            createdAtUtc=NOW,
            expiresAtUtc=NOW + timedelta(minutes=15),
            maxUses=2,
        )


def test_enrollment_request_and_agent_are_hash_only() -> None:
    request = AgentEnrollmentRequest(
        requestId="enrreq-test",
        tokenId="enrtok-test",
        tokenProofHash=HASH,
        workspaceId="pilot-workspace",
        agentId="ops-agent",
        agentDisplayName="Ops Agent",
        deviceDisplayName="Ops Host 01",
        platform="linux",
        capabilities=("read", "read"),
        hostFingerprintHash=HASH,
        requestedAtUtc=NOW,
        idempotencyKey="enrollment-request-1",
    )
    enrolled = EnrolledAgent(
        enrollmentId="enr-test",
        workspaceId=request.workspace_id,
        agentId=request.agent_id,
        principalId="principal-agent",
        deviceId="device-host-01",
        tokenId=request.token_id,
        status="active",
        capabilities=request.capabilities,
        policyProfile="enterprise",
        createdAtUtc=NOW,
    )

    assert request.capabilities == ("read",)
    assert request.model_dump(by_alias=True)["tokenProofHash"] == HASH
    assert enrolled.status == "active"


def test_enrollment_token_hash_is_deterministic_and_raw_token_random() -> None:
    raw = generate_raw_enrollment_token()

    assert raw.startswith("enr_")
    assert hash_enrollment_token(raw, token_id="enrtok-test", workspace_id="pilot-workspace") == (
        hash_enrollment_token(raw, token_id="enrtok-test", workspace_id="pilot-workspace")
    )
    with pytest.raises(ValueError):
        hash_enrollment_token("", token_id="enrtok-test", workspace_id="pilot-workspace")
