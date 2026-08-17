from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from imperaos.control_plane.enterprise_workspace import (
    SHA256_HEX_RE,
    EnterpriseDevice,
    EnterprisePrincipal,
    StrictModel,
    _validate_optional_hash,
    _validate_safe_id,
    hash_identity_ref,
    sha256_text,
    stable_id,
    utc_now,
)
from imperaos.runtime.paths import CONTROL_PLANE_STATE_ROOT


class EnrollmentMemoryScope(StrictModel):
    scope: str = Field(min_length=1, max_length=80)
    mode: Literal["read", "write", "proposal_only", "requires_approval"]


class AgentEnrollmentToken(StrictModel):
    schema_version: Literal["agent-enrollment-token/v1"] = Field(
        default="agent-enrollment-token/v1",
        alias="schemaVersion",
    )
    token_id: str = Field(alias="tokenId")
    token_hash: str = Field(alias="tokenHash")
    organization_id: str = Field(alias="organizationId")
    workspace_id: str = Field(alias="workspaceId")
    intended_agent_id: str | None = Field(default=None, alias="intendedAgentId")
    intended_device_label: str = Field(alias="intendedDeviceLabel", min_length=1, max_length=160)
    allowed_principal_type: Literal["service_agent", "external_agent"] = Field(
        alias="allowedPrincipalType"
    )
    allowed_capabilities: tuple[str, ...] = Field(alias="allowedCapabilities")
    policy_profile: str = Field(alias="policyProfile", min_length=1)
    memory_scopes: tuple[EnrollmentMemoryScope, ...] = Field(
        default_factory=tuple,
        alias="memoryScopes",
    )
    created_by_principal_id: str = Field(alias="createdByPrincipalId")
    created_at_utc: datetime = Field(alias="createdAtUtc")
    expires_at_utc: datetime = Field(alias="expiresAtUtc")
    max_uses: Literal[1] = Field(default=1, alias="maxUses")
    use_count: int = Field(default=0, ge=0, le=1, alias="useCount")
    status: Literal["active", "used", "revoked", "expired"] = "active"
    approval_required: Literal[True] = Field(default=True, alias="approvalRequired")

    @field_validator(
        "token_id",
        "organization_id",
        "workspace_id",
        "intended_agent_id",
        "created_by_principal_id",
    )
    @classmethod
    def _safe_ids(cls, value: str | None, info: object) -> str | None:
        if value is None:
            return None
        return _validate_safe_id(value, str(getattr(info, "field_name", "id")))

    @field_validator("token_hash")
    @classmethod
    def _token_hash(cls, value: str) -> str:
        if not SHA256_HEX_RE.fullmatch(value):
            raise ValueError("token_hash must be sha256 hex")
        return value

    @field_validator("allowed_capabilities")
    @classmethod
    def _capabilities(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        capabilities = tuple(sorted(set(value)))
        if not capabilities:
            raise ValueError("allowed_capabilities cannot be empty")
        for capability in capabilities:
            _validate_safe_id(capability, "capability")
        return capabilities


class AgentEnrollmentTokenCreateRequest(StrictModel):
    workspace_id: str = Field(alias="workspaceId")
    intended_agent_id: str | None = Field(default=None, alias="intendedAgentId")
    intended_device_label: str = Field(alias="intendedDeviceLabel", min_length=1, max_length=160)
    allowed_principal_type: Literal["service_agent", "external_agent"] = Field(
        default="external_agent",
        alias="allowedPrincipalType",
    )
    allowed_capabilities: tuple[str, ...] = Field(alias="allowedCapabilities")
    ttl_minutes: int = Field(default=15, ge=1, le=1440, alias="ttlMinutes")


class AgentEnrollmentTokenCreateResult(StrictModel):
    schema_version: Literal["agent-enrollment-token-create-result/v1"] = Field(
        default="agent-enrollment-token-create-result/v1",
        alias="schemaVersion",
    )
    status: Literal["created", "blocked"]
    token_id: str | None = Field(default=None, alias="tokenId")
    raw_token: str | None = Field(default=None, alias="rawToken")
    expires_at_utc: datetime | None = Field(default=None, alias="expiresAtUtc")
    evidence_ref: str | None = Field(default=None, alias="evidenceRef")
    raw_token_shown_once: bool = Field(default=False, alias="rawTokenShownOnce")
    raw_token_persisted: Literal[False] = Field(default=False, alias="rawTokenPersisted")
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")


class AgentEnrollmentTokenRevokeResult(StrictModel):
    schema_version: Literal["agent-enrollment-token-revoke-result/v1"] = Field(
        default="agent-enrollment-token-revoke-result/v1",
        alias="schemaVersion",
    )
    status: Literal["revoked", "unchanged", "blocked"]
    token_id: str = Field(alias="tokenId")
    evidence_ref: str | None = Field(default=None, alias="evidenceRef")
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")


class AgentEnrollmentRequest(StrictModel):
    schema_version: Literal["agent-enrollment-request/v1"] = Field(
        default="agent-enrollment-request/v1",
        alias="schemaVersion",
    )
    request_id: str = Field(alias="requestId")
    token_id: str = Field(alias="tokenId")
    token_proof_hash: str = Field(alias="tokenProofHash")
    workspace_id: str = Field(alias="workspaceId")
    agent_id: str = Field(alias="agentId")
    agent_display_name: str = Field(alias="agentDisplayName", min_length=1, max_length=160)
    device_display_name: str = Field(alias="deviceDisplayName", min_length=1, max_length=160)
    platform: Literal["linux", "macos", "windows", "unknown"]
    capabilities: tuple[str, ...]
    host_fingerprint_hash: str | None = Field(default=None, alias="hostFingerprintHash")
    requested_at_utc: datetime = Field(alias="requestedAtUtc")
    status: Literal["pending_approval", "approved", "rejected", "expired"] = "pending_approval"
    idempotency_key: str = Field(alias="idempotencyKey", min_length=8, max_length=160)

    @field_validator("request_id", "token_id", "workspace_id", "agent_id")
    @classmethod
    def _safe_ids(cls, value: str, info: object) -> str:
        return _validate_safe_id(value, str(getattr(info, "field_name", "id")))

    @field_validator("token_proof_hash")
    @classmethod
    def _proof_hash(cls, value: str) -> str:
        if not SHA256_HEX_RE.fullmatch(value):
            raise ValueError("token_proof_hash must be sha256 hex")
        return value

    @field_validator("host_fingerprint_hash")
    @classmethod
    def _host_hash(cls, value: str | None) -> str | None:
        return _validate_optional_hash(value, "host_fingerprint_hash")

    @field_validator("capabilities")
    @classmethod
    def _capabilities(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        capabilities = tuple(sorted(set(value)))
        if not capabilities:
            raise ValueError("capabilities cannot be empty")
        for capability in capabilities:
            _validate_safe_id(capability, "capability")
        return capabilities


class AgentEnrollmentImportResult(StrictModel):
    schema_version: Literal["agent-enrollment-import-result/v1"] = Field(
        default="agent-enrollment-import-result/v1",
        alias="schemaVersion",
    )
    status: Literal["imported", "unchanged", "blocked"]
    request_id: str | None = Field(default=None, alias="requestId")
    evidence_ref: str | None = Field(default=None, alias="evidenceRef")
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")


class AgentEnrollmentDecision(StrictModel):
    schema_version: Literal["agent-enrollment-decision/v1"] = Field(
        default="agent-enrollment-decision/v1",
        alias="schemaVersion",
    )
    status: Literal["approved", "rejected", "unchanged", "blocked"]
    request_id: str = Field(alias="requestId")
    enrollment_id: str | None = Field(default=None, alias="enrollmentId")
    device_id: str | None = Field(default=None, alias="deviceId")
    principal_id: str | None = Field(default=None, alias="principalId")
    evidence_ref: str | None = Field(default=None, alias="evidenceRef")
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")


class EnrolledAgent(StrictModel):
    schema_version: Literal["enrolled-agent/v1"] = Field(
        default="enrolled-agent/v1",
        alias="schemaVersion",
    )
    enrollment_id: str = Field(alias="enrollmentId")
    workspace_id: str = Field(alias="workspaceId")
    agent_id: str = Field(alias="agentId")
    principal_id: str = Field(alias="principalId")
    device_id: str = Field(alias="deviceId")
    token_id: str = Field(alias="tokenId")
    status: Literal["pending_approval", "active", "suspended", "revoked"]
    capabilities: tuple[str, ...]
    policy_profile: str = Field(alias="policyProfile", min_length=1)
    created_at_utc: datetime = Field(alias="createdAtUtc")
    last_seen_at_utc: datetime | None = Field(default=None, alias="lastSeenAtUtc")

    @field_validator(
        "enrollment_id",
        "workspace_id",
        "agent_id",
        "principal_id",
        "device_id",
        "token_id",
    )
    @classmethod
    def _safe_ids(cls, value: str, info: object) -> str:
        return _validate_safe_id(value, str(getattr(info, "field_name", "id")))

    @field_validator("capabilities")
    @classmethod
    def _capabilities(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        capabilities = tuple(sorted(set(value)))
        if not capabilities:
            raise ValueError("capabilities cannot be empty")
        return capabilities


def generate_raw_enrollment_token() -> str:
    return f"enr_{secrets.token_urlsafe(32)}"


def generate_bound_raw_enrollment_token(*, token_id: str, workspace_id: str) -> str:
    return f"enr_{token_id}_{workspace_id}_{secrets.token_urlsafe(32)}"


def hash_enrollment_token(raw_token: str, *, token_id: str, workspace_id: str) -> str:
    normalized = raw_token.strip()
    if not normalized:
        raise ValueError("raw token cannot be empty")
    return sha256_text(f"{workspace_id}|{token_id}|{normalized}")


def token_proof_hash(raw_token: str, *, token_id: str, workspace_id: str) -> str:
    return sha256_text(f"proof|{workspace_id}|{token_id}|{raw_token.strip()}")


class AgentEnrollmentRequestCreateResult(StrictModel):
    schema_version: Literal["agent-enrollment-request-create-result/v1"] = Field(
        default="agent-enrollment-request-create-result/v1",
        alias="schemaVersion",
    )
    status: Literal["created", "blocked"]
    request: AgentEnrollmentRequest | None = None
    output_path: str | None = Field(default=None, alias="outputPath")
    raw_token_persisted: Literal[False] = Field(default=False, alias="rawTokenPersisted")
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")

    @model_validator(mode="after")
    def _created_requires_request(self) -> AgentEnrollmentRequestCreateResult:
        if self.status == "created" and self.request is None:
            raise ValueError("created result requires request")
        return self


class EnterpriseEnrollmentError(RuntimeError):
    def __init__(self, error_code: str, message: str):
        super().__init__(message)
        self.error_code = error_code


def create_enrollment_token(
    *,
    config: Any,
    actor: Any,
    request: AgentEnrollmentTokenCreateRequest,
    root_dir: str | Path = CONTROL_PLANE_STATE_ROOT,
) -> AgentEnrollmentTokenCreateResult:
    from imperaos.control_plane.enterprise_rbac import check_roles_for_permission
    from imperaos.control_plane.enterprise_workspace_store import EnterpriseWorkspaceStore

    store = EnterpriseWorkspaceStore(root_dir)
    decision = check_roles_for_permission(
        _roles_for_actor(store=store, actor=actor, workspace_id=request.workspace_id),
        "agent.enrollment.create",
    )
    if not decision.allowed:
        return AgentEnrollmentTokenCreateResult(
            status="blocked",
            blockingReasons=[decision.reason_code],
        )
    workspace = store.get_workspace(request.workspace_id)
    organization = store.get_organization()
    if workspace is None or organization is None:
        return AgentEnrollmentTokenCreateResult(
            status="blocked",
            blockingReasons=["ENTERPRISE_WORKSPACE_SETUP_REQUIRED"],
        )
    now = utc_now()
    token_id = stable_id(
        "enrtok",
        request.workspace_id,
        request.intended_agent_id or request.intended_device_label,
        secrets.token_hex(8),
    )
    raw_token = generate_bound_raw_enrollment_token(
        token_id=token_id,
        workspace_id=request.workspace_id,
    )
    token = AgentEnrollmentToken(
        tokenId=token_id,
        tokenHash=hash_enrollment_token(
            raw_token,
            token_id=token_id,
            workspace_id=request.workspace_id,
        ),
        organizationId=organization.organization_id,
        workspaceId=request.workspace_id,
        intendedAgentId=request.intended_agent_id,
        intendedDeviceLabel=request.intended_device_label,
        allowedPrincipalType=request.allowed_principal_type,
        allowedCapabilities=request.allowed_capabilities,
        policyProfile=workspace.provider_policy_profile,
        memoryScopes=(),
        createdByPrincipalId=_principal_id_for_actor(actor),
        createdAtUtc=now,
        expiresAtUtc=now + timedelta(minutes=request.ttl_minutes),
    )
    write = store.write_enrollment_token(token)
    if write.status == "conflict":
        return AgentEnrollmentTokenCreateResult(
            status="blocked",
            blockingReasons=["TOKEN_ID_CONFLICT"],
        )
    evidence_ref = store.write_evidence_event(
        event_type="agent_enrollment_token_created",
        payload={
            "tokenId": token.token_id,
            "tokenHash": token.token_hash,
            "workspaceId": token.workspace_id,
            "agentId": token.intended_agent_id,
            "actorIdHash": hash_identity_ref(str(actor.actor_id)),
        },
    )
    return AgentEnrollmentTokenCreateResult(
        status="created",
        tokenId=token.token_id,
        rawToken=raw_token,
        expiresAtUtc=token.expires_at_utc,
        evidenceRef=evidence_ref,
        rawTokenShownOnce=True,
        rawTokenPersisted=False,
    )


def revoke_enrollment_token(
    *,
    config: Any,
    actor: Any,
    token_id: str,
    reason: str,
    root_dir: str | Path = CONTROL_PLANE_STATE_ROOT,
) -> AgentEnrollmentTokenRevokeResult:
    del config
    from imperaos.control_plane.enterprise_rbac import check_roles_for_permission
    from imperaos.control_plane.enterprise_workspace_store import EnterpriseWorkspaceStore

    store = EnterpriseWorkspaceStore(root_dir)
    token = store.get_enrollment_token(token_id)
    if token is None:
        return AgentEnrollmentTokenRevokeResult(
            status="blocked",
            tokenId=token_id,
            blockingReasons=["TOKEN_NOT_FOUND"],
        )
    decision = check_roles_for_permission(
        _roles_for_actor(store=store, actor=actor, workspace_id=token.workspace_id),
        "agent.enrollment.revoke",
    )
    if not decision.allowed:
        return AgentEnrollmentTokenRevokeResult(
            status="blocked",
            tokenId=token_id,
            blockingReasons=[decision.reason_code],
        )
    if token.status == "revoked":
        return AgentEnrollmentTokenRevokeResult(status="unchanged", tokenId=token_id)
    updated = token.model_copy(update={"status": "revoked"})
    store.write_enrollment_token(updated)
    evidence_ref = store.write_evidence_event(
        event_type="agent_enrollment_token_revoked",
        payload={
            "tokenId": token_id,
            "workspaceId": token.workspace_id,
            "reasonHash": sha256_text(reason),
            "actorIdHash": hash_identity_ref(str(actor.actor_id)),
        },
    )
    return AgentEnrollmentTokenRevokeResult(
        status="revoked",
        tokenId=token_id,
        evidenceRef=evidence_ref,
    )


def create_enrollment_request_from_token(
    *,
    raw_token: str,
    agent_id: str,
    agent_display_name: str,
    device_display_name: str,
    platform: str,
    capabilities: list[str],
    output_path: Path | None = None,
) -> AgentEnrollmentRequestCreateResult:
    token_id, workspace_id = _parse_raw_enrollment_token(raw_token)
    request = AgentEnrollmentRequest(
        requestId=stable_id("enrreq", token_id, agent_id, device_display_name),
        tokenId=token_id,
        tokenProofHash=hash_enrollment_token(
            raw_token,
            token_id=token_id,
            workspace_id=workspace_id,
        ),
        workspaceId=workspace_id,
        agentId=agent_id,
        agentDisplayName=agent_display_name,
        deviceDisplayName=device_display_name,
        platform=platform,
        capabilities=tuple(capabilities),
        hostFingerprintHash=None,
        requestedAtUtc=utc_now(),
        idempotencyKey=stable_id("enrollment-request", token_id, agent_id),
    )
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(
                request.model_dump(mode="json", by_alias=True),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    return AgentEnrollmentRequestCreateResult(
        status="created",
        request=request,
        outputPath=str(output_path) if output_path else None,
        rawTokenPersisted=False,
    )


def import_enrollment_request(
    *,
    config: Any,
    actor: Any,
    request: AgentEnrollmentRequest,
    root_dir: str | Path = CONTROL_PLANE_STATE_ROOT,
) -> AgentEnrollmentImportResult:
    del config
    from imperaos.control_plane.enterprise_rbac import check_roles_for_permission
    from imperaos.control_plane.enterprise_workspace_store import EnterpriseWorkspaceStore

    store = EnterpriseWorkspaceStore(root_dir)
    decision = check_roles_for_permission(
        _roles_for_actor(store=store, actor=actor, workspace_id=request.workspace_id),
        "agent.enrollment.import",
    )
    if not decision.allowed:
        return AgentEnrollmentImportResult(
            status="blocked",
            requestId=request.request_id,
            blockingReasons=[decision.reason_code],
        )
    token = store.get_enrollment_token(request.token_id)
    blocking_reason = _token_blocking_reason(token, request=request)
    if blocking_reason is not None:
        return AgentEnrollmentImportResult(
            status="blocked",
            requestId=request.request_id,
            blockingReasons=[blocking_reason],
        )
    write = store.write_enrollment_request(request)
    evidence_ref = store.write_evidence_event(
        event_type="agent_enrollment_request_imported",
        payload={
            "requestId": request.request_id,
            "tokenId": request.token_id,
            "workspaceId": request.workspace_id,
            "requestHash": sha256_text(request.model_dump_json(by_alias=True)),
            "actorIdHash": hash_identity_ref(str(actor.actor_id)),
        },
    )
    return AgentEnrollmentImportResult(
        status="imported" if write.status == "written" else "unchanged",
        requestId=request.request_id,
        evidenceRef=evidence_ref,
    )


def approve_enrollment_request(
    *,
    config: Any,
    actor: Any,
    request_id: str,
    root_dir: str | Path = CONTROL_PLANE_STATE_ROOT,
) -> AgentEnrollmentDecision:
    del config
    from imperaos.control_plane.enterprise_rbac import check_roles_for_permission
    from imperaos.control_plane.enterprise_workspace_store import EnterpriseWorkspaceStore

    store = EnterpriseWorkspaceStore(root_dir)
    request = store.get_enrollment_request(request_id)
    if request is None:
        return AgentEnrollmentDecision(
            status="blocked",
            requestId=request_id,
            blockingReasons=["REQUEST_NOT_FOUND"],
        )
    decision = check_roles_for_permission(
        _roles_for_actor(store=store, actor=actor, workspace_id=request.workspace_id),
        "agent.enrollment.approve",
    )
    if not decision.allowed:
        return AgentEnrollmentDecision(
            status="blocked",
            requestId=request_id,
            blockingReasons=[decision.reason_code],
        )
    token = store.get_enrollment_token(request.token_id)
    blocking_reason = _token_blocking_reason(token, request=request)
    if blocking_reason is not None:
        return AgentEnrollmentDecision(
            status="blocked",
            requestId=request_id,
            blockingReasons=[blocking_reason],
        )
    agent_principal = EnterprisePrincipal(
        principalId=stable_id("principal", request.workspace_id, request.agent_id),
        principalType=token.allowed_principal_type,
        displayName=request.agent_display_name,
        status="active",
        externalSubjectRefHash=hash_identity_ref(request.agent_id),
        issuerHash=hash_identity_ref("agent-enrollment"),
        createdAtUtc=utc_now(),
        lastSeenAtUtc=None,
    )
    device_principal = EnterprisePrincipal(
        principalId=stable_id("principal", request.workspace_id, request.device_display_name),
        principalType="device_host",
        displayName=request.device_display_name,
        status="active",
        externalSubjectRefHash=hash_identity_ref(request.device_display_name),
        issuerHash=hash_identity_ref("agent-enrollment"),
        createdAtUtc=utc_now(),
        lastSeenAtUtc=None,
    )
    device = EnterpriseDevice(
        deviceId=stable_id("device", request.workspace_id, request.device_display_name),
        workspaceId=request.workspace_id,
        principalId=device_principal.principal_id,
        displayName=request.device_display_name,
        platform=request.platform,
        hostFingerprintHash=request.host_fingerprint_hash,
        status="active",
        createdAtUtc=utc_now(),
    )
    enrollment = EnrolledAgent(
        enrollmentId=stable_id("enr", request.workspace_id, request.agent_id),
        workspaceId=request.workspace_id,
        agentId=request.agent_id,
        principalId=agent_principal.principal_id,
        deviceId=device.device_id,
        tokenId=request.token_id,
        status="active",
        capabilities=request.capabilities,
        policyProfile=token.policy_profile,
        createdAtUtc=utc_now(),
    )
    store.write_principal(agent_principal)
    store.write_principal(device_principal)
    store.write_device(device)
    store.write_enrolled_agent(enrollment)
    store.write_enrollment_token(token.model_copy(update={"status": "used", "use_count": 1}))
    store.write_enrollment_request(request.model_copy(update={"status": "approved"}))
    evidence_ref = store.write_evidence_event(
        event_type="agent_enrollment_approved",
        payload={
            "requestId": request.request_id,
            "tokenId": request.token_id,
            "workspaceId": request.workspace_id,
            "agentId": request.agent_id,
            "deviceId": device.device_id,
            "enrollmentId": enrollment.enrollment_id,
            "actorIdHash": hash_identity_ref(str(actor.actor_id)),
        },
    )
    return AgentEnrollmentDecision(
        status="approved",
        requestId=request.request_id,
        enrollmentId=enrollment.enrollment_id,
        deviceId=device.device_id,
        principalId=agent_principal.principal_id,
        evidenceRef=evidence_ref,
    )


def reject_enrollment_request(
    *,
    config: Any,
    actor: Any,
    request_id: str,
    reason: str,
    root_dir: str | Path = CONTROL_PLANE_STATE_ROOT,
) -> AgentEnrollmentDecision:
    del config
    from imperaos.control_plane.enterprise_workspace_store import EnterpriseWorkspaceStore

    store = EnterpriseWorkspaceStore(root_dir)
    request = store.get_enrollment_request(request_id)
    if request is None:
        return AgentEnrollmentDecision(
            status="blocked",
            requestId=request_id,
            blockingReasons=["REQUEST_NOT_FOUND"],
        )
    store.write_enrollment_request(request.model_copy(update={"status": "rejected"}))
    evidence_ref = store.write_evidence_event(
        event_type="agent_enrollment_rejected",
        payload={
            "requestId": request_id,
            "reasonHash": sha256_text(reason),
            "actorIdHash": hash_identity_ref(str(actor.actor_id)),
        },
    )
    return AgentEnrollmentDecision(
        status="rejected",
        requestId=request_id,
        evidenceRef=evidence_ref,
    )


def require_active_enrollment(
    *,
    agent_id: str,
    workspace_id: str | None = None,
    root_dir: str | Path = CONTROL_PLANE_STATE_ROOT,
) -> EnrolledAgent:
    from imperaos.control_plane.enterprise_workspace_store import EnterpriseWorkspaceStore

    store = EnterpriseWorkspaceStore(root_dir)
    enrollment = store.get_enrolled_agent_by_agent_id(agent_id, workspace_id=workspace_id)
    if enrollment is None:
        raise EnterpriseEnrollmentError("AGENT_NOT_ENROLLED", f"agent '{agent_id}' is not enrolled")
    if enrollment.status == "revoked":
        raise EnterpriseEnrollmentError("ENROLLMENT_REVOKED", "enrollment is revoked")
    if enrollment.status != "active":
        raise EnterpriseEnrollmentError("AGENT_NOT_ENROLLED", "enrollment is not active")
    device = store.get_device(enrollment.device_id)
    if device is not None and device.status in {"suspended", "revoked"}:
        raise EnterpriseEnrollmentError("DEVICE_SUSPENDED", "device is not active")
    principal = store.get_principal(enrollment.principal_id)
    if principal is not None and principal.status in {"disabled", "revoked"}:
        raise EnterpriseEnrollmentError("PRINCIPAL_REVOKED", "principal is not active")
    return enrollment


def _principal_id_for_actor(actor: Any) -> str:
    return stable_id("principal", str(actor.actor_id))


def _roles_for_actor(*, store: Any, actor: Any, workspace_id: str) -> tuple[str, ...]:
    principal_id = _principal_id_for_actor(actor)
    roles: list[str] = []
    for membership in store.list_memberships(workspace_id=workspace_id, principal_id=principal_id):
        if membership.status == "active":
            roles.extend(membership.roles)
    return tuple(sorted(set(roles)))


def _parse_raw_enrollment_token(raw_token: str) -> tuple[str, str]:
    parts = raw_token.split("_", 3)
    if len(parts) != 4 or parts[0] != "enr":
        raise ValueError("invalid enrollment token format")
    return parts[1], parts[2]


def _token_blocking_reason(
    token: AgentEnrollmentToken | None,
    *,
    request: AgentEnrollmentRequest,
) -> str | None:
    if token is None:
        return "TOKEN_NOT_FOUND"
    if token.status == "revoked":
        return "TOKEN_REVOKED"
    if token.status == "used" or token.use_count >= token.max_uses:
        return "TOKEN_ALREADY_USED"
    if token.status == "expired" or token.expires_at_utc < datetime.now(UTC):
        return "TOKEN_EXPIRED"
    if token.workspace_id != request.workspace_id:
        return "WORKSPACE_TOKEN_MISMATCH"
    if request.token_proof_hash != token.token_hash:
        return "TOKEN_PROOF_MISMATCH"
    if not set(request.capabilities).issubset(set(token.allowed_capabilities)):
        return "CAPABILITY_NOT_ALLOWED"
    return None
