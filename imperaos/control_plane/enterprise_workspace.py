from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from imperaos.runtime.paths import CONTROL_PLANE_STATE_ROOT

SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{1,127}$")
SHA256_HEX_RE = re.compile(r"^[a-f0-9]{64}$")


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        use_enum_values=True,
    )


def utc_now() -> datetime:
    return datetime.now(UTC)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hash_identity_ref(value: str) -> str:
    normalized = value.strip()
    if SHA256_HEX_RE.fullmatch(normalized):
        return normalized
    if not normalized:
        raise ValueError("identity reference cannot be empty")
    return sha256_text(normalized)


def stable_id(prefix: str, *parts: object) -> str:
    digest = sha256_text("|".join(str(part) for part in parts))[:24]
    return f"{prefix}-{digest}"


def make_membership_id(workspace_id: str, principal_id: str) -> str:
    return stable_id("membership", workspace_id, principal_id)


def _validate_safe_id(value: str, field_name: str) -> str:
    if not SAFE_ID_RE.fullmatch(value):
        raise ValueError(f"{field_name} must be a safe identifier")
    return value


def _validate_optional_hash(value: str | None, field_name: str) -> str | None:
    if value is not None and not SHA256_HEX_RE.fullmatch(value):
        raise ValueError(f"{field_name} must be sha256 hex")
    return value


class EnterpriseOrganization(StrictModel):
    schema_version: Literal["enterprise-organization/v1"] = Field(
        default="enterprise-organization/v1",
        alias="schemaVersion",
    )
    organization_id: str = Field(alias="organizationId")
    display_name: str = Field(alias="displayName", min_length=1, max_length=160)
    status: Literal["active", "blocked", "archived"]
    created_by_principal_id: str = Field(alias="createdByPrincipalId")
    created_at_utc: datetime = Field(alias="createdAtUtc")
    updated_at_utc: datetime = Field(alias="updatedAtUtc")

    @field_validator("organization_id", "created_by_principal_id")
    @classmethod
    def _safe_ids(cls, value: str, info: Any) -> str:
        return _validate_safe_id(value, str(info.field_name))


class EnterpriseWorkspace(StrictModel):
    schema_version: Literal["enterprise-workspace/v1"] = Field(
        default="enterprise-workspace/v1",
        alias="schemaVersion",
    )
    workspace_id: str = Field(alias="workspaceId")
    organization_id: str = Field(alias="organizationId")
    display_name: str = Field(alias="displayName", min_length=1, max_length=160)
    environment: Literal["dev", "staging", "production", "pilot"]
    status: Literal["active", "setup_required", "blocked", "archived"]
    default_policy_pack_id: str | None = Field(default=None, alias="defaultPolicyPackId")
    memory_authority_mode: Literal["local_authority", "disabled"] = Field(
        alias="memoryAuthorityMode"
    )
    provider_policy_profile: str = Field(alias="providerPolicyProfile", min_length=1)
    evidence_mode: Literal["hash_only"] = Field(alias="evidenceMode")
    created_by_principal_id: str = Field(alias="createdByPrincipalId")
    created_at_utc: datetime = Field(alias="createdAtUtc")
    updated_at_utc: datetime = Field(alias="updatedAtUtc")

    @field_validator(
        "workspace_id",
        "organization_id",
        "created_by_principal_id",
        "default_policy_pack_id",
    )
    @classmethod
    def _safe_ids(cls, value: str | None, info: Any) -> str | None:
        if value is None:
            return None
        return _validate_safe_id(value, str(info.field_name))


class EnterprisePrincipal(StrictModel):
    schema_version: Literal["enterprise-principal/v1"] = Field(
        default="enterprise-principal/v1",
        alias="schemaVersion",
    )
    principal_id: str = Field(alias="principalId")
    principal_type: Literal[
        "human_user",
        "service_agent",
        "external_agent",
        "device_host",
        "break_glass",
    ] = Field(alias="principalType")
    display_name: str = Field(alias="displayName", min_length=1, max_length=160)
    status: Literal["active", "disabled", "revoked", "pending"]
    external_subject_ref_hash: str | None = Field(default=None, alias="externalSubjectRefHash")
    issuer_hash: str | None = Field(default=None, alias="issuerHash")
    created_at_utc: datetime = Field(alias="createdAtUtc")
    last_seen_at_utc: datetime | None = Field(default=None, alias="lastSeenAtUtc")

    @field_validator("principal_id")
    @classmethod
    def _safe_id(cls, value: str) -> str:
        return _validate_safe_id(value, "principal_id")

    @field_validator("external_subject_ref_hash", "issuer_hash")
    @classmethod
    def _hashes(cls, value: str | None, info: Any) -> str | None:
        return _validate_optional_hash(value, str(info.field_name))


class EnterpriseWorkspaceMembership(StrictModel):
    schema_version: Literal["enterprise-membership/v1"] = Field(
        default="enterprise-membership/v1",
        alias="schemaVersion",
    )
    membership_id: str = Field(alias="membershipId")
    workspace_id: str = Field(alias="workspaceId")
    principal_id: str = Field(alias="principalId")
    roles: tuple[str, ...]
    status: Literal["active", "suspended", "revoked"]
    granted_by_principal_id: str = Field(alias="grantedByPrincipalId")
    granted_at_utc: datetime = Field(alias="grantedAtUtc")
    expires_at_utc: datetime | None = Field(default=None, alias="expiresAtUtc")

    @field_validator("membership_id", "workspace_id", "principal_id", "granted_by_principal_id")
    @classmethod
    def _safe_ids(cls, value: str, info: Any) -> str:
        return _validate_safe_id(value, str(info.field_name))

    @field_validator("roles")
    @classmethod
    def _roles_non_empty_unique_sorted(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        roles = tuple(sorted(set(value)))
        if not roles:
            raise ValueError("roles cannot be empty")
        for role in roles:
            _validate_safe_id(role, "role")
        return roles


class EnterpriseDevice(StrictModel):
    schema_version: Literal["enterprise-device/v1"] = Field(
        default="enterprise-device/v1",
        alias="schemaVersion",
    )
    device_id: str = Field(alias="deviceId")
    workspace_id: str = Field(alias="workspaceId")
    principal_id: str = Field(alias="principalId")
    display_name: str = Field(alias="displayName", min_length=1, max_length=160)
    platform: Literal["linux", "macos", "windows", "unknown"]
    host_fingerprint_hash: str | None = Field(default=None, alias="hostFingerprintHash")
    status: Literal["pending", "active", "suspended", "revoked"]
    created_at_utc: datetime = Field(alias="createdAtUtc")
    last_seen_at_utc: datetime | None = Field(default=None, alias="lastSeenAtUtc")

    @field_validator("device_id", "workspace_id", "principal_id")
    @classmethod
    def _safe_ids(cls, value: str, info: Any) -> str:
        return _validate_safe_id(value, str(info.field_name))

    @field_validator("host_fingerprint_hash")
    @classmethod
    def _host_hash(cls, value: str | None) -> str | None:
        return _validate_optional_hash(value, "host_fingerprint_hash")


class EnterpriseIdentitySummary(StrictModel):
    enabled: bool
    verified: bool
    actor_id: str | None = Field(default=None, alias="actorId")
    error_code: str | None = Field(default=None, alias="errorCode")


class EnterpriseOrganizationSummary(StrictModel):
    organization_id: str = Field(alias="organizationId")
    display_name: str = Field(alias="displayName")
    status: str = "active"


class EnterpriseWorkspaceSummary(StrictModel):
    workspace_id: str = Field(alias="workspaceId")
    display_name: str = Field(alias="displayName")
    status: str = "active"
    environment: str | None = None


class EnterprisePrincipalSummary(StrictModel):
    principal_id: str = Field(alias="principalId")
    display_name: str = Field(alias="displayName")
    principal_type: str | None = Field(default=None, alias="principalType")
    status: str = "active"


class EnterpriseMembershipSummary(StrictModel):
    membership_id: str = Field(alias="membershipId")
    principal_id: str | None = Field(default=None, alias="principalId")
    workspace_id: str | None = Field(default=None, alias="workspaceId")
    roles: list[str] = Field(default_factory=list)
    status: str = "active"


class CanonicalRoleSummary(StrictModel):
    role_id: str = Field(alias="roleId")
    label: str
    risk: str
    permissions: list[str] = Field(default_factory=list)


class EnterpriseDeviceSummary(StrictModel):
    device_id: str = Field(alias="deviceId")
    status: str
    workspace_id: str | None = Field(default=None, alias="workspaceId")
    principal_id: str | None = Field(default=None, alias="principalId")
    display_name: str | None = Field(default=None, alias="displayName")
    platform: str | None = None


class EnterpriseEnrollmentSummary(StrictModel):
    active: int = 0
    pending_approval: int = Field(default=0, alias="pendingApproval")
    revoked: int = 0
    expired_tokens: int = Field(default=0, alias="expiredTokens")


class EnterpriseWorkspaceSnapshot(StrictModel):
    schema_version: Literal["enterprise-workspace-snapshot/v1"] = Field(
        default="enterprise-workspace-snapshot/v1",
        alias="schemaVersion",
    )
    status: Literal["ready", "setup_required", "blocked", "disabled"]
    identity: EnterpriseIdentitySummary
    organization: EnterpriseOrganizationSummary | None = None
    workspaces: list[EnterpriseWorkspaceSummary] = Field(default_factory=list)
    current_workspace_id: str | None = Field(default=None, alias="currentWorkspaceId")
    principals: list[EnterprisePrincipalSummary] = Field(default_factory=list)
    memberships: list[EnterpriseMembershipSummary] = Field(default_factory=list)
    roles: list[CanonicalRoleSummary] = Field(default_factory=list)
    devices: list[EnterpriseDeviceSummary] = Field(default_factory=list)
    enrollments: EnterpriseEnrollmentSummary = Field(default_factory=EnterpriseEnrollmentSummary)
    permission_matrix: dict[str, list[str]] = Field(default_factory=dict, alias="permissionMatrix")
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")
    raw_secrets_exposed: Literal[False] = Field(default=False, alias="rawSecretsExposed")
    network_listener_enabled: Literal[False] = Field(
        default=False,
        alias="networkListenerEnabled",
    )
    generated_at_utc: datetime = Field(default_factory=utc_now, alias="generatedAtUtc")

    @model_validator(mode="after")
    def _blocked_requires_reason(self) -> EnterpriseWorkspaceSnapshot:
        if self.status == "blocked" and not self.blocking_reasons:
            raise ValueError("blocked snapshot requires blocking reasons")
        return self


class EnterpriseWorkspaceBootstrapRequest(StrictModel):
    organization_id: str = Field(alias="organizationId")
    workspace_id: str = Field(alias="workspaceId")
    display_name: str = Field(alias="displayName", min_length=1, max_length=160)
    environment: Literal["dev", "staging", "production", "pilot"] = "pilot"
    provider_policy_profile: str = Field(default="enterprise", alias="providerPolicyProfile")

    @field_validator("organization_id", "workspace_id")
    @classmethod
    def _safe_ids(cls, value: str, info: Any) -> str:
        return _validate_safe_id(value, str(info.field_name))


class EnterpriseWorkspaceBootstrapResult(StrictModel):
    schema_version: Literal["enterprise-workspace-bootstrap-result/v1"] = Field(
        default="enterprise-workspace-bootstrap-result/v1",
        alias="schemaVersion",
    )
    status: Literal["created", "unchanged", "blocked", "conflict"]
    organization_id: str | None = Field(default=None, alias="organizationId")
    workspace_id: str | None = Field(default=None, alias="workspaceId")
    bootstrap_principal_id: str | None = Field(default=None, alias="bootstrapPrincipalId")
    membership_id: str | None = Field(default=None, alias="membershipId")
    evidence_ref: str | None = Field(default=None, alias="evidenceRef")
    blocking_reasons: list[str] = Field(default_factory=list, alias="blockingReasons")
    raw_secrets_exposed: Literal[False] = Field(default=False, alias="rawSecretsExposed")


def build_bootstrap_principal_from_actor(actor: Any) -> EnterprisePrincipal:
    actor_id = str(actor.actor_id)
    principal_type = (
        "break_glass" if bool(getattr(actor, "is_break_glass", False)) else "human_user"
    )
    return EnterprisePrincipal(
        principalId=stable_id("principal", actor_id),
        principalType=principal_type,
        displayName=actor_id,
        status="active",
        externalSubjectRefHash=hash_identity_ref(str(actor.subject)),
        issuerHash=hash_identity_ref(str(actor.issuer)),
        createdAtUtc=utc_now(),
        lastSeenAtUtc=utc_now(),
    )


def bootstrap_enterprise_workspace(
    *,
    config: Any,
    request: EnterpriseWorkspaceBootstrapRequest,
    root_dir: str | Path = CONTROL_PLANE_STATE_ROOT,
    env: dict[str, str] | None = None,
) -> EnterpriseWorkspaceBootstrapResult:
    from imperaos.control_plane.enterprise_workspace_store import EnterpriseWorkspaceStore
    from imperaos.enterprise.identity import IdentityResolutionError, resolve_actor_context

    try:
        actor = resolve_actor_context(config, env=env)
    except IdentityResolutionError as exc:
        return EnterpriseWorkspaceBootstrapResult(
            status="blocked",
            blockingReasons=[exc.error_code],
            rawSecretsExposed=False,
        )

    store = EnterpriseWorkspaceStore(root_dir)
    now = utc_now()
    principal = build_bootstrap_principal_from_actor(actor)
    organization = EnterpriseOrganization(
        organizationId=request.organization_id,
        displayName=request.organization_id,
        status="active",
        createdByPrincipalId=principal.principal_id,
        createdAtUtc=now,
        updatedAtUtc=now,
    )
    workspace = EnterpriseWorkspace(
        workspaceId=request.workspace_id,
        organizationId=request.organization_id,
        displayName=request.display_name,
        environment=request.environment,
        status="active",
        defaultPolicyPackId=None,
        memoryAuthorityMode="local_authority",
        providerPolicyProfile=request.provider_policy_profile,
        evidenceMode="hash_only",
        createdByPrincipalId=principal.principal_id,
        createdAtUtc=now,
        updatedAtUtc=now,
    )
    membership_id = make_membership_id(request.workspace_id, principal.principal_id)
    membership = EnterpriseWorkspaceMembership(
        membershipId=membership_id,
        workspaceId=request.workspace_id,
        principalId=principal.principal_id,
        roles=("platform_admin",),
        status="active",
        grantedByPrincipalId=principal.principal_id,
        grantedAtUtc=now,
    )

    write_results = [
        store.write_organization(organization),
        store.write_workspace(workspace),
        store.write_principal(principal),
        store.write_membership(membership),
    ]
    if any(result.status == "conflict" for result in write_results):
        return EnterpriseWorkspaceBootstrapResult(
            status="conflict",
            organizationId=request.organization_id,
            workspaceId=request.workspace_id,
            bootstrapPrincipalId=principal.principal_id,
            membershipId=membership_id,
            blockingReasons=["ENTERPRISE_WORKSPACE_CONFLICT"],
        )

    evidence_ref = store.write_evidence_event(
        event_type="enterprise_workspace_bootstrap",
        payload={
            "organizationId": request.organization_id,
            "workspaceId": request.workspace_id,
            "principalId": principal.principal_id,
            "membershipId": membership_id,
            "actorIdHash": hash_identity_ref(str(actor.actor_id)),
            "status": "created"
            if any(result.status == "written" for result in write_results)
            else "unchanged",
        },
    )
    status = (
        "created"
        if any(result.status == "written" for result in write_results)
        else "unchanged"
    )
    return EnterpriseWorkspaceBootstrapResult(
        status=status,
        organizationId=request.organization_id,
        workspaceId=request.workspace_id,
        bootstrapPrincipalId=principal.principal_id,
        membershipId=membership_id,
        evidenceRef=evidence_ref,
    )
