from pathlib import Path

from imperaos.memory.workspace_authority import build_workspace_memory_authority
from imperaos.memory.workspace_models import (
    MemoryPrincipal,
    MemoryWorkspace,
    MemoryWorkspaceMembership,
    WorkspaceMemoryWriteRequest,
)
from imperaos.runtime.config import RuntimeConfig


def test_workspace_authority_evidence_has_no_raw_candidate_fields(tmp_path: Path) -> None:
    config = RuntimeConfig.from_profile("balanced")
    config.memory.workspace_authority.enabled = True
    config.memory.workspace_authority.db_path = str(tmp_path / "workspace_memory.sqlite3")
    authority = build_workspace_memory_authority(config, evidence_root=tmp_path / "evidence")
    authority.store.upsert_principal(
        MemoryPrincipal(principalId="operator-local", principalType="operator", displayName="OP")
    )
    authority.store.create_workspace(
        MemoryWorkspace(
            workspaceId="default",
            displayName="Default",
            ownerPrincipalId="operator-local",
        )
    )
    authority.store.grant_membership(
        MemoryWorkspaceMembership(
            membershipId="member-operator-local",
            workspaceId="default",
            principalId="operator-local",
            roles=("owner",),
            grantedBy="operator-local",
        )
    )

    authority.propose_or_write(
        WorkspaceMemoryWriteRequest(
            workspaceId="default",
            principalId="operator-local",
            scopeType="personal",
            scopeId="operator-local",
            summary="Evidence artifact should contain only hashes and policy data.",
        )
    )

    evidence = (tmp_path / "evidence" / "latest.json").read_text(encoding="utf-8")
    assert "candidateText" not in evidence
    assert "raw secret" not in evidence
    assert '"rawContentIncluded": false' in evidence
