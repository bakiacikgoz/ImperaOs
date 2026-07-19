from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from imperaos.memory.models import stable_id
from imperaos.memory.semantic.models import IndexRebuildRequest
from imperaos.memory.semantic.service import SemanticMemoryService
from imperaos.memory.workspace_authority import build_workspace_memory_authority
from imperaos.memory.workspace_models import (
    MemoryPrincipal,
    MemoryWorkspace,
    MemoryWorkspaceMembership,
    WorkspaceMemoryWriteRequest,
)
from imperaos.runtime.config import RuntimeConfig


@dataclass(frozen=True, slots=True)
class SemanticFixture:
    config: RuntimeConfig
    service: SemanticMemoryService
    expected_memory_id: str
    hard_negative_memory_id: str


def build_semantic_fixture(root: Path) -> SemanticFixture:
    config = RuntimeConfig.from_profile("balanced")
    config.memory.workspace_authority.enabled = True
    config.memory.workspace_authority.default_workspace_id = "default"
    config.memory.workspace_authority.default_principal_id = "operator-local"
    config.memory.workspace_authority.db_path = str(root / "workspace_memory.sqlite3")
    config.memory.semantic.enabled = True
    config.memory.semantic.runtime_injection_enabled = False
    config.memory.semantic.backend = "in_memory_fixture"
    authority = build_workspace_memory_authority(
        config,
        evidence_root=root / "memory-authority",
    )
    for principal_id in ("operator-local", "intruder-local"):
        authority.store.upsert_principal(
            MemoryPrincipal(
                principalId=principal_id,
                principalType="operator",
                displayName=principal_id,
            )
        )
        authority.store.grant_membership(
            MemoryWorkspaceMembership(
                membershipId=stable_id("wm_member", "default", principal_id),
                workspaceId="default",
                principalId=principal_id,
                roles=("owner",),
                grantedBy=principal_id,
            )
        )
    authority.store.create_workspace(
        MemoryWorkspace(
            workspaceId="default",
            displayName="Default",
            ownerPrincipalId="operator-local",
        )
    )
    expected = authority.propose_or_write(
        WorkspaceMemoryWriteRequest(
            workspaceId="default",
            principalId="operator-local",
            scopeType="personal",
            scopeId="operator-local",
            summary="Provider governance RC target evidence pilot closure is ready.",
            memoryTarget="provider-governance-rc",
        )
    )
    hard_negative = authority.propose_or_write(
        WorkspaceMemoryWriteRequest(
            workspaceId="default",
            principalId="intruder-local",
            scopeType="personal",
            scopeId="intruder-local",
            summary="Private unrelated billing migration notes.",
            memoryTarget="intruder-private",
        )
    )
    service = SemanticMemoryService(
        config=config,
        authority=authority,
        index_root=root / "memory-semantic" / "indexes",
        evidence_root=root / "memory-semantic" / "events",
    )
    service.rebuild(IndexRebuildRequest(workspaceId="default", apply=True, dryRun=False))
    return SemanticFixture(
        config=config,
        service=service,
        expected_memory_id=expected.memory_id or "",
        hard_negative_memory_id=hard_negative.memory_id or "",
    )
