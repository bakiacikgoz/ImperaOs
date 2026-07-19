from __future__ import annotations

from pathlib import Path
from typing import Any, TypeVar

from pydantic import Field

from imperaos.control_plane.agent_enrollment import (
    AgentEnrollmentRequest,
    AgentEnrollmentToken,
    EnrolledAgent,
)
from imperaos.control_plane.enterprise_workspace import (
    EnterpriseDevice,
    EnterpriseOrganization,
    EnterprisePrincipal,
    EnterpriseWorkspace,
    EnterpriseWorkspaceMembership,
    StrictModel,
    stable_id,
    utc_now,
)
from imperaos.control_plane.storage import ControlPlaneStore, canonical_json_hash
from imperaos.runtime.paths import CONTROL_PLANE_STATE_ROOT

ModelT = TypeVar("ModelT", bound=StrictModel)


class StoreWriteResult(StrictModel):
    status: str
    path: str
    existing_hash: str | None = Field(default=None, alias="existingHash")
    new_hash: str | None = Field(default=None, alias="newHash")


class EnterpriseWorkspaceStore:
    def __init__(self, root_dir: str | Path = CONTROL_PLANE_STATE_ROOT) -> None:
        self.store = ControlPlaneStore(root_dir)
        self.base = "enterprise-workspace"

    def get_organization(self) -> EnterpriseOrganization | None:
        return self._read_model("organization.json", EnterpriseOrganization)

    def write_organization(self, organization: EnterpriseOrganization) -> StoreWriteResult:
        return self._write_model("organization.json", organization)

    def get_workspace(self, workspace_id: str) -> EnterpriseWorkspace | None:
        return self._read_model(f"workspaces/{workspace_id}.json", EnterpriseWorkspace)

    def list_workspaces(self) -> list[EnterpriseWorkspace]:
        return self._list_models("workspaces", EnterpriseWorkspace)

    def write_workspace(self, workspace: EnterpriseWorkspace) -> StoreWriteResult:
        return self._write_model(f"workspaces/{workspace.workspace_id}.json", workspace)

    def get_principal(self, principal_id: str) -> EnterprisePrincipal | None:
        return self._read_model(f"principals/{principal_id}.json", EnterprisePrincipal)

    def list_principals(self, workspace_id: str | None = None) -> list[EnterprisePrincipal]:
        del workspace_id
        return self._list_models("principals", EnterprisePrincipal)

    def write_principal(self, principal: EnterprisePrincipal) -> StoreWriteResult:
        return self._write_model(f"principals/{principal.principal_id}.json", principal)

    def get_membership(self, membership_id: str) -> EnterpriseWorkspaceMembership | None:
        return self._read_model(f"memberships/{membership_id}.json", EnterpriseWorkspaceMembership)

    def list_memberships(
        self,
        workspace_id: str | None = None,
        principal_id: str | None = None,
    ) -> list[EnterpriseWorkspaceMembership]:
        memberships = self._list_models("memberships", EnterpriseWorkspaceMembership)
        if workspace_id is not None:
            memberships = [item for item in memberships if item.workspace_id == workspace_id]
        if principal_id is not None:
            memberships = [item for item in memberships if item.principal_id == principal_id]
        return memberships

    def write_membership(self, membership: EnterpriseWorkspaceMembership) -> StoreWriteResult:
        return self._write_model(f"memberships/{membership.membership_id}.json", membership)

    def get_device(self, device_id: str) -> EnterpriseDevice | None:
        return self._read_model(f"devices/{device_id}.json", EnterpriseDevice)

    def list_devices(self, workspace_id: str | None = None) -> list[EnterpriseDevice]:
        devices = self._list_models("devices", EnterpriseDevice)
        if workspace_id is not None:
            devices = [item for item in devices if item.workspace_id == workspace_id]
        return devices

    def write_device(self, device: EnterpriseDevice) -> StoreWriteResult:
        return self._write_model(f"devices/{device.device_id}.json", device)

    def get_enrollment_token(self, token_id: str) -> AgentEnrollmentToken | None:
        return self._read_model(f"enrollment-tokens/{token_id}.json", AgentEnrollmentToken)

    def list_enrollment_tokens(self, workspace_id: str | None = None) -> list[AgentEnrollmentToken]:
        tokens = self._list_models("enrollment-tokens", AgentEnrollmentToken)
        if workspace_id is not None:
            tokens = [item for item in tokens if item.workspace_id == workspace_id]
        return tokens

    def write_enrollment_token(self, token: AgentEnrollmentToken) -> StoreWriteResult:
        return self._write_model(f"enrollment-tokens/{token.token_id}.json", token)

    def get_enrollment_request(self, request_id: str) -> AgentEnrollmentRequest | None:
        return self._read_model(f"enrollment-requests/{request_id}.json", AgentEnrollmentRequest)

    def list_enrollment_requests(
        self,
        workspace_id: str | None = None,
    ) -> list[AgentEnrollmentRequest]:
        requests = self._list_models("enrollment-requests", AgentEnrollmentRequest)
        if workspace_id is not None:
            requests = [item for item in requests if item.workspace_id == workspace_id]
        return requests

    def write_enrollment_request(self, request: AgentEnrollmentRequest) -> StoreWriteResult:
        return self._write_model(f"enrollment-requests/{request.request_id}.json", request)

    def get_enrolled_agent_by_agent_id(
        self,
        agent_id: str,
        workspace_id: str | None = None,
    ) -> EnrolledAgent | None:
        for enrollment in self.list_enrolled_agents(workspace_id=workspace_id):
            if enrollment.agent_id == agent_id:
                return enrollment
        return None

    def list_enrolled_agents(self, workspace_id: str | None = None) -> list[EnrolledAgent]:
        agents = self._list_models("enrolled-agents", EnrolledAgent)
        if workspace_id is not None:
            agents = [item for item in agents if item.workspace_id == workspace_id]
        return agents

    def write_enrolled_agent(self, enrollment: EnrolledAgent) -> StoreWriteResult:
        return self._write_model(f"enrolled-agents/{enrollment.enrollment_id}.json", enrollment)

    def write_evidence_event(self, *, event_type: str, payload: dict[str, Any]) -> str:
        event_id = stable_id(
            "event",
            event_type,
            canonical_json_hash(payload),
            utc_now().isoformat(),
        )
        relative = f"evidence/{event_id}.json"
        event = {
            "eventId": event_id,
            "eventType": event_type,
            "payloadHash": canonical_json_hash(payload),
            "payload": payload,
            "rawSecretsExposed": False,
            "generatedAtUtc": utc_now().isoformat(),
        }
        self.store.write_json_atomic(f"{self.base}/{relative}", event)
        return f"enterprise-workspace/{relative}"

    def _relative(self, relative_path: str) -> str:
        return f"{self.base}/{relative_path}"

    def _read_model(self, relative_path: str, model: type[ModelT]) -> ModelT | None:
        payload = self.store.read_json(self._relative(relative_path), default=None)
        if payload is None:
            return None
        return model.model_validate(payload)

    def _list_models(self, directory: str, model: type[ModelT]) -> list[ModelT]:
        path = self.store.path(self._relative(directory))
        if not path.exists():
            return []
        results: list[ModelT] = []
        for item in sorted(path.glob("*.json")):
            try:
                results.append(model.model_validate_json(item.read_text(encoding="utf-8")))
            except Exception:
                continue
        return results

    def _write_model(self, relative_path: str, model: StrictModel) -> StoreWriteResult:
        payload = model.model_dump(mode="json", by_alias=True)
        full_relative = self._relative(relative_path)
        existing = self.store.read_json(full_relative, default=None)
        new_hash = canonical_json_hash(payload)
        if existing is not None:
            existing_hash = canonical_json_hash(existing)
            if existing_hash == new_hash:
                return StoreWriteResult(
                    status="unchanged",
                    path=full_relative,
                    existingHash=existing_hash,
                    newHash=new_hash,
                )
            return StoreWriteResult(
                status="conflict",
                path=full_relative,
                existingHash=existing_hash,
                newHash=new_hash,
            )
        self.store.write_json_atomic(full_relative, payload)
        return StoreWriteResult(status="written", path=full_relative, newHash=new_hash)
