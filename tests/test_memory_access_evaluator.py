from pathlib import Path

from imperaos.memory.access_evaluator import MemoryAccessEvaluator
from imperaos.memory.workspace_models import (
    MemoryAccessRequest,
    MemoryPrincipal,
    MemoryScopeAclRule,
    MemoryWorkspace,
    MemoryWorkspaceMembership,
)
from imperaos.memory.workspace_store import WorkspaceMemoryStore


def _store(tmp_path: Path) -> WorkspaceMemoryStore:
    store = WorkspaceMemoryStore(tmp_path / "workspace_memory.sqlite3")
    store.upsert_principal(
        MemoryPrincipal(principalId="operator-local", principalType="operator", displayName="OP")
    )
    store.create_workspace(
        MemoryWorkspace(
            workspaceId="default",
            displayName="Default",
            ownerPrincipalId="operator-local",
        )
    )
    store.grant_membership(
        MemoryWorkspaceMembership(
            membershipId="member-operator-local",
            workspaceId="default",
            principalId="operator-local",
            roles=("owner",),
            grantedBy="operator-local",
        )
    )
    return store


def test_rbac_unknown_principal_denies_fail_closed(tmp_path: Path) -> None:
    decision = MemoryAccessEvaluator(store=_store(tmp_path)).evaluate(
        MemoryAccessRequest(
            workspaceId="default",
            principalId="missing-principal",
            action="read",
            scopeType="team",
            scopeId="platform",
            permission="memory.read.team",
        )
    )

    assert decision.action == "deny"
    assert decision.reason_code == "MEMORY_PRINCIPAL_UNKNOWN"


def test_rbac_explicit_deny_precedes_owner_role(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.upsert_acl_rule(
        MemoryScopeAclRule(
            aclId="acl-deny-owner",
            workspaceId="default",
            scopeType="team",
            scopeId="platform",
            role="owner",
            permissions=("memory.read.team",),
            effect="deny",
            reason="deny test",
        )
    )

    decision = MemoryAccessEvaluator(store=store).evaluate(
        MemoryAccessRequest(
            workspaceId="default",
            principalId="operator-local",
            action="read",
            scopeType="team",
            scopeId="platform",
            permission="memory.read.team",
        )
    )

    assert decision.action == "deny"
    assert decision.reason_code == "MEMORY_SCOPE_ACL_DENY"
