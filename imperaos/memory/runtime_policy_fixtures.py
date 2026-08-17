from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from imperaos.memory.authority import build_memory_authority
from imperaos.memory.runtime_bridge import MemoryRuntimeBridge
from imperaos.memory.semantic import IndexRebuildRequest, SemanticMemoryService
from imperaos.memory.workspace_authority import build_workspace_memory_authority
from imperaos.memory.workspace_models import (
    MemoryPrincipal,
    MemoryScopeAclRule,
    MemoryWorkspace,
    MemoryWorkspaceMembership,
    WorkspaceMemoryWriteRequest,
)
from imperaos.runtime.config import RuntimeConfig


@dataclass(frozen=True, slots=True)
class MemoryRuntimePolicyFixture:
    config: RuntimeConfig
    bridge: MemoryRuntimeBridge
    evidence_root: Path


def build_memory_runtime_policy_fixture(
    tmp_root: Path,
    *,
    profile: str = "enterprise",
    semantic_mode: str = "disabled",
    semantic_enabled: bool = False,
) -> MemoryRuntimePolicyFixture:
    evidence_root = tmp_root / "artifacts"
    config = RuntimeConfig.from_profile(profile)
    config.memory.runtime.enabled = True
    config.memory.runtime.policy_enforcement_enabled = True
    config.memory.runtime.post_run_write_enabled = True
    config.memory.runtime.semantic_runtime_mode = semantic_mode
    config.memory.workspace_authority.enabled = True
    config.memory.workspace_authority.db_path = str(tmp_root / "workspace_memory.sqlite3")
    config.memory.workspace_authority.default_workspace_id = "workspace-main"
    config.memory.workspace_authority.default_principal_id = "operator-main"
    config.memory.semantic.enabled = semantic_enabled
    config.memory.semantic.runtime_injection_enabled = semantic_enabled
    config.memory.semantic.backend = "sqlite_text"
    authority = build_workspace_memory_authority(
        config,
        evidence_root=evidence_root / "workspace-authority",
    )
    _seed_workspace(authority)
    bridge = MemoryRuntimeBridge(
        config=config,
        authority=build_memory_authority(config, evidence_root=evidence_root / "legacy"),
        workspace_authority=authority,
        evidence_root=evidence_root / "memory-runtime",
    )
    if semantic_enabled:
        SemanticMemoryService(
            config=config,
            authority=authority,
            index_root=evidence_root / "memory-semantic" / "indexes",
        ).rebuild(IndexRebuildRequest(workspaceId="workspace-main", apply=True, dryRun=False))
    return MemoryRuntimePolicyFixture(config=config, bridge=bridge, evidence_root=evidence_root)


def _seed_workspace(authority: object) -> None:
    store = authority.store
    principals = [
        ("operator-main", "operator", "Operator Main"),
        ("agent-alpha", "agent", "Agent Alpha"),
        ("external-alpha", "agent", "External Alpha"),
        ("viewer-beta", "operator", "Viewer Beta"),
    ]
    for principal_id, principal_type, display in principals:
        store.upsert_principal(
            MemoryPrincipal(
                principalId=principal_id,
                principalType=principal_type,
                displayName=display,
            )
        )
    store.create_workspace(
        MemoryWorkspace(
            workspaceId="workspace-main",
            displayName="Workspace Main",
            ownerPrincipalId="operator-main",
        )
    )
    for principal_id, roles in (
        ("operator-main", ("owner",)),
        ("agent-alpha", ("agent",)),
        ("external-alpha", ("agent",)),
        ("viewer-beta", ("viewer",)),
    ):
        store.grant_membership(
            MemoryWorkspaceMembership(
                membershipId=f"member-{principal_id}",
                workspaceId="workspace-main",
                principalId=principal_id,
                roles=roles,
                grantedBy="operator-main",
            )
        )
    for rule in (
        MemoryScopeAclRule(
            aclId="acl-team-alpha-agent",
            workspaceId="workspace-main",
            scopeType="team",
            scopeId="team-alpha",
            principalId="agent-alpha",
            permissions=("memory.read.team", "memory.write.team"),
            effect="allow",
            reason="fixture team access",
        ),
        MemoryScopeAclRule(
            aclId="acl-case-42-agent",
            workspaceId="workspace-main",
            scopeType="case",
            scopeId="case-42",
            principalId="agent-alpha",
            permissions=("memory.read.case", "memory.write.case"),
            effect="allow",
            reason="fixture case access",
        ),
    ):
        store.upsert_acl_rule(rule)
    for request in (
        WorkspaceMemoryWriteRequest(
            workspaceId="workspace-main",
            principalId="operator-main",
            scopeType="personal",
            scopeId="operator-main",
            summary="Operator prefers hash only policy evidence.",
            memoryTarget="operator-policy",
        ),
        WorkspaceMemoryWriteRequest(
            workspaceId="workspace-main",
            principalId="agent-alpha",
            scopeType="agent",
            scopeId="agent-alpha",
            summary="Agent alpha handles provider governance follow ups.",
            memoryTarget="agent-provider",
        ),
        WorkspaceMemoryWriteRequest(
            workspaceId="workspace-main",
            principalId="agent-alpha",
            scopeType="team",
            scopeId="team-alpha",
            summary="Team alpha keeps runtime policy evidence redacted.",
            memoryTarget="team-policy",
        ),
    ):
        authority.propose_or_write(request)
