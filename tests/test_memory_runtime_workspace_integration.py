from pathlib import Path

from imperaos.memory.authority import build_memory_authority
from imperaos.memory.runtime_bridge import MemoryRuntimeBridge, RuntimeMemoryRequest
from imperaos.memory.workspace_authority import build_workspace_memory_authority
from imperaos.memory.workspace_models import (
    MemoryPrincipal,
    MemoryWorkspace,
    MemoryWorkspaceMembership,
    WorkspaceMemoryWriteRequest,
)
from imperaos.runtime.config import RuntimeConfig


def test_runtime_bridge_uses_workspace_authority_when_enabled(tmp_path: Path) -> None:
    config = RuntimeConfig.from_profile("balanced")
    config.memory.v3_enabled = False
    config.memory.runtime.enabled = True
    config.memory.workspace_authority.enabled = True
    config.memory.workspace_authority.db_path = str(tmp_path / "workspace_memory.sqlite3")
    workspace_authority = build_workspace_memory_authority(
        config,
        evidence_root=tmp_path / "evidence",
    )
    workspace_authority.store.upsert_principal(
        MemoryPrincipal(principalId="operator-local", principalType="operator", displayName="OP")
    )
    workspace_authority.store.create_workspace(
        MemoryWorkspace(
            workspaceId="default",
            displayName="Default",
            ownerPrincipalId="operator-local",
        )
    )
    workspace_authority.store.grant_membership(
        MemoryWorkspaceMembership(
            membershipId="member-operator-local",
            workspaceId="default",
            principalId="operator-local",
            roles=("owner",),
            grantedBy="operator-local",
        )
    )
    workspace_authority.propose_or_write(
        WorkspaceMemoryWriteRequest(
            workspaceId="default",
            principalId="operator-local",
            scopeType="personal",
            scopeId="operator-local",
            summary="Workspace bridge remembers provider evidence.",
        )
    )
    bridge = MemoryRuntimeBridge(
        config=config,
        authority=build_memory_authority(config, evidence_root=tmp_path / "legacy"),
        workspace_authority=workspace_authority,
    )

    pack = bridge.retrieve_context(
        RuntimeMemoryRequest(
            run_id="run-workspace",
            query="provider evidence",
            actor_id="operator-local",
            requester_role="operator",
        )
    )

    assert pack.status == "pass"
    assert pack.hits[0].redacted_summary == "Workspace bridge remembers provider evidence."
    assert pack.raw_content_included is False
