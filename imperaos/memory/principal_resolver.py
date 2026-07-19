from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import Field

from imperaos.memory.models import StrictModel, hash_identity
from imperaos.memory.workspace_models import WorkspaceScopeType
from imperaos.runtime.config import RuntimeConfig

PrincipalKind = Literal["operator", "session", "agent", "team_agent", "external_agent"]
ResolutionStatus = Literal["pass", "degraded", "denied", "error"]


class ParsedMemoryScope(StrictModel):
    scope_type: WorkspaceScopeType = Field(alias="scopeType")
    scope_id: str = Field(alias="scopeId")
    raw: str

    @property
    def wire(self) -> str:
        return f"{self.scope_type}:{self.scope_id}"


class ResolvedMemoryPrincipal(StrictModel):
    status: ResolutionStatus = "pass"
    principal_kind: PrincipalKind = Field(alias="principalKind")
    principal_id: str = Field(alias="principalId")
    principal_hash: str = Field(alias="principalHash")
    workspace_id: str = Field(alias="workspaceId")
    requested_scopes: tuple[str, ...] = Field(default_factory=tuple, alias="requestedScopes")
    allowed_scopes: tuple[str, ...] = Field(default_factory=tuple, alias="allowedScopes")
    denied_scopes: tuple[str, ...] = Field(default_factory=tuple, alias="deniedScopes")
    roles: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = Field(default_factory=tuple, alias="reasonCodes")
    raw_content_included: Literal[False] = Field(default=False, alias="rawContentIncluded")


@dataclass(frozen=True, slots=True)
class PrincipalResolutionInput:
    actor_id: str
    requester_role: str
    workspace_id: str | None = None
    principal_id: str | None = None
    agent_id: str | None = None
    team_id: str | None = None
    case_id: str | None = None
    project_id: str | None = None
    requested_scopes: tuple[str, ...] = ()


class AgentMemoryPrincipalResolver:
    def __init__(self, *, config: RuntimeConfig, workspace_authority: object | None = None) -> None:
        self.config = config
        self.workspace_authority = workspace_authority

    def resolve(self, request: PrincipalResolutionInput) -> ResolvedMemoryPrincipal:
        workspace_id = (
            request.workspace_id
            or self.config.memory.workspace_authority.default_workspace_id
            or "default"
        )
        kind = self._principal_kind(request)
        principal_id = self._principal_id(request, kind)
        reason_codes: list[str] = []
        status: ResolutionStatus = "pass"
        if not principal_id:
            reason_codes.append("MEMORY_PRINCIPAL_UNAVAILABLE")
            status = "error" if self._strict else "degraded"
            principal_id = self.config.memory.workspace_authority.default_principal_id

        requested_scopes = tuple(
            dict.fromkeys(
                request.requested_scopes
                or _derived_scopes(
                    principal_id=principal_id,
                    agent_id=request.agent_id,
                    team_id=request.team_id,
                    case_id=request.case_id,
                    project_id=request.project_id,
                )
            )
        )
        parsed_scopes: list[ParsedMemoryScope] = []
        denied_scopes: list[str] = []
        for raw_scope in requested_scopes:
            try:
                parsed_scopes.append(parse_memory_scope(raw_scope))
            except ValueError:
                denied_scopes.append(raw_scope)
                reason_codes.append("MEMORY_RUNTIME_SCOPE_INVALID")
        if not parsed_scopes:
            reason_codes.append("MEMORY_RUNTIME_SCOPE_UNAVAILABLE")
            status = "error" if self._strict else "degraded"

        roles = self._membership_roles(workspace_id, principal_id)
        if self.config.memory.workspace_authority.enabled:
            if roles is None:
                reason_codes.append("MEMORY_WORKSPACE_MEMBERSHIP_UNAVAILABLE")
                status = "error" if self._strict else "degraded"
            elif not roles:
                reason_codes.append("MEMORY_WORKSPACE_MEMBERSHIP_DENIED")
                status = "denied" if self._strict else "degraded"
        elif self._strict:
            reason_codes.append("MEMORY_WORKSPACE_AUTHORITY_DISABLED")
            status = "error"

        return ResolvedMemoryPrincipal(
            status=status,
            principalKind=kind,
            principalId=principal_id,
            principalHash=hash_identity(principal_id),
            workspaceId=workspace_id,
            requestedScopes=requested_scopes,
            allowedScopes=tuple(scope.wire for scope in parsed_scopes),
            deniedScopes=tuple(denied_scopes),
            roles=tuple(roles or ()),
            reasonCodes=tuple(dict.fromkeys(reason_codes)),
            rawContentIncluded=False,
        )

    @property
    def _strict(self) -> bool:
        return self.config.profile_name in set(
            self.config.memory.runtime.strict_fail_closed_profiles
        )

    def _principal_kind(self, request: PrincipalResolutionInput) -> PrincipalKind:
        role = request.requester_role.lower().replace("-", "_")
        if role in {"external_agent", "external"}:
            return "external_agent"
        if role in {"agent", "assistant"} and request.team_id:
            return "team_agent"
        if role in {"agent", "assistant"}:
            return "agent"
        if role in {"session", "anonymous", "guest"}:
            return "session"
        return "operator"

    def _principal_id(self, request: PrincipalResolutionInput, kind: PrincipalKind) -> str:
        if request.principal_id:
            return request.principal_id
        if kind in {"agent", "team_agent", "external_agent"} and request.agent_id:
            return request.agent_id
        if kind == "session":
            return f"session:{hash_identity(request.actor_id)[:24]}"
        return request.actor_id or self.config.memory.workspace_authority.default_principal_id

    def _membership_roles(self, workspace_id: str, principal_id: str) -> tuple[str, ...] | None:
        enterprise_roles = self._enterprise_membership_roles(workspace_id, principal_id)
        if enterprise_roles is not None:
            return enterprise_roles
        authority = self.workspace_authority
        if authority is None or not hasattr(authority, "store"):
            return None if self.config.memory.workspace_authority.enabled else ()
        store = authority.store
        workspace = store.get_workspace(workspace_id)
        principal = store.get_principal(principal_id)
        if workspace is None or principal is None:
            return ()
        membership = store.get_membership(
            workspace_id=workspace_id,
            principal_id=principal_id,
        )
        if membership is None or membership.status != "active":
            return ()
        return tuple(membership.roles)

    def _enterprise_membership_roles(
        self,
        workspace_id: str,
        principal_id: str,
    ) -> tuple[str, ...] | None:
        try:
            from imperaos.control_plane.enterprise_workspace_store import EnterpriseWorkspaceStore

            store = EnterpriseWorkspaceStore()
            workspace = store.get_workspace(workspace_id)
            principal = store.get_principal(principal_id)
            if workspace is None and principal is None:
                return None
            if workspace is None or principal is None:
                return ()
            memberships = store.list_memberships(
                workspace_id=workspace_id,
                principal_id=principal_id,
            )
        except Exception:
            return None
        roles: list[str] = []
        for membership in memberships:
            if membership.status == "active":
                roles.extend(membership.roles)
        return tuple(sorted(set(roles)))


def parse_memory_scope(value: str) -> ParsedMemoryScope:
    if ":" not in value:
        raise ValueError("memory scope must use scope_type:scope_id")
    scope_type, scope_id = value.split(":", 1)
    if not scope_type or not scope_id:
        raise ValueError("memory scope must include scope_type and scope_id")
    return ParsedMemoryScope(scopeType=scope_type, scopeId=scope_id, raw=value)


def _derived_scopes(
    *,
    principal_id: str,
    agent_id: str | None,
    team_id: str | None,
    case_id: str | None,
    project_id: str | None,
) -> tuple[str, ...]:
    scopes = [f"personal:{principal_id}"]
    if agent_id:
        scopes.append(f"agent:{agent_id}")
    if team_id:
        scopes.append(f"team:{team_id}")
    if case_id:
        scopes.append(f"case:{case_id}")
    if project_id:
        scopes.append(f"project:{project_id}")
    return tuple(scopes)
