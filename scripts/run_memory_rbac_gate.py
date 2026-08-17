from __future__ import annotations

import json
import tempfile
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


def main() -> None:
    with tempfile.TemporaryDirectory() as temp:
        store = WorkspaceMemoryStore(Path(temp) / "workspace_memory.sqlite3")
        store.upsert_principal(
            MemoryPrincipal(
                principalId="operator-local",
                principalType="operator",
                displayName="OP",
            )
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
        store.upsert_acl_rule(
            MemoryScopeAclRule(
                aclId="acl-deny-team-read",
                workspaceId="default",
                scopeType="team",
                scopeId="platform",
                role="owner",
                permissions=("memory.read.team",),
                effect="deny",
                reason="gate deny precedence",
            )
        )
        evaluator = MemoryAccessEvaluator(store=store)
        unknown = evaluator.evaluate(
            MemoryAccessRequest(
                workspaceId="default",
                principalId="missing-principal",
                action="read",
                scopeType="team",
                scopeId="platform",
                permission="memory.read.team",
            )
        )
        denied = evaluator.evaluate(
            MemoryAccessRequest(
                workspaceId="default",
                principalId="operator-local",
                action="read",
                scopeType="team",
                scopeId="platform",
                permission="memory.read.team",
            )
        )
        status = (
            "pass"
            if unknown.reason_code == "MEMORY_PRINCIPAL_UNKNOWN"
            and denied.reason_code == "MEMORY_SCOPE_ACL_DENY"
            else "fail"
        )
        print(
            json.dumps(
                {
                    "status": status,
                    "unknownPrincipal": unknown.model_dump(mode="json", by_alias=True),
                    "denyPrecedence": denied.model_dump(mode="json", by_alias=True),
                },
                indent=2,
                sort_keys=True,
            )
        )
        if status != "pass":
            raise SystemExit(1)


if __name__ == "__main__":
    main()
